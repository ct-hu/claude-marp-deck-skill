# marp-deck design system v1

**單一真理源**。所有衍生 asset（theme.css / mermaid-config.json /
gemini-style suffix / matplotlib style）都從這份檔案產出。改色票
/ 字型只動這裡，跑 `derive_assets.py` 重生其他檔案。

> 為什麼需要：repo 內舊版做法是把規範散在 SKILL.md「簡報模板規範」+
> 各 slide outline 頂部 + theme.css + Gemini prompts 五個地方，導
> 致改一個地方其他四個忘記改、生成的 deck 風格漂移（slide 1 跟 slide
> 12 像兩份不同 deck）。DESIGN.md 集中之後，每份 deck 第一次生出來
> 就會落在同一個視覺語言裡。

---

## 1. Palette

```yaml
# 色票 — 所有衍生 asset 必須引用這些 token，不得 hard-code hex
tokens:
  fg: "#1A1A1A"               # primary text — 比純黑柔一些（搭暖底）
  bg: "#FAF6EE"               # slide background — 暖米色（v1.5）
  accent-primary: "#D9633E"   # 單一暖珊瑚橘（v1.5，原 #2563EB 藍）
  accent-warn: "#B82E2E"      # 警示 / 代價 — 深紅（搭暖底）
  accent-positive: "#3F7F4C"  # success / 適用場景 — 深綠（搭暖底）
  muted: "#6B6258"            # secondary text — 暖灰
  border-subtle: "#E5DDC9"    # 表格 hairline — 暖灰
  code-bg: "#1F2329"          # code block background — 深色（v1.5）
  code-fg: "#E8E2D3"          # code text on dark bg

# 不在這份清單上的顏色，禁止直接出現在任何衍生檔內
```

## 2. Typography

```yaml
fonts:
  display: "Inter Tight, Noto Sans TC, sans-serif"
  body:    "Inter, Noto Sans TC, sans-serif"
  mono:    "JetBrains Mono, Consolas, monospace"

scale:            # v1.5 — Tier 1 視覺更新（參考 Playwright deck）
  title-h1: 44px         # was 28（cover 72）
  h2: 26px               # was 20
  h3: 20px               # was 17
  body: 22px             # was 18
  li: 19px               # was 16
  subtitle: 17px         # was 15
  small: 14px
  code: 15px             # was 12-13
  chapter: 14px          # 新：— CHAPTER NN · TOPIC 等寬大寫小字
```

## 3. Spacing & layout

```yaml
slide:
  aspect: "16:9"        # 1280 × 720 logical
  padding: "56px 80px 64px 80px"  # v1.5 — 更寬鬆 breathing room

grid:
  default: "left-text 38% / right-image 62%"  # v2 — 圖更顯眼、字更大空間
  gap: 24px
  align-items: "start"   # 對齊頂部，避免內容垂直置中時頂端溢出蓋到 title
  right-img-max-height: "78vh"  # 圖佔更多垂直空間

# v1.3 — aspect-aware override：build_hybrid.py 偵測 SVG viewBox 寬高比、
# 自動加 class 讓 grid 跟圖的自然形狀匹配。不加會發生「TD flowchart 在寬
# right-col 裡被縮成很窄、內部文字小到看不到」這種事。
aspect_bands:
  very-tall: { threshold: "<0.50",        grid: "65% / 35%", max-h: "82vh", class: "img-very-tall" }
  tall:      { threshold: "0.50 - 0.90",  grid: "50% / 50%", max-h: "78vh", class: "img-tall" }
  default:   { threshold: "0.90 - 1.80",  grid: "38% / 62%", max-h: "65vh", class: "" }
  wide:      { threshold: ">1.80",        grid: "30% / 70%", max-h: "72vh", class: "img-wide" }
  # 注意：1.50-1.80 不算 wide。chart aspect ~1.55 在 default 38/62 已 width-bound，
  # 縮窄左欄反而擠壓 callout、撞 footer。只把真正寬扁的圖（2:1 panoramic 以上）走 wide。

aspect_warnings:
  - "aspect < 0.45：CSS 救不回來、考慮改 mermaid 來源（TD → LR）或改 hand-SVG"

# v1.4 — density-aware widening：左欄內容有 code block 或 > 14 行、且圖
# aspect 是 default（沒 img-tall/wide class）時，把右欄收窄 62% → 55%。
# default 圖在 max-h:65vh 通常是 height-bound、右欄有 13% 橫向空間沒用
# 到，挪給文字左欄可以放大字 / 不擠 wrap，但圖實際大小不變。
density_class:
  trigger: "left-col has ``` block OR > 14 lines"
  effect: "narrow right-col 62% → 55%, left-col gets +19% width"
  not_applied_when: "aspect class already adjusted grid (img-tall / img-wide / img-very-tall)"

table-only-slides:
  layout: "full-width"   # 沒右圖，表格滿版
  examples: "對照表 / 數據總表 / cost matrix"
```

## 4. 工具選擇樹

每張 slide 對應視覺要走哪個工具，**這份 mapping 是 deterministic 的**：

| 視覺型態 | 工具 | 理由 |
|---|---|---|
| **sequence / handshake / timeline / drop** | Mermaid `sequenceDiagram` | 文字真實、0 typo、source 可 diff |
| **flowchart ≤ 7 nodes** | Mermaid `flowchart TD` | 同上 |
| **line chart with axes + annotations** | matplotlib | 精確控制 axis 數字 |
| **scenario cards / icon collage / 多 icon 場景** | Gemini Flash | 裝飾性、Gemini 強項 |
| **balance scale / cover decoration** | Gemini Flash | 同上 |
| **structure diagram (datagram / sliding window snapshots)** | Gemini Flash（暫時）→ 未來改 hand-SVG | 需要精確空間關係 |
| **對照表 / 數據總表** | Marp native table | 已是文字、滿版 |

**不要在同一張 slide 混用兩種視覺型態**（時間軸 + 表格 → 擁擠）。

## 5. Mermaid theme (auto-derived)

```yaml
# derive_assets.py 會把這段寫進 mermaid-config.json
mermaid:
  theme: "base"
  variables:
    fontFamily: "{{ fonts.body }}"
    fontSize: "22px"        # v2 — 18 → 22，投影機上看得清
    primaryColor: "{{ tokens.accent-primary }}"
    primaryTextColor: "{{ tokens.fg }}"
    primaryBorderColor: "{{ tokens.fg }}"
    lineColor: "{{ tokens.fg }}"
    secondaryColor: "{{ tokens.code-bg }}"
    actorBkg: "{{ tokens.accent-primary }}"
    actorTextColor: "{{ tokens.bg }}"
    noteBkgColor: "#FAFAFA"
    noteBorderColor: "{{ tokens.muted }}"
    signalColor: "{{ tokens.accent-primary }}"
  # mermaid-cli 11 把 sequence actor/message 寫死 16px、忽略 sequence.*FontSize，
  # 只能靠 themeCSS !important 拉大（保守 20/18、避免撐爆 box）。derive_assets emit：
  themeCSS: ".actor{font-size:20px!important} .messageText{font-size:18px!important} .noteText{font-size:16px!important}"
```

## 6. matplotlib style (auto-derived)

```yaml
# derive_assets.py 會 emit marp-deck.mplstyle
matplotlib:
  figure.facecolor: "{{ tokens.bg }}"
  axes.facecolor: "{{ tokens.bg }}"
  axes.edgecolor: "{{ tokens.fg }}"
  axes.labelcolor: "{{ tokens.fg }}"
  axes.titlesize: 19       # v2 — 15 → 19
  axes.titleweight: bold
  axes.labelsize: 17       # v2 — 軸標籤大幅放大
  xtick.labelsize: 14
  ytick.labelsize: 14
  legend.fontsize: 14
  axes.spines.top: False
  axes.spines.right: False
  grid.color: "{{ tokens.border-subtle }}"
  grid.alpha: 0.25
  font.family: "{{ fonts.body }}"
  axes.prop_cycle: "cycler(color=['{{ tokens.accent-primary }}', '{{ tokens.muted }}', '{{ tokens.accent-warn }}', '{{ tokens.accent-positive }}'])"
```

## 7. Gemini prompt suffix (auto-derived)

```text
# 所有 Gemini Flash image gen 都接這段、不再 per-slide 重寫

Style: polished flat 2D vector technical illustration on pure white
(#FFFFFF) background. Thin black outlines, solid color fills only.
Palette: blue {{ tokens.accent-primary }} for primary/active elements,
red {{ tokens.accent-warn }} for failures/costs/warnings, green
{{ tokens.accent-positive }} for success/positive states, gray
{{ tokens.muted }} for secondary/passive elements. No gradients, no 3D,
no photography, no decorative icons unrelated to the subject. Aspect
ratio 3:2, diagram fills the canvas with comfortable margins.

Labels — PROMINENT and legible for projector viewing at 6m distance.
Use BIG bold sans-serif text (Inter / Noto Sans TC equivalent), not tiny captions.

Language — describe in Traditional Chinese (繁體中文); keep technical
terms / proper nouns / variable names / acronyms in English.
Examples:
  ✓ "代價：1 RTT setup"             (Chinese description + English term)
  ✓ "TCP connection · 4-tuple 識別"
  ✓ "stream A：seq=100..200 卡住"
  ✗ "cost: 1 RTT before first data" (all English — DO NOT do this)
  ✗ "傳輸控制協定握手"               (translated proper noun — DO NOT)

Keep these English: TCP, UDP, QUIC, ACK, SYN, HOL, BDP, RTT, CWND,
sliding window, slow start, AIMD, handshake, stream, packet, datagram,
seq=NNN, src_ip, dst_port, etc.
```

## 8. Anti-patterns (硬性禁止)

從 v1 → v3 三輪 iteration + 試做 deck 觀察的踩雷清單。生成前 grep
這些字眼 / 行為，**有就退回去改 prompt 或 source markdown**：

```yaml
anti_patterns:
  - "副標題（subtitle）"          # 浪費版面、增加擁擠感
  - "callout quote box（引用塊）" # 同上
  - "3D 效果 / gradient / drop shadow / glassmorphism"
  - "purple gradient on white"   # AI 通用 cliche
  - "Inter / Roboto / Arial 當 display 字"  # 太通用，改用 Inter Tight
  - "generic AI icon collage"    # 一堆無關 icon 堆疊
  - "圖內字超過 5 個 label"      # 改用 Mermaid 或 SVG
  - "同張 slide 混用兩種視覺型態"
  - "raw <svg> embed in Marp"    # Marp 不解析 inline SVG，會以 raw text 渲染

# 中文用語
chinese_phrasing:
  - "「帶走的 N 件事」"          # 英文 "key takeaways" 直譯、不自然。改用「重點回顧」
  - "「真相」「正解」"           # 像在判對錯，過於武斷。改用「實際運作」「常見作法」
  - 純中文翻譯專有名詞           # 例：「傳輸控制協定」→ 保留 TCP；「握手」→ 保留 handshake 或寫「handshake (握手)」
```

## 9. Source markdown 寫法（搭配新 pipeline）

```yaml
# source-NN-topic.md 不再需要重寫「簡報模板規範」section
required:
  - "## Slide N: 標題" 章節分隔
  - "**標題：**" — 主標題（大字）
  - "**內容：**" — slide 左 col body（現況；可長）
  - "**視覺：**" — 圖描述（給 image gen / hand-SVG 參考、不渲染）
optional (新增於 v1.2):
  - "**副標：**" — 標題下方 1-2 行精煉 lede（"為什麼這頁存在"）
  - "**設計理由：**" — slide 底部深色 callout strip（"核心觀念"、"為什麼這樣設計"）
  - "**核心觀念：**" — 藍色 callout box（"記住這一句"）
  - "**Anti-pattern：**" — 紅色 callout box（"千萬不要踩這個雷"）
optional (新增於 v1.5):
  - "**章節：**" — 標題上方等寬大寫小字「— CHAPTER 02 · GETTING STARTED」，建立 narrative 結構
forbidden:
  - "簡報模板規範" section（pipeline 自動套用 DESIGN.md）
  - hard-code 顏色 hex（用 token 名稱，例：accent-primary）
  - "Image gen prompt prefix" section（pipeline 自動套用 §7）
```

### 副標寫法準則（v1.2 新增）

借鑑 Reference deck 的觀察：副標是「為什麼這頁存在」的 1 句話，**不是**標題的同義詞延伸。

| ✓ 好的副標 | ✗ 不好的副標 |
|---|---|
| 「為什麼從 UDP 起點？因為 TCP 改不動」 | 「TCP 的痛點」（跟標題重複）|
| 「觀念導正：autoconnect 是允許列表而非開關」 | 「autoconnect 設定」（沒資訊量）|
| 「兩套獨立運作的 Scouting 機制」 | 「Scouting 機制詳解」（一樣是描述標題）|

副標長度建議 1-2 行、每行 15-25 個字。

### 設計理由（design rationale）寫法準則

放 slide 底部深色 strip。承載「**為什麼這樣設計**」的元層級資訊。Reference deck 範例：
- 「為什麼 via_router_only 仍保留 multicast 直連？因為同網段物理距離最近、直連能保證最低延遲與節省 Router 頻寬。」

跟「內容」差別：內容是 **what / how**，設計理由是 **why**。

## 10. Refero 借鑑

styles.refero.design 免費 gallery 是**靈感來源**，不是直接餵 agent：

- **拿什麼**：typography 搭配、spacing 節奏、layout idea
- **不拿什麼**：配色（用我們自己的 §1）、品牌 logo
- 不需要訂閱 Pro / MCP

當前參考的設計語言：**Linear-ish 乾淨技術感**（深 vs 淺對比、generous whitespace、hairline rules）。

---

## 11. Callout palette (v1.2 新增)

借鑑 reference deck（Zenoh 跨網段選路 deck）的設計慣例，新增 4 種底部 callout strip：

```yaml
callout_styles:
  design-rationale:
    bg: "#1A2540"          # 深 navy
    text: "#E5E7EB"        # 淺灰白字
    用途: "為什麼這樣設計 — 元層級的 why"
    位置: slide 最底部、深色 strip
  key-concept:
    bg: "#EFF6FF"          # 淡藍
    border: "#2563EB"      # accent-primary
    text: "#0A0A0A"
    用途: "記住這一句 — 核心觀念框"
  anti-pattern:
    bg: "#FEF2F2"          # 淡紅
    border: "#DC2626"      # accent-warn
    text: "#0A0A0A"
    用途: "千萬不要踩 — 警示框（圖示 ⚠️）"
  observation:
    bg: "#F0FDF4"          # 淡綠
    border: "#16A34A"      # accent-positive
    text: "#0A0A0A"
    用途: "觀察 / 結論 / 實測結果"
```

每張 slide 最多用 1 個 callout（多用會稀釋重點）。

## 12. Shape vocabulary（形狀辭典，v1.2 新增）

借鑑 reference deck 的形狀語意，所有 hand-SVG / Mermaid 應該對齊：

```yaml
shape_meaning:
  hexagon "⬡":   peer / actor / endpoint    # 自治節點
  rectangle "▭": router / server / infrastructure  # 基礎建設
  circle "⬤":   client / lightweight node   # 輕量端點
  rounded_rect: container / scope / network # 群組、scope
  trapezoid:    天平盤 / 對照組             # 抽象比較
  diamond:      decision point              # 決策點
  red_X:        failure / dropped / killed  # 故障標記
  green_check:  success / active / healthy  # 成功標記
```

未來新寫 SVG 對齊這套詞彙，跨 deck 視覺一致。

## Changelog

- **v1 (2026-05-13)**：首版。把散在 SKILL.md / 各 source markdown / build.py 的設計規範集中
- **v1.1 (2026-05-13)**：tune iteration 1：
  - grid 45/55 → 38/62（圖更顯眼）
  - Mermaid fontSize 18 → 22（投影機可讀）
  - matplotlib title 15 → 19、軸標 13 → 17
  - Gemini prompt 加「中文描述 + 英文專有名詞」+「PROMINENT projector-legible labels」
  - 新 anti-pattern §8「中文用語」：避「帶走的」、避「真相 / 正解」、避純中文翻譯專有名詞
- **v1.2 (2026-05-13)**：tune iteration 2（借鑑 reference deck）：
  - source markdown 新增 optional 段：「副標」「設計理由」「核心觀念」「Anti-pattern」
  - §11 加 4 種 callout style（design-rationale / key-concept / anti-pattern / observation）
  - §12 加形狀辭典（hexagon = peer、rectangle = router、circle = client、…）
  - matplotlib title 19 → 24、labelsize 17 → 20（更應對 SVG 縮放）
- **v1.3 (2026-05-14)**：aspect-aware grid。build_hybrid.py 偵測 SVG viewBox
  寬高比，自動套 img-very-tall / img-tall / img-wide class，避免 tall flowchart
  在 38/62 grid 被縮成窄條、字小到看不到。aspect < 0.45 時 build 印警告
  建議改源頭（TD→LR、改 hand-SVG 等）— CSS 對極端 aspect 救不太回來。
- **v1.4 (2026-05-14)**：density-aware widening。左欄有 code block / > 14 行
  且圖是 default aspect 時、自動把右欄 62% → 55%，左欄拿到多 19% 寬給文字。
  圖實際大小不變（default 圖 height-bound、右欄有 13% 橫向空間沒用到）。
- **v1.5 (2026-05-14)**：Tier 1 視覺更新（參考 Playwright Test Runner 教學
  deck 的 Claude Design 風格）：
  - 背景 #FFFFFF → 暖米 #FAF6EE、accent 藍 → 暖珊瑚橘 #D9633E
  - Code block 淺灰底 → 深色 #1F2329（搭暖底對比強、code 變美學主角）
  - 字級大幅放大：H1 28→44（cover 44→72）、body 18→22、li 16→19、code 12-13→15
  - Padding 40/56 → 56/80（generous breathing room）
  - 新增 optional 段「章節」— H1 上方等寬大寫小字 narrative anchor
