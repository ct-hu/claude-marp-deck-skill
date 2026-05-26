#!/usr/bin/env python3
"""Derive theme.css / mermaid-config.json / gemini-style.txt / mplstyle from DESIGN.md.

Read DESIGN.md (the single source of truth) and emit the runtime assets
used by build_hybrid.py. Run this once after any DESIGN.md edit; the
emitted files are gitignored — they are always regeneratable.

Usage:
    python3 derive_assets.py [--out DIR]   # default: alongside DESIGN.md
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


def parse_design_md(path: Path) -> dict:
    """Extract the YAML-ish token blocks. Naive: just looks for the known
    fenced ```yaml blocks under each numbered section. We rely on
    DESIGN.md being well-structured; this is not a full YAML parser."""
    text = path.read_text(encoding="utf-8")
    spec: dict = {}

    def block(section_title: str) -> str:
        pat = re.compile(
            rf"## \d+\. {re.escape(section_title)}.*?```yaml\n(.*?)```",
            re.DOTALL,
        )
        m = pat.search(text)
        return m.group(1) if m else ""

    def text_block(section_title: str) -> str:
        pat = re.compile(
            rf"## \d+\. {re.escape(section_title)}.*?```text\n(.*?)```",
            re.DOTALL,
        )
        m = pat.search(text)
        return m.group(1) if m else ""

    # §1 Palette
    palette_block = block("Palette")
    tokens = {}
    for line in palette_block.splitlines():
        m = re.match(r'\s*([\w-]+):\s*"([^"]+)"', line)
        if m:
            tokens[m.group(1)] = m.group(2)
    spec["tokens"] = tokens

    # §2 Typography
    typo_block = block("Typography")
    fonts = {}
    in_fonts = False
    for line in typo_block.splitlines():
        if line.strip().startswith("fonts:"):
            in_fonts = True; continue
        if line.strip().startswith("scale:"):
            in_fonts = False; continue
        if in_fonts:
            m = re.match(r'\s*(\w+):\s*"([^"]+)"', line)
            if m:
                fonts[m.group(1)] = m.group(2)
    spec["fonts"] = fonts

    # §3 Spacing & layout — extract a few key fields by regex
    spec["layout"] = {
        "padding": _extract_str(block("Spacing & layout"), "padding"),
        "grid_gap": _extract_str(block("Spacing & layout"), "gap"),
        "right_img_max_height": _extract_str(block("Spacing & layout"), "right-img-max-height"),
    }

    # §7 Gemini prompt suffix (text block)
    spec["gemini_suffix_template"] = text_block("Gemini prompt suffix (auto-derived)").strip()

    return spec


def _extract_str(blob: str, key: str) -> str:
    m = re.search(rf'\s*{re.escape(key)}:\s*"?([^"\n]+)"?', blob)
    return m.group(1).strip() if m else ""


def subst(template: str, tokens: dict, fonts: dict) -> str:
    """Mustache-ish {{ tokens.x }} / {{ fonts.x }} substitution."""
    def repl(m):
        path = m.group(1).strip()
        scope, key = path.split(".", 1)
        if scope == "tokens":
            return tokens.get(key, m.group(0))
        if scope == "fonts":
            return fonts.get(key, m.group(0))
        return m.group(0)
    return re.sub(r"\{\{\s*([\w.-]+)\s*\}\}", repl, template)


def emit_theme_css(spec: dict, out: Path) -> None:
    t = spec["tokens"]
    f = spec["fonts"]
    css = f"""/* @theme marp-deck */
/* AUTO-GENERATED from DESIGN.md — do not edit by hand. */
@import 'default';

:root {{
  --color-fg: {t['fg']};
  --color-bg: {t['bg']};
  --color-accent: {t['accent-primary']};
  --color-warn: {t['accent-warn']};
  --color-positive: {t['accent-positive']};
  --color-muted: {t['muted']};
  --color-border: {t['border-subtle']};
  --color-code-bg: {t['code-bg']};
}}

section {{
  background: var(--color-bg);
  color: var(--color-fg);
  font-family: {f['body']};
  font-size: 20px;
  padding: 44px 64px 52px 64px;
  line-height: 1.5;
}}

h1 {{
  font-family: {f['display']};
  font-size: 38px;
  font-weight: 800;
  line-height: 1.15;
  margin: 0 0 14px 0;
  border-bottom: 2px solid var(--color-accent);
  padding-bottom: 8px;
}}
h2 {{ font-family: {f['display']}; font-size: 23px; color: var(--color-accent); font-weight: 700; margin: 10px 0 4px; }}
h3 {{ font-family: {f['display']}; font-size: 19px; font-weight: 700; margin: 8px 0 4px; }}

strong {{ color: var(--color-accent); }}

ul, ol {{ padding-left: 24px; margin: 6px 0; }}
li {{ margin-bottom: 4px; font-size: 18px; line-height: 1.45; }}

p {{ margin: 6px 0; }}

/* Chapter prefix (v1.5) — small mono uppercase label above H1,
 * "— CHAPTER 02 · GETTING STARTED" style. Optional via source field. */
.chapter-prefix {{
  font-family: {f['mono']};
  font-size: 14px;
  letter-spacing: 0.12em;
  color: var(--color-accent);
  text-transform: uppercase;
  margin: 0 0 14px 0;
  font-weight: 500;
}}
.chapter-prefix::before {{
  content: "— ";
}}

table {{
  width: 100%; border-collapse: collapse;
  font-size: 16px; margin: 8px 0;
}}
th {{
  background: var(--color-accent); color: white;
  padding: 6px 10px; text-align: left; font-weight: 600;
}}
td {{
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}}
tr:nth-child(even) td {{ background: #F2EDDF; }}  /* warm-tinted alt row */

/* Inline code: subtle on warm bg, slight tint. */
code {{
  background: #EFE7D2; padding: 2px 6px; border-radius: 3px;
  font-family: {f['mono']}; font-size: 0.88em;
  color: var(--color-fg);
}}

/* Code blocks: build_hybrid.py transforms ```fenced``` source into
 * <div class="codeblock"> to bypass Marp's marp-pre auto-scaling, which
 * silently shrinks fonts when a single line overflows.
 *
 * v1.5 — dark code block style (Tier 1 visual refresh):
 *   - dark #1F2329 bg with light cream text (high contrast on warm slide bg)
 *   - rounded corners, no left accent bar (looks more like terminal)
 *   - bigger font (13 → 15) so code is genuinely readable */
pre, .codeblock {{
  background: #1F2329;
  color: {t['code-fg']};
  padding: 14px 18px;
  border-radius: 8px;
  font-family: {f['mono']};
  font-size: 14px; line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  overflow: hidden;
  margin: 8px 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
pre code {{ background: transparent; padding: 0; color: inherit; }}

blockquote {{
  border-left: 4px solid var(--color-muted);
  background: #F2EDDF;
  padding: 10px 16px; margin: 10px 0;
  font-style: italic; color: var(--color-muted);
  font-size: 17px;
}}

/* Two-column slide grid: left text + right image (v1.1 — image-emphasised) */
.slide-grid {{
  display: grid;
  grid-template-columns: 38% 62%;
  gap: 24px;
  align-items: start;
  width: 100%;
}}
.left-col {{ overflow: hidden; min-width: 0; }}
.right-col {{
  display: flex;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
}}
.right-col img {{
  width: 100%; max-width: 100%;
  max-height: 65vh;
  object-fit: contain;
  display: block;
}}

/* Aspect-aware grid override (v1.3) — build_hybrid.py reads each SVG's
 * viewBox and adds img-very-tall / img-tall / img-wide to .slide-grid so
 * the column split matches the image's natural shape. Without this, a
 * tall mermaid (e.g. flowchart TD chain, sequence diagram) gets shrunk
 * to fit a wide right-col, leaving text unreadably small. */
.slide-grid.img-very-tall {{   /* aspect < 0.50 */
  grid-template-columns: 65% 35%;
}}
.slide-grid.img-very-tall .right-col img {{ max-height: 82vh; }}

.slide-grid.img-tall {{        /* 0.50 ≤ aspect < 0.90 */
  grid-template-columns: 50% 50%;
}}
.slide-grid.img-tall .right-col img {{ max-height: 78vh; }}

.slide-grid.img-wide {{        /* aspect > 1.80 */
  grid-template-columns: 30% 70%;
}}
.slide-grid.img-wide .right-col img {{ max-height: 72vh; }}

/* Density-aware widening: when left-col content has a code block or many
 * lines AND image aspect is default (no img-tall/wide class), narrow the
 * right-col from 62% → 55%. Default-aspect images are height-bound at
 * max-h:65vh, so this reclaims the unused horizontal space for text
 * without shrinking the image. */
.slide-grid.left-dense {{
  grid-template-columns: 45% 55%;
}}

/* Section: anchor content to TOP (override Marp's default justify-content:center),
 * use margin-top:auto on the design-rationale callout to push it to the bottom
 * while still keeping everything else flowing from the top. */
section {{
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  overflow: hidden;
}}
.slide-grid {{
  flex: 0 1 auto;
}}
.callout.design-rationale {{
  margin-top: auto;  /* push to slide bottom */
}}
/* Cover keeps its vertical centering. */
section.cover {{
  justify-content: center;
}}

section.cover h1 {{
  font-size: 52px;
  font-weight: 800;
  line-height: 1.05;
  border: none;
  padding: 0;
  margin-bottom: 22px;
}}
section.cover {{ padding: 90px 80px 64px 80px; }}
section.cover .subtitle {{ font-size: 22px; font-style: normal; color: var(--color-fg); }}
/* Cover tagline — em-dash 後半段，視覺上是 H1 的延續但語意 / metadata 獨立 */
section.cover .cover-tagline {{
  font-size: 32px;
  font-weight: 500;
  color: var(--color-fg);
  margin: -8px 0 18px 0;
  line-height: 1.2;
}}

/* Footer + page number — small mono on muted color (v1.5) */
footer {{
  font-family: {f['mono']};
  font-size: 13px;
  letter-spacing: 0.08em;
  color: var(--color-muted);
  text-transform: uppercase;
}}
section::after {{
  font-family: {f['mono']};
  font-size: 13px;
  color: var(--color-muted);
}}

/* Subtitle (副標) — slim lede under H1, before main content */
.subtitle {{
  font-size: 17px;
  font-weight: 400;
  color: var(--color-muted);
  margin: -2px 0 14px 0;
  line-height: 1.4;
  font-style: italic;
}}

/* Callout strips (v1.2) — bottom-of-slide design rationale + warnings */
.callout {{
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 15px;
  line-height: 1.45;
}}
.callout-label {{
  font-weight: 700;
  display: inline-block;
  margin-right: 8px;
}}

.callout.design-rationale {{
  background: #1A2540;
  color: #E5E7EB;
  margin-bottom: 30px;  /* clearance for footer text + page number below */
}}
.callout.design-rationale .callout-label {{ color: #93C5FD; }}

.callout.key-concept {{
  background: #EFF6FF;
  border-left: 4px solid var(--color-accent);
  color: var(--color-fg);
}}
.callout.key-concept .callout-label {{ color: var(--color-accent); }}

.callout.anti-pattern {{
  background: #FEF2F2;
  border-left: 4px solid var(--color-warn);
  color: var(--color-fg);
}}
.callout.anti-pattern .callout-label {{ color: var(--color-warn); }}

.callout.observation {{
  background: #F0FDF4;
  border-left: 4px solid var(--color-positive);
  color: var(--color-fg);
}}
.callout.observation .callout-label {{ color: var(--color-positive); }}
"""
    out.write_text(css, encoding="utf-8")


def emit_mermaid_config(spec: dict, out: Path) -> None:
    t = spec["tokens"]; f = spec["fonts"]
    # edgeLabelBackground is set explicitly to the warm slide bg — without
    # this, Mermaid derives the edge label bg from secondaryColor and we end
    # up with dark text on dark bg (invisible). tertiaryTextColor covers
    # cluster / subgraph label text for the same readability reason.
    cfg = {
        "theme": "base",
        "themeVariables": {
            "fontFamily": f["body"],
            "fontSize": "22px",
            "primaryColor": t["accent-primary"],
            "primaryTextColor": t["fg"],
            "primaryBorderColor": t["fg"],
            "lineColor": t["fg"],
            "secondaryColor": t["code-bg"],
            "tertiaryColor": t["bg"],
            "tertiaryTextColor": t["fg"],
            "edgeLabelBackground": t["bg"],
            "actorBkg": t["accent-primary"],
            "actorTextColor": t["bg"],
            "actorLineColor": t["fg"],
            "noteBkgColor": "#FAFAFA",
            "noteTextColor": t["fg"],
            "noteBorderColor": t["muted"],
            "signalColor": t["accent-primary"],
            "signalTextColor": t["fg"],
            "clusterBkg": t["bg"],
            "clusterBorder": t["border-subtle"],
        },
        # mermaid-cli 11 hardcodes sequence actor/message labels to 16px and
        # ignores sequence.*FontSize — themeCSS with !important is the only lever.
        # Modest 20/18 so labels still fit the boxes mermaid sized at 16px.
        "themeCSS": (
            ".actor, .actor tspan { font-size: 20px !important; } "
            ".messageText { font-size: 18px !important; } "
            ".noteText, .noteText tspan { font-size: 16px !important; }"
        ),
    }
    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def emit_gemini_suffix(spec: dict, out: Path) -> None:
    template = spec["gemini_suffix_template"]
    rendered = subst(template, spec["tokens"], spec["fonts"])
    out.write_text(rendered + "\n", encoding="utf-8")


def emit_mpl_style(spec: dict, out: Path) -> None:
    t = spec["tokens"]; f = spec["fonts"]
    # Strip leading '#' — matplotlib style files treat # as comment marker.
    bare = lambda hex_: hex_.lstrip("#")
    # Font stack: matplotlib picks ONE font (not character-level fallback), so a
    # CJK-capable font must be FIRST. matplotlib walks the list and takes the
    # first one actually registered on the host, so we list every common CJK
    # family across Linux / Windows / macOS — whichever exists wins.
    # Han codepoints are identical across regional variants; we just need *any*
    # CJK-capable font to be available.
    cjk_first = [
        # Linux (Noto CJK ttc — one variant gets registered per family name)
        "Noto Sans CJK JP", "Noto Sans CJK TC", "Noto Sans CJK SC",
        # Windows (preinstalled since Win 7+)
        "Microsoft JhengHei", "Microsoft YaHei",
        # macOS
        "PingFang TC", "PingFang SC", "Heiti TC", "Hiragino Sans GB",
        # Standalone Noto (some distros / Win installs without CJK ttc)
        "Noto Sans TC", "Noto Sans SC", "Noto Sans HK", "Noto Sans JP",
        # Older Windows fallback
        "SimHei", "SimSun",
        # Linux fallback
        "Droid Sans Fallback",
    ]
    families = [s.strip() for s in f["body"].split(",")]
    seen = set()
    full = []
    for fam in cjk_first + families:
        if fam not in seen:
            full.append(fam); seen.add(fam)
    sans_stack = ", ".join(full)
    # Note on sizing: charts are rendered as SVG via matplotlib then scaled
    # to fit a ~793×561px Marp right-column. matplotlib default figsize
    # 14×9 inches produces a wide SVG that gets aggressively downscaled, so
    # the effective on-screen font size is half what's specified here. We
    # bump font sizes aggressively to compensate. Chart scripts should use
    # figsize=(10, 6.5) to keep aspect close to right-col proportions.
    style = f"""# AUTO-GENERATED from DESIGN.md — do not edit by hand.
figure.facecolor: {bare(t['bg'])}
axes.facecolor: {bare(t['bg'])}
axes.edgecolor: {bare(t['fg'])}
axes.labelcolor: {bare(t['fg'])}
axes.titlesize: 24
axes.titleweight: bold
axes.labelsize: 20
xtick.labelsize: 17
ytick.labelsize: 17
legend.fontsize: 16
axes.spines.top: False
axes.spines.right: False
grid.color: {bare(t['border-subtle'])}
grid.alpha: 0.25
font.family: sans-serif
font.sans-serif: {sans_stack}
axes.prop_cycle: cycler('color', ['{bare(t['accent-primary'])}', '{bare(t['muted'])}', '{bare(t['accent-warn'])}', '{bare(t['accent-positive'])}'])
lines.linewidth: 2.8
axes.unicode_minus: False
"""
    out.write_text(style, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default=None, type=Path,
                    help="path to DESIGN.md (default: alongside this script)")
    ap.add_argument("--out", default=None, type=Path,
                    help="output dir (default: alongside DESIGN.md)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    design = args.design or (here / "DESIGN.md")
    out = args.out or here

    if not design.exists():
        print(f"ERROR: {design} not found", file=sys.stderr); sys.exit(1)

    spec = parse_design_md(design)
    if not spec.get("tokens"):
        print("ERROR: no palette tokens parsed from DESIGN.md", file=sys.stderr); sys.exit(1)

    print(f"[derive] DESIGN.md → {len(spec['tokens'])} tokens, "
          f"{len(spec['fonts'])} font slots")

    emit_theme_css(spec, out / "theme.css")
    emit_mermaid_config(spec, out / "mermaid-config.json")
    emit_gemini_suffix(spec, out / "gemini-style.txt")
    emit_mpl_style(spec, out / "marp-deck.mplstyle")

    print(f"[emit] {out / 'theme.css'}")
    print(f"[emit] {out / 'mermaid-config.json'}")
    print(f"[emit] {out / 'gemini-style.txt'}")
    print(f"[emit] {out / 'marp-deck.mplstyle'}")


if __name__ == "__main__":
    main()
