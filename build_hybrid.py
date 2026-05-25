#!/usr/bin/env python3
"""Hybrid deck pipeline — Mermaid + matplotlib + Gemini, all driven by
DESIGN.md.

Per-deck config (deck.toml) declares which tool each slide uses:
    [slides.4]
    type = "mermaid"
    source = "mermaid/slide-04.mmd"

    [slides.5]
    type = "gemini"
    prompt = '''
    A polished diagram of ...
    '''

    [slides.9]
    type = "chart"
    source = "charts/slide-09.py"

    [slides.2]
    type = "table"        # no image — Marp native

Run:
    python3 build_hybrid.py --deck path/to/deck.toml

Outputs (gitignored, alongside deck.toml):
    img/slide-NN.png  (per image-bearing slide)
    deck.md           (Marp source)
    deck.pptx
    deck.pdf
"""
from __future__ import annotations
import argparse
import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # fallback


SKILL_DIR = Path(__file__).resolve().parent


# ── Aspect-aware layout ─────────────────────────────────────────────────────
# Image text legibility on a 16:9 slide = SVG fontSize × (rendered_width /
# viewBox_width). When an SVG is much taller than its column (e.g. mermaid TD
# flowchart), object-fit:contain shrinks it to fit height — leaving the image
# narrow and the text tiny. Counter: pick a grid that matches the image's
# natural shape, plus bump max-height for tall images.
#
# Thresholds (W/H aspect):
#   < 0.50  very tall  → narrow right-col 35%, max-h 82vh
#   < 0.90  tall       → right-col 50%, max-h 78vh
#   ≤ 1.80  default    → right-col 62%, max-h 65vh  (no class needed)
#   > 1.80  wide       → right-col 70%, max-h 72vh
# Note: a chart at aspect ~1.55 fits the default cell width-bound and looks
# fine, so the wide threshold is set above that — only truly wide images
# (panoramic 2:1 or wider) benefit from the override.
ASPECT_VERY_TALL = 0.50
ASPECT_TALL = 0.90
ASPECT_WIDE = 1.80


def get_svg_aspect(svg_path: Path) -> float | None:
    """Return viewBox W/H from an SVG. None if it can't parse one."""
    if not svg_path.exists() or svg_path.suffix.lower() != ".svg":
        return None
    head = svg_path.read_text(encoding="utf-8", errors="replace")[:3000]
    m = re.search(r'viewBox=["\']([\d.\s,+-]+)["\']', head)
    if not m:
        return None
    parts = re.split(r"[\s,]+", m.group(1).strip())
    if len(parts) != 4:
        return None
    try:
        w, h = float(parts[2]), float(parts[3])
    except ValueError:
        return None
    return w / h if h > 0 else None


def aspect_class(aspect: float | None) -> str:
    if aspect is None:
        return ""
    if aspect < ASPECT_VERY_TALL:
        return "img-very-tall"
    if aspect < ASPECT_TALL:
        return "img-tall"
    if aspect > ASPECT_WIDE:
        return "img-wide"
    return ""


def transform_fenced_code(content: str) -> str:
    """Replace ```fenced``` blocks with <div class="codeblock"> blocks.

    Marp's <pre> rendering wraps every pre in <pre is="marp-pre"> which
    silently downscales the font when a single line overflows — that's
    why a 120-char line renders at ~9px while sibling pre blocks stay
    at 13px. Bypass by using a div that we style ourselves; div doesn't
    get the auto-scaling treatment.
    """
    out = []
    in_pre = False
    buf: list[str] = []
    for line in content.split("\n"):
        if line.lstrip().startswith("```"):
            if in_pre:
                escaped = (
                    "\n".join(buf)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                # Use explicit <br> for line breaks instead of \n —
                # markdown-it splits HTML blocks at blank lines, which
                # would inject paragraph breaks between bullets.
                escaped = escaped.replace("\n", "<br>")
                out.append(f'<div class="codeblock">{escaped}</div>')
                buf = []
                in_pre = False
            else:
                in_pre = True
            continue
        if in_pre:
            buf.append(line)
        else:
            out.append(line)
    return "\n".join(out)


def density_class(content: str) -> str:
    """Left-col text density → CSS class to widen left-col when crowded.
    Only applied when aspect class is empty (default 38/62), because the
    tall/wide bands already adjust the grid in the opposite direction.

    Rationale: for default-aspect images (0.9-1.8) the image is height-
    bound in a 62%-wide column, leaving ~13% of horizontal space unused.
    Narrowing right-col to 55% reclaims that for text without shrinking
    the image (still height-bound after the swap).
    """
    if "```" in content:
        return "left-dense"
    if content.count("\n") > 14:
        return "left-dense"
    return ""


def load_env(name: str, env_file: str) -> str | None:
    """Load $KEY from ~/.{env_file} if not in env. Returns key or None."""
    if os.environ.get(name):
        return os.environ[name]
    p = Path.home() / env_file
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith(f"{name}="):
                val = line.split("=", 1)[1].strip()
                os.environ[name] = val
                return val
    return None


# ── markdown parsing ────────────────────────────────────────────────────────

def parse_source_markdown(path: Path) -> list[dict]:
    """Split by `## Slide N: ...`, extract 5-section structure:
      標題 / 副標 (optional) / 內容 / 設計理由 (optional) / 視覺 (not used).
    Also extracts 核心觀念 / Anti-pattern callouts if present.
    """
    text = path.read_text(encoding="utf-8")
    pat = re.compile(r"^## Slide (\d+):\s*(.+?)$", re.MULTILINE)
    matches = list(pat.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        out.append({
            "num": int(m.group(1)),
            "title": _section(body, "標題") or m.group(2).strip(),
            "subtitle": _section(body, "副標"),
            "content": _section(body, "內容"),
            "design_rationale": _section(body, "設計理由"),
            "key_concept": _section(body, "核心觀念"),
            "anti_pattern": _section(body, "Anti-pattern") or _section(body, "踩雷"),
            "chapter": _section(body, "章節"),
        })
    return out


def _section(body: str, name: str) -> str:
    # Stop at the NEXT named section header OR a markdown horizontal rule
    # (`---` on its own line, which is the slide separator). A header is
    # **TEXT：** with a REQUIRED full-width or half-width colon. Bold body
    # lines like **1. 即時...** (no colon) do NOT count as a new section.
    pat = re.compile(
        rf"\*\*{name}[：:]\*\*\s*(.+?)(?=^\*\*[^*\n]+[：:]\*\*|^---\s*$|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pat.search(body)
    return m.group(1).strip() if m else ""


# ── per-slide generators ────────────────────────────────────────────────────

def _is_cache_fresh(out_path: Path, *deps: Path) -> bool:
    """True if out_path exists and is newer than every existing dep.

    Used by gen_mermaid / gen_chart / gen_svg_copy so editing source (or the
    deck-wide config / style) invalidates the cached generated artifact.
    """
    if not out_path.exists():
        return False
    out_mtime = out_path.stat().st_mtime
    for dep in deps:
        if dep.exists() and dep.stat().st_mtime > out_mtime:
            return False
    return True


def gen_mermaid(mmd_path: Path, out_svg: Path, mermaid_config: Path) -> None:
    """Render Mermaid to SVG (vector, real text — Chinese works)."""
    if _is_cache_fresh(out_svg, mmd_path, mermaid_config):
        return
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    # Windows: prefer .cmd shim; Linux/macOS: bare name
    win_mmdc = SKILL_DIR / "node_modules/.bin/mmdc.cmd"
    nix_mmdc = SKILL_DIR / "node_modules/.bin/mmdc"
    if win_mmdc.exists():
        mmdc = str(win_mmdc)
    elif nix_mmdc.exists():
        mmdc = str(nix_mmdc)
    else:
        mmdc = "mmdc"
    cmd = [str(mmdc), "-i", str(mmd_path), "-o", str(out_svg),
           "-c", str(mermaid_config), "-w", "1400", "-H", "900", "-b", "white"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"mmdc failed: {r.stderr[-300:]}")


def gen_chart(py_path: Path, out_svg: Path, mpl_style: Path) -> None:
    """Run matplotlib chart script. Script must save to OUT_PATH (.svg).

    The deck-wide mplstyle is pre-applied via a bootstrap wrapper, so chart
    authors don't need to call plt.style.use() themselves — they get the
    deck's typography / palette / CJK font fallback for free. MPL_STYLE is
    still exported so scripts that want to re-apply or inspect it can.
    """
    if _is_cache_fresh(out_svg, py_path, mpl_style):
        return
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ,
           "OUT_PATH": str(out_svg),
           "MPL_STYLE": str(mpl_style)}
    bootstrap = (
        "import matplotlib.pyplot as _plt; "
        f"_plt.style.use({str(mpl_style)!r}); "
        f"exec(open({str(py_path)!r}, encoding='utf-8').read(), "
        f"{{'__file__': {str(py_path)!r}, '__name__': '__main__'}})"
    )
    r = subprocess.run(["python3", "-c", bootstrap], capture_output=True,
                       text=True, env=env,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"chart script failed: {r.stderr[-300:]}")


def gen_svg_copy(svg_src: Path, out_svg: Path) -> None:
    """Hand-written SVG — just copy from source to img/ dir.

    Uses shutil.copy2 to preserve source mtime, so subsequent rebuilds can
    compare mtimes via _is_cache_fresh and re-copy when source is edited.
    """
    if _is_cache_fresh(out_svg, svg_src):
        return
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(svg_src, out_svg)
    if not out_svg.exists():
        raise RuntimeError(f"failed to copy SVG to {out_svg}")


def gen_gemini(prompt: str, out_png: Path, *, gemini_suffix: str,
               model: str = "gemini-2.5-flash-image",
               aspect: str = "3:2") -> None:
    if out_png.exists():
        return
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if not load_env("GEMINI_API_KEY", ".gemini.env"):
        raise RuntimeError("GEMINI_API_KEY not in env or ~/.gemini.env")
    from google import genai
    from google.genai import types

    full_prompt = prompt.rstrip() + "\n\n" + gemini_suffix
    client = genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect),
        ),
    )
    for part in response.parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            data = (inline.data if isinstance(inline.data, bytes)
                    else base64.b64decode(inline.data))
            out_png.write_bytes(data)
            return
    raise RuntimeError("Gemini returned no image")


# ── Marp emission ───────────────────────────────────────────────────────────

def emit_marp_deck(slides, deck_cfg, image_dir, out_md, footer):
    lines = [
        "---",
        "marp: true",
        "theme: marp-deck",
        "paginate: true",
        f"footer: '{footer}'",
        "---",
        "",
    ]
    # Map slide type → file extension actually produced
    ext_for = {
        "mermaid": "svg", "chart": "svg", "svg": "svg", "gemini": "png",
    }
    for s in slides:
        num = s["num"]
        cfg = deck_cfg.get("slides", {}).get(str(num), {})
        type_ = cfg.get("type", "table")
        has_image = type_ in ext_for
        if num > 1:
            lines.append("---")
            lines.append("")
        is_cover = num == 1
        if is_cover:
            lines.append("<!-- _class: cover -->")
            lines.append("<!-- _paginate: false -->")
            lines.append("<!-- _footer: '' -->")  # cover has no footer (v1.5)
        lines.append("")
        # Chapter prefix (v1.5) — mono uppercase small label above H1.
        # Skip on cover (cover has its own title treatment).
        if s.get("chapter") and not is_cover:
            ch = s["chapter"].strip().replace("\n", " ")
            lines.append(f"<p class=\"chapter-prefix\">{ch}</p>")
            lines.append("")
        # On cover, split "topic —— tagline" into clean H1 + separate tagline
        # element. This keeps H1 metadata clean (no literal "<br>" leaking into
        # PPTX slide title / PDF bookmark / image filename suggestions), while
        # the visual two-line layout is preserved via .cover-tagline CSS.
        title_text = s["title"]
        cover_tagline = None
        if is_cover and "——" in title_text:
            head, tail = title_text.split("——", 1)
            title_text = head.rstrip()
            cover_tagline = "—— " + tail.lstrip()
        lines.append(f"# {title_text}")
        if is_cover and cover_tagline:
            lines.append("")
            lines.append(f'<p class="cover-tagline">{cover_tagline}</p>')
        # Subtitle lede (v1.2)
        if s.get("subtitle"):
            sub = s["subtitle"].strip().replace("\n", " ")
            lines.append("")
            lines.append(f"<p class=\"subtitle\">{sub}</p>")
        lines.append("")
        # Cover (v1.5): emit only title + subtitle. Body content / callouts /
        # design-rationale belong on content slides, not the cover —
        # cluttering the cover breaks the "tagline" feel.
        if is_cover:
            lines.append("")
            continue
        body = transform_fenced_code(s["content"])
        if has_image:
            ext = ext_for[type_]
            img_path = image_dir / f"slide-{num:02d}.{ext}"
            ac = aspect_class(get_svg_aspect(img_path)) if ext == "svg" else ""
            # Density class only applies when image aspect is default (no
            # ac) — tall/wide bands already adjust the grid the other way.
            dc = density_class(s["content"]) if not ac else ""
            grid_cls = "slide-grid"
            if ac:
                grid_cls += f" {ac}"
            if dc:
                grid_cls += f" {dc}"
            lines.append(f"<div class=\"{grid_cls}\">")
            lines.append("<div class=\"left-col\">")
            lines.append("")
            lines.append(body.strip())
            lines.append("")
            # Per-slide callouts within the left column (key-concept / anti-pattern)
            _emit_inline_callouts(lines, s)
            lines.append("</div>")
            lines.append(
                f"<div class=\"right-col\">"
                f"<img src=\"./img/slide-{num:02d}.{ext}\" alt=\"\"></div>")
            lines.append("</div>")
        else:
            lines.append(body.strip())
            _emit_inline_callouts(lines, s)
        # Design-rationale bottom strip (full-width)
        if s.get("design_rationale"):
            dr = _inline_md_to_html(
                s["design_rationale"].strip().replace("\n", " "))
            lines.append("")
            lines.append(
                f"<div class=\"callout design-rationale\">"
                f"<span class=\"callout-label\">設計理由</span>{dr}</div>")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def _inline_md_to_html(text: str) -> str:
    """Convert minimal inline markdown (code / bold / italic) to HTML.

    Marp doesn't parse markdown inside raw HTML blocks (which is how callout
    <div>s are emitted), so `**foo**` would otherwise render as literal
    asterisks. Convert here, in this order:
      1. backtick code first (so ** inside `code` isn't bolded)
      2. `**...**` → <strong>
      3. single-* italic, but not inside ** pairs
    """
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\*<])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _emit_inline_callouts(lines, s):
    """Emit key-concept / anti-pattern callouts inline in the left column."""
    if s.get("key_concept"):
        kc = _inline_md_to_html(s["key_concept"].strip().replace("\n", " "))
        lines.append("")
        lines.append(
            f"<div class=\"callout key-concept\">"
            f"<span class=\"callout-label\">核心觀念</span>{kc}</div>")
    if s.get("anti_pattern"):
        ap = _inline_md_to_html(s["anti_pattern"].strip().replace("\n", " "))
        lines.append("")
        lines.append(
            f"<div class=\"callout anti-pattern\">"
            f"<span class=\"callout-label\">⚠ 踩雷</span>{ap}</div>")


# ── main pipeline ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, type=Path,
                    help="path to deck.toml")
    ap.add_argument("--parallel", default=3, type=int)
    args = ap.parse_args()

    cfg = tomllib.loads(args.deck.read_text(encoding="utf-8"))
    deck_dir = args.deck.resolve().parent

    meta = cfg["meta"]
    source_md = (deck_dir / meta["source"]).resolve()
    output_basename = meta["output_basename"]
    footer = meta.get("footer", "")

    # Derived assets from DESIGN.md
    theme_css = SKILL_DIR / "theme.css"
    mermaid_cfg = SKILL_DIR / "mermaid-config.json"
    mpl_style = SKILL_DIR / "marp-deck.mplstyle"
    gemini_suffix = (SKILL_DIR / "gemini-style.txt").read_text(encoding="utf-8")
    for p in (theme_css, mermaid_cfg, mpl_style):
        if not p.exists():
            print(f"ERROR: {p} missing — run derive_assets.py first",
                  file=sys.stderr); sys.exit(1)

    # Parse source
    slides = parse_source_markdown(source_md)
    print(f"[parse] {len(slides)} slides from {source_md.name}")

    img_dir = deck_dir / "img"
    img_dir.mkdir(exist_ok=True)

    # Plan: list (slide_num, type, generator-fn-closure)
    tasks = []
    for s in slides:
        num = s["num"]
        scfg = cfg.get("slides", {}).get(str(num), {})
        type_ = scfg.get("type", "table")
        if type_ == "mermaid":
            out = img_dir / f"slide-{num:02d}.svg"
            mmd = (deck_dir / scfg["source"]).resolve()
            tasks.append((num, type_, lambda mmd=mmd, out=out:
                          gen_mermaid(mmd, out, mermaid_cfg)))
        elif type_ == "chart":
            out = img_dir / f"slide-{num:02d}.svg"
            py = (deck_dir / scfg["source"]).resolve()
            tasks.append((num, type_, lambda py=py, out=out:
                          gen_chart(py, out, mpl_style)))
        elif type_ == "svg":
            out = img_dir / f"slide-{num:02d}.svg"
            src = (deck_dir / scfg["source"]).resolve()
            tasks.append((num, type_, lambda src=src, out=out:
                          gen_svg_copy(src, out)))
        elif type_ == "gemini":
            out = img_dir / f"slide-{num:02d}.png"
            prompt = scfg["prompt"]
            tasks.append((num, type_, lambda prompt=prompt, out=out:
                          gen_gemini(prompt, out, gemini_suffix=gemini_suffix)))
        # table → no image task

    by_type = lambda t: sum(1 for _, x, _ in tasks if x == t)
    print(f"[plan] {by_type('mermaid')} mermaid · {by_type('chart')} chart · "
          f"{by_type('svg')} svg · {by_type('gemini')} gemini")

    # Execute. Gemini/mermaid/chart in parallel.
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futs = {pool.submit(fn): (num, type_) for num, type_, fn in tasks}
        for f in as_completed(futs):
            num, type_ = futs[f]
            try:
                f.result()
                print(f"  [OK] slide-{num:02d} ({type_})")
            except Exception as e:
                print(f"  [FAIL] slide-{num:02d} ({type_}): {e}")

    # Emit Marp deck
    deck_md = deck_dir / f"{output_basename}.md"
    emit_marp_deck(slides, cfg, img_dir, deck_md, footer)
    print(f"\n[emit] {deck_md}")

    # Report aspect-aware classification (helps spot images that need source rework)
    print("[aspect]")
    for s in slides:
        num = s["num"]
        scfg = cfg.get("slides", {}).get(str(num), {})
        t = scfg.get("type", "table")
        if t not in ("mermaid", "chart", "svg"):
            continue
        p = img_dir / f"slide-{num:02d}.svg"
        ar = get_svg_aspect(p)
        if ar is None:
            continue
        cls = aspect_class(ar) or "default"
        flag = " ← consider source rework" if ar < 0.45 else ""
        extras = []
        if not aspect_class(ar) and density_class(s["content"]):
            extras.append("+left-dense")
        extra = f" [{', '.join(extras)}]" if extras else ""
        print(f"  slide-{num:02d}  aspect={ar:.2f}  → {cls}{extra}{flag}")

    # Render — use absolute paths since cwd is marp install dir
    deck_md_abs = deck_md.resolve()
    theme_abs = theme_css.resolve()
    for fmt in ("pptx", "pdf"):
        out = (deck_dir / f"{output_basename}.{fmt}").resolve()
        # Prefer locally-installed marp-cli; otherwise let `npx` pull the full
        # package name (`marp` alone is not a valid npm package; the actual
        # package is `@marp-team/marp-cli` which registers `marp` as bin).
        win_marp = SKILL_DIR / "node_modules/.bin/marp.cmd"
        nix_marp = SKILL_DIR / "node_modules/.bin/marp"
        if win_marp.exists():
            marp_cmd = [str(win_marp)]
        elif nix_marp.exists():
            marp_cmd = [str(nix_marp)]
        else:
            marp_cmd = ["npx", "--yes", "@marp-team/marp-cli"]
        cmd = [*marp_cmd, "--no-stdin", str(deck_md_abs), "--theme", str(theme_abs),
               f"--{fmt}", "--allow-local-files", "-o", str(out)]
        # Absolute paths are passed to marp, so cwd just needs to be valid.
        r = subprocess.run(cmd, cwd=str(SKILL_DIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print(f"  [{fmt}] {out} ({out.stat().st_size // 1024} KB)")
        else:
            print(f"  [{fmt} ERR] RC={r.returncode}\n--- stderr ---\n{r.stderr}\n--- stdout ---\n{r.stdout}")


if __name__ == "__main__":
    main()
