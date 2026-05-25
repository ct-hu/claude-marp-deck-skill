---
name: marp-deck
description: 把 5 段式 markdown + deck.toml 變成投影片 .pptx / .pdf 的 pipeline。自己 render mermaid / matplotlib chart / 手刻 SVG → Marp 排版 → Chrome headless 出檔。中文不亂、跨 deck 視覺一致、aspect-aware grid 自動處理圖片形狀差異。當使用者說「把這份 md 變成簡報」、「用這個 outline 出 deck」、「Marp 做投影片」、「中文簡報生成」時觸發。
---

# marp-deck — markdown → 簡報

把 5 段式 markdown source + `deck.toml` mapping 轉成投影片：

```
source.md + deck.toml
   ↓
build_hybrid.py
   ├─ Mermaid (.mmd) → SVG
   ├─ matplotlib script (.py) → SVG
   ├─ hand-written SVG → copy
   └─ Marp native table
   ↓
Marp markdown deck.md
   ↓
Chrome headless
   ↓
deck.pptx + deck.pdf
```

跟「直接交給 NotebookLM / Gemini 生圖生 slide」相比，差別：
- **中文 0 hallucinate**（自己 render、不靠 LLM 生圖文）
- **跨 deck 視覺一致**（單一 DESIGN.md 真理源）
- **source-controlled**（mermaid / chart / SVG 都是文字檔可 diff）

## 觸發情境

- 「把這份 markdown 變成簡報」
- 「用這個 outline 出 deck」
- 「Marp 做投影片」
- 「中文技術簡報生成」
- 上游 skill（如 `notebooklm-marp-deck`）研究完、要進「生成簡報」階段時呼叫

## 必備工具

- Python 3.11+（`tomllib` 內建）；fallback 用 `pip install tomli`
- Node.js + `npx marp-cli` + `mmdc`（mermaid-cli）— skill 內可 `npm install` 本地裝（build_hybrid.py 會優先用 local `node_modules/.bin/mmdc`），或全域 `npm install -g @marp-team/marp-cli @mermaid-js/mermaid-cli`
- matplotlib + 字型 `Noto Sans CJK JP`（apt: `fonts-noto-cjk`） — 中文圖表才不會方塊
- Chrome / Chromium — marp-cli 跑 headless 出 PDF / PPTX

## 0a. Content verification — 寫前 fact-check（必做）

> **🔴 LLM-generated 內容對「版本 / 預設值 / API / 配置語法 / 具體數據」
> 系統性不可靠。**任何「version X+ 才支援 Y」「default = Z」「config 寫法
> 是這樣」「實測 N×」這種陳述、**寫進 source.md 前必須核實**。

### 哪些陳述要 fact-check

| 類別 | 例子 | 風險 |
|---|---|---|
| 版本支援邊界 | 「Zenoh 1.5+ 才支援 QUIC」「TLS 1.3 從 OpenSSL 1.1.1 起」 | LLM 常常猜錯版本號（高） |
| 預設值 | 「CongestionControl 預設 BLOCK」「TCP cwnd 初始 = 10 MSS」 | LLM 常記錯（高） |
| Config 語法 | TOML vs JSON / table vs array of strings / key 名 | LLM 容易混淆語法（高） |
| API 簽名 | 「`Session::declare_publisher(key, qos)` 接這幾個參數」 | LLM hallucinate 參數（中-高）|
| 具體數據 | 「20% 丟包 QUIC 吞吐 4.6× TCP」 | 來源不明的精確數字（高） |
| RFC 引用 | 「RFC 9000 §17.2 定義 connection_id 0-20 bytes」 | RFC 章節號常引錯（中）|
| Spec 細節 | 「stream_id bit 0 = initiator」「QUIC long header 第一 bit = 1」 | 細節易記錯（中） |

### 怎麼核實（三邊驗證）

對每個 fact-check-able 陳述、走至少**兩個**獨立來源：

| 來源 | 怎麼查 | 例子 |
|---|---|---|
| 官方 docs / 部落格 | `WebFetch` 該專案 docs.rs / readthedocs / official site / 官方 blog release notes | `https://zenoh.io/docs/manual/quic/`、`zenoh.io/blog/...` |
| 標準文件 | `WebFetch` RFC、IETF spec | `datatracker.ietf.org/doc/html/rfc9000` |
| 本機原始碼 / stub | 讀 `.pyi` / source / config schema | `~/.local/lib/python3.10/site-packages/zenoh/__init__.pyi` |
| 實測 | 跑 minimal code 看實際行為 | `pub = sess.declare_publisher(...); print(pub.reliability)` |

**驗證一致才能寫進 source.md**。寫的時候在 markdown 留 trace 註解：
```
<!-- verified: zenoh.io/docs/manual/quic/ + 1.9.0 release blog (2026-04-16) -->
```

### 不能核實的處理

若多查不確定、就**改成保守陳述**：

| ❌ 不可靠 | ✅ 保守 |
|---|---|
| 「20% 丟包 QUIC 吞吐 4.6× TCP」 | 「高丟包下 QUIC 吞吐優於 TCP、具體比例視場景跟 CC 演算法」 |
| 「Zenoh 1.5+ 支援 QUIC」 | 「Zenoh 從早期就支援 QUIC、1.9+ 加 multistream」 |
| 「QUIC 比 TCP 快」 | 「QUIC 在 lossy / 高 RTT / mobile 場景有優勢；穩定有線 TCP 略勝」 |

寧可保守準確、不要精確但錯。

### 過去地雷紀錄

- ❌ **「Zenoh 1.5+ 支援 QUIC」（真相：基本 QUIC 從 Zenoh 早期就有、1.5 加 datagram、1.9 加 multistream）**
- ❌ **Zenoh config `[[listen.endpoints]] tcp = "..."`（真相：JSON5 array of strings `endpoints: ["tcp/host:port"]`）**
- ❌ **「Zenoh CongestionControl 預設 BLOCK」（真相：實測 + Rust docs 都是 DROP）**

不重複踩。每寫一個 deck、把這頁的「fact-check 過的陳述」列在 commit message。

## 0. Per-slide content planning（寫 markdown 前先規劃）

寫 source markdown **不是**把材料塞進 5 段式格子就完工。每張 slide 是「內容
密度 × 視覺類型 × 預期 aspect × layout 分配」的組合 — 沒先想過就會生出
半空白頁、或者「右邊大圖把左邊表格壓成 30% 寬」這種比例失衡。

每頁開寫前過下面 5 個 check：

### (1) 一句話寫得出來「這頁要幹嘛」嗎？

每頁該有單一 takeaway。如果寫不出一句話、表示這頁混了兩個概念、要拆。

> ✓ Slide 5：「QUIC 用 per-stream sequence/ACK 解掉 TCP HOL blocking」  
> ✗ Slide 5：「QUIC 的 multistream + 0-RTT + connection migration」（三個概念塞一頁）

### (2) 內容密度估計 — 預估 word/line count

寫之前粗估 body 內容會有多少：

| 密度 | 估計 | 風險 |
|---|---|---|
| 稀疏 | < 80 字 / < 5 行 | **slide 會半空白**，要補 副標 + 設計理由 / 核心觀念 把垂直空間填滿 |
| 中等 | 80-200 字 / 5-15 行 | 標準、剛好 |
| 密 | > 200 字 / > 15 行 | overflow 風險，可能要拆兩頁 或 用 img-very-tall layout 給左欄多寬度 |

**反例（要避免）**：一頁只有 4-row 表格 + 1 句 tagline → 50% body 是白的，
audience 讀成「這頁不用心」。要嘛加 副標 + 設計理由 把空間吃滿，要嘛跟
相鄰的 thin slide 合併。

### (3) 視覺類型 → 預期 aspect → grid 分配

選 deck.toml type 之前，**預測** image 的 aspect ratio：

| 視覺 source | 典型 aspect (W/H) | 套到的 grid | 左欄 / 右欄 |
|---|---|---|---|
| mermaid `flowchart LR` 短鏈（≤ 5 nodes）| ~2.5-3.6 | `img-wide` | **30% / 70%** |
| mermaid `flowchart LR` 多 node 帶 subgraph | ~1.3-1.8 | default | 38% / 62% |
| mermaid `flowchart TD` 長鏈（≥ 6 nodes）| ~0.3-0.5 | `img-very-tall` | 65% / 35% |
| mermaid `sequenceDiagram` | ~0.6-0.9 | `img-tall` | 50% / 50% |
| matplotlib line/bar chart | ~1.4-1.7 | default 或 `img-wide` | 38-30% / 62-70% |
| hand-SVG 正方形（800×600）| 1.33 | default | 38% / 62% |
| Marp native table（無圖）| n/a | 滿版 | 100% |

### (4) 內容跟 layout 比例 match check

預測完 layout 寬度，**確認左欄塞得下、塞得有重量**：

| Left col 寬 | 適合塞 | 不適合 |
|---|---|---|
| 30% (`img-wide`) | 短 bullet ≤ 4 條、單句說明 | 多欄表格、code block、密集段落 |
| 38% (default) | 短 table（≤ 3 欄）、6-8 bullet、短 code block (~8 行) | 多欄寬表、長 code |
| 50% (`img-tall`) | 多欄表格、code block 10+ 行、稍密段落 | 還是不適合超長 code |
| 65% (`img-very-tall`) | 密集表格、長 bullet list | — |
| 100% (no image) | 任何 | — |

**反例（要避免）**：mermaid LR 短鏈 → aspect 3.5 → `img-wide` → 左欄只剩
30%，但你想塞 4 欄 × 5 row 的對照表 → 表格被擠到讀不到。

**修法**：
- 改 mermaid 方向 `LR` → `TD` 讓 image 變 tall（左欄拿到 50%+）
- 或者放棄 image，整頁走 table-fullwidth
- 或者 trim 左欄內容到 4 bullet 內

### (5) 該不該畫圖？— diagram decision flow

寫純文字 + table 沒錯、但有時候 audience 在概念上接不到、就是因為缺一張圖。
判斷某頁是否要加 diagram，問自己 6 個問題：

| 問題 | 如果是 「Yes」 → | 該畫嗎 |
|---|---|---|
| 概念主要是 **結構 / topology**（誰連到誰、誰包誰）？ | 文字描述要繞、看圖 2 秒就懂 | **畫**（hand-SVG）|
| 概念主要是 **時序流動**（request → response → ...）？ | 時間軸有意義 | **畫**（mermaid sequenceDiagram）|
| 概念是 **N 個選項對比**（A vs B vs C）？ | 屬性差異列得出來 | **不畫**（table 通常更清楚）|
| 概念是 **數據 / 數字分布**（throughput vs loss% 等）？ | 軸跟值有意義 | **畫**（chart）|
| 概念抽象到 **文字會留下歧義**（「共用 vs 各自」「之前 vs 之後」「同一個 vs 多個」）？ | reader 容易誤解 | **畫**（hand-SVG）|
| 「diagram」其實只是「box 裡塞文字」？ | 沒有真的形狀 / 連線資訊 | **不畫**（直接用 bullet / table）|

具體判斷例（QUIC deck 19 頁的設計決策）：

| Slide 主題 | 工具 | 為什麼 |
|---|---|---|
| TCP vs QUIC 場景對照表 | table | N 個選項 + 屬性、no topology |
| QUIC stack 5 層 | code ASCII | 簡單堆疊、無連線形狀、ASCII 就夠 |
| HTTP/1.1 vs HTTP/2 連線拓樸 | **hand-SVG** | structure：6 條 TCP vs 1 條 TCP；純文字看不出「共用 vs 各自」 |
| HOL blocking 例子 | **hand-SVG** | 「掉一個、後面全卡」直接看 pipe + X 一目瞭然 |
| 0-RTT vs TCP setup RTT 差 | code ASCII | timeline 短、ASCII timeline 已夠視覺 |
| Connection migration | **hand-SVG** | 「IP 變、connection 死 / 活」要看到「同一張圖切兩個狀態」 |
| 重組 4 frames 按 offset | code ASCII | timestamp + buffer state 是表格性質、ASCII 表格夠 |

**反例（過去常犯）**：
- ❌ 把表格內容塞進 box + 連 box 用箭頭 → 「diagram」其實是繞路寫的 table
- ❌ 比較 A vs B 還配上「兩個 box + 箭頭」 → 直接 2-column table 比較清楚
- ❌ 為了 layout 變化硬畫圖 → 結果圖比文字更難懂

**Rule of thumb**：先寫 source.md 純文字版、感覺概念清楚就停手；感覺**讀者要腦補才能理解**才畫圖。

### (6) 連續頁 layout 多樣性 check

整 deck 排完一次後、掃過 layout 序列：

> ✗ S2 default / S3 default / S4 default / S5 default / S6 default
> （5 頁同 layout、視覺疲勞）
>
> ✓ S2 table / S3 default / S4 img-wide / S5 table / S6 img-tall
> （穿插、節奏好）

**規則**：避免 **3+ 頁連續同 layout**。中間穿插 table-fullwidth、img-tall、
或 img-very-tall 任一種破節奏。

### (7) Audience anchor — 新手向 deck 必補定義錨點

**新手 deck 引入任何技術單位 / 縮寫 / 領域術語時、第一次出現必含定義錨點**。

| 單位 / 術語 | 必補錨點 |
|---|---|
| dBm | 「相對 1 mW 的對數功率；0 dBm = 1 mW」|
| dBFS | 「相對 ADC 滿格 (Full Scale)，總是 ≤ 0」|
| dB | 「兩功率比值的對數（無單位）」|
| RBW | 「Resolution Bandwidth — FFT bin 的頻率寬度」|
| FFT | 「快速傅立葉轉換 — 時域 → 頻域」|
| 1 mW | 「milliwatt，毫瓦 = 1/1000 watt」|

**反例**：第一次提 dBm 就直接用、沒解釋 → 新手讀者中斷。

**修法**：在 unit 第一次出現位置加 1 句 inline 補充，或括號註「（= 1/1000 W）」。
若用 table 比較 dB / dBm / dBFS，table 內已含對應「是什麼」欄即可、不需重複 inline。

**何時套用**：source markdown 註解第一行有 `<!-- audience: beginner -->`、
或主 agent prompt 中提到「新手 / onboarding / 入門」字眼、就強制套用此 check。

### (8) Table cell width discipline

**Marp native 表格在 default grid 38/62 layout 內、cell 寬度有限**。中文不像
英文有 word boundary、被擠時會在奇怪位置斷字（例如把「示波器」拆成「示波\n器」）。

| Layout | 每欄能塞的 cell 寬度（per cell）|
|---|---|
| default 38/62（表在左欄）| ≤ 12 中文字 / ≤ 25 英文字 |
| img-tall 50/50（表在左欄）| ≤ 16 中文字 / ≤ 35 英文字 |
| table-fullwidth | ≤ 25 中文字 / ≤ 50 英文字 |
| 4+ 欄表 in default grid | **不行** — 至少要 table-fullwidth |

**修法**：
- cell 內中文文字 ≤ 上限；超過用 `<br>` **顯式斷句**
- 或把表搬到 table-fullwidth layout（`[slides.N] type = "table"` 沒右圖）
- 或拆成 2 個窄表 / 拆兩 slide

**反例（過去常踩）**：
> ✗ default grid 的 5-欄表，欄名都是「資料來源 / 視覺特徵 / 典型頻寬」這種長字串
> → 表頭擠成 2 行、cell 內容跟著 wrap、整個表變難讀
> ✓ 改 table-fullwidth、或拆成兩 slide 各 3 欄

---

寫完 source.md 後、跑 build 之前、再走一次這 8 個 check。若 build 出來
aspect log 跟你預估不同（例如預期 img-tall 但實際 default）、回去看 image
source 為什麼形狀不一樣、調整或接受 layout 變動後左欄重量。

## 0c. 自我檢查 — 每次 build 後必跑 6 個檢查（autonomous）

寫完 source.md / SVG → 跑 build → **不要直接交給 user 看**，先自己過一輪
checklist。下面這 6 類問題 author 可以自動偵測 + 修、不需 user 提醒。

### Check 1 — Table bottom row clipping

**症狀**：table 最後 1-2 row 在 rendered PDF 看不到（被切掉）。

**怎麼自動偵測**：
1. `grep "^|" source.md` 數每張 slide 的 table row 數
2. 用 `Read` 讀 rendered PDF 的對應頁
3. 比對 visible row count vs source row count
4. 不一致 → overflow

**修法**：
- 砍 1 row（選最不關鍵的）
- 或砍其他並列元素（inline 句子、bullet list）
- 或合併 cell 內容讓 table 變窄不變高

### Check 2 — Code block bottom truncation

**症狀**：code block 最後 N 行不見（特別是 closing `}` / `└──┘` 看不到）。

**怎麼自動偵測**：
1. `grep -c "^\`\`\`" source.md` 找 fenced code blocks
2. 數每個 code block 行數
3. 12+ 行的 code block + 其他 body 元素 → 高機率 overflow
4. Read PDF、確認最後一行是否可見

**修法**：
- Trim code block 行數（合併 / 簡化）
- 砍 inline comments
- 拆成 2 個更短的 code block

### Check 3 — SVG font sizes（per-layout floor）

**症狀**：SVG 內某些 text font-size 太小、render 後在投影機 / PDF 看不清楚。

**怎麼自動偵測**：
```bash
grep -oE 'font-size="[0-9]+"' /path/to/slide-NN-*.svg | sort -un
# 看最小值是否低於該 SVG 的 layout floor
```

**Floor 表（依 layout 決定）**：

| SVG 用在哪個 layout | Title / panel header | Card label / body | Caption / inline annotation | 絕對 floor |
|---|---|---|---|---|
| **default** 38/62（右欄縮 0.78×）| ≥ 22px | ≥ 18px | ≥ 16px | **16px** |
| **img-tall** 50/50（右欄縮 0.85×）| ≥ 20px | ≥ 16px | ≥ 14px | **14px** |
| **img-wide** 30/70（右欄較大）| ≥ 18px | ≥ 15px | ≥ 13px | **13px** |
| **cover / recap**（滿版 SVG）| ≥ 30px | ≥ 20px | ≥ 18px | **16px** |

**為什麼 floor 從 14 升到 16**：14px 在 default 38/62 grid 縮 0.78× 後實際視覺
< 11px、投影機上看不到。過去案例：spectrum-primer slide 22 recap SVG 用 13-14px
caption、user 反映「右邊字太小」。**新規則：default 任何字 ≥ 16px source。**

**修法**：
- bump font-size 到 floor 以上
- 如果 bump 後 layout 擠 → 重新分佈（少塞元素 / 放大 viewBox local 區）
- 如果 bump 後 box 變太擠 → 砍些次要元素

### Check 4 — Subtitle trailing `---` artifact

**症狀**：cover 副標 / 任何 slide 最後一個欄位後出現意外的 ` ---`。

**怎麼自動偵測**：
```bash
grep -E "(subtitle|callout-label).*---" /path/to/built.md
```

**修法**：
- 在 source.md 該 slide 末尾加 dummy field 終止符（如 `**視覺：** —`）
- 或修 build_hybrid.py 的 `_section` regex（已修、加 `^---\s*$` lookahead）

### Check 5 — Long title 兩行 wrap 點

**症狀**：title 長度 > 1 line、wrap 點落在不自然位置（mid-phrase / mid-comma）。

**怎麼自動偵測**：
1. 算 title 字元數（中文算 2 寬、英文算 1）
2. > 30 寬度 → 高機率 wrap
3. Read PDF 看 wrap 位置

**修法**：
- 縮短 title（move 細節到 副標）
- 在語意斷點插 `<br>`（cover 用 `——` 自動處理）
- 重新斷詞

### Check 6 — Image-text-vs-body size ratio

**症狀**：SVG 內字看起來比 body 文字小很多（reader 讀不舒服）。

**怎麼自動偵測**：
1. SVG aspect class（從 build log `[aspect]` 區）
2. SVG max font-size × scale factor （default 0.78× / img-tall 0.85×）
3. 跟 body 字級 20px 比、< 70% → 失衡

**修法**：bump SVG 字級到符合 body × 70% 以上 floor。

### Check 7 — SVG safe area（text / shape 超出 viewBox）

**症狀**：hand-SVG 內的 text 或 shape 部分超出 viewBox 邊界、被裁切。

**過去案例**：spectrum-primer slide 10 delta marker、SVG 內 callout box 的
`ΔdBm ≈ −43.2 dB` 那行 y 落在 ~390+、但容器 height 縮放後底部被切掉，
user 反映「右邊圖的說明文字被裁切」。

**Safe area 規格**（viewBox 800 × 600 一律遵守）：

| 元素 | 規則 |
|---|---|
| `<text>` 元素 | x ∈ [40, 760]，y ∈ [40, 560]（避開邊緣 40px padding）|
| `<rect>` | x ≥ 20 且 x+width ≤ 780；y ≥ 20 且 y+height ≤ 580 |
| `<circle>` | cx ∈ [20, 780] 且 cx-r ≥ 0；cy ∈ [20, 580] 且 cy+r ≤ 600 |
| 群組 / box 包含的最後 text | y ≤ 540（給 trailing line height 留 20px buffer）|

**怎麼自動偵測**：

```bash
# text 元素超出下界 (y > 560)
grep -oE 'y="(56[1-9]|5[7-9][0-9]|[6-9][0-9]{2})"' svg/*.svg

# text 元素超出右界 (x > 760)
grep -oE 'x="(76[1-9]|7[7-9][0-9]|[89][0-9]{2})"' svg/*.svg

# rect 寬度過大（手動算 x+width）
grep -E '<rect[^>]+width="[0-9]+"' svg/*.svg | python3 -c "
import sys, re
for line in sys.stdin:
    m = re.search(r'x=\"(\d+)\"[^>]+width=\"(\d+)\"', line)
    if m and int(m.group(1)) + int(m.group(2)) > 780:
        print('overflow:', line.strip())
"
```

**修法**：
- text 元素 y 偏低 → 把整個 group 上移、或縮小 box / element height
- 文字行數太多 box 裝不下 → 砍 1-2 行、或加大 box（在 safe area 內）
- 整個 SVG 元素佈局太密 → rework，可能要拉大 viewBox（但同時得調整字級保持比例）

### Check 8 — matplotlib suptitle 重疊

**症狀**：matplotlib 圖的 `fig.suptitle()` 與 source.md 已有的 slide 標題重複；
或 suptitle 跟 subplot title 在 SVG export 時擠在一起重疊。

**過去案例**：spectrum-primer slide 4 RBW chart 用 `fig.suptitle('兩個距離 8 kHz...', y=1.02)`
+ 兩個 subplot 各自 `ax.set_title('RBW 5 kHz → 分得開')` → SVG export 後
suptitle 跟 subplot title 在頂部擠成一團。

**規則：默認不用 `fig.suptitle()`**。理由：
1. source.md 已經有 slide `**標題：**`，suptitle 是重複資訊
2. SVG export 時 `y=1.02` 不穩、容易與 subplot title 撞

**例外（要用 suptitle 時）**：

```python
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
# 用 tight_layout 為 suptitle 保留頂部空間
fig.tight_layout(rect=[0, 0, 1, 0.92])
fig.suptitle('...', fontsize=15, y=0.97)  # y < 1.0 才安全
```

**怎麼自動偵測**：

```bash
grep -n "fig.suptitle\|plt.suptitle" charts/*.py
# 找到的話、檢查附近是否有 tight_layout(rect=...) 或 subplots_adjust(top=...)
```

**修法**：
- 移除 `fig.suptitle(...)` 行（最簡單，標題交給 source.md）
- 或加 `fig.tight_layout(rect=[0, 0, 1, 0.92])` 騰空間
- subplot 個別標題用 `ax.set_title(...)` 即可，不需要 fig 級 title

### 流程：自動掃 → 找問題 → 自動修 → 重新 build → 再掃

每改完 source.md / SVG / deck.toml：
1. `python3 build_hybrid.py --deck deck.toml`
2. **不直接交 user**，先：
   - `pdfinfo deck.pdf` 確認頁數對
   - `Read` PDF 隨機 3-5 頁掃 overflow / 小字
   - SVG slides 一定要看一次
   - Code block 多的 slide 一定要看一次
3. 找到問題 → 修 → goto 1
4. 自掃 ≤ 1 issue / 5 頁 → 才交 user

不要把「reviewer 應該抓」當藉口跳過自掃 — reviewer 是 second pass、不是
first pass。Author 該攔下的 cosmetic 問題就自己攔下。

## 1. Source markdown：5 段式

**Source.md 頂部建議加 metadata 標頭**（讓 author / reviewer / subagent 知道 audience）：

```markdown
# {Deck title}

<!--
audience: beginner | intermediate | expert
fact-checked:
  - 重點數據 1（核實來源）
  - 重點數據 2
-->
```

當 `audience: beginner` 時，§0 (7) Audience anchor check 自動套用 — 任何單位 /
縮寫 / 領域術語第一次出現必補定義錨點。

每張 slide 三段必填、四段選填：

```markdown
## Slide N: <章節標題 — 給 deck 作者看的，不渲染>

**標題：** 簡短（必要）

**副標：** 1-2 行精煉 lede「為什麼這頁存在」（選填）

**內容：** main body — table / code block / bullet / 段落（必要）

**設計理由：** slide 底部深色 callout strip，承載「為什麼這樣設計」（選填）

**視覺：** 給 mermaid / hand-SVG 設計者看的、不渲染（選填）

**章節：** H1 上方等寬大寫小字「CHAPTER 02 · GETTING STARTED」風格（選填）

**核心觀念：** 藍色 callout box「記住這一句」（選填）

**Anti-pattern：** 紅色 callout box「千萬不要踩」（選填）
```

**Cover (slide 1) 特殊**：只渲染 H1 + 副標。內容 / 設計理由 / callouts 不出，
保持封面 tagline 感。

## 2. deck.toml：把 slide 對到工具

```toml
[meta]
source = "../path/to/source.md"
output_basename = "my-deck"
footer = "MY · TOPIC"

[slides.2]
type = "table"                  # 沒右圖，Marp native 表格滿版

[slides.4]
type = "mermaid"
source = "mermaid/slide-04.mmd"

[slides.9]
type = "chart"
source = "charts/slide-09.py"   # 必須 save 到 OUT_PATH（env var）

[slides.1]
type = "svg"
source = "svg/slide-01-cover.svg"  # hand-written SVG，layout 自己畫

[slides.5]
type = "gemini"                 # AI 生圖。中文 hallucinate 嚴重，避用
prompt = "..."
```

### 工具選擇樹

| 視覺型態 | 用什麼 | 為什麼 |
|---|---|---|
| sequence / handshake / timeline | `mermaid` (`sequenceDiagram`) | 文字真實、0 typo、可 diff |
| flowchart ≤ 7 nodes | `mermaid` (`flowchart LR/TB`) | 同上 |
| line / bar chart with axes | `chart` (matplotlib) | 精確控制軸數字 |
| cover / decoration / cards / 精確 layout | `svg` (hand-written) | 完全可控、中文不亂 |
| 對照表 / 數據總表 | `table` (Marp native) | 已是文字、滿版 |
| 場景插畫 / 抽象 icon collage | `gemini` | **避用**，中文 hallucinate |

決定原則：能用 mermaid / chart / table 就用，需要精確 layout 才寫 hand-SVG，
最後不得已才 gemini。

## 3. 跑 build

```bash
# 改 DESIGN.md 之後（任何色票 / 字型 / aspect / 規範調整）
cd ~/.claude/skills/marp-deck
python3 derive_assets.py
# → 重生 theme.css / mermaid-config.json / gemini-style.txt / marp-deck.mplstyle

# 跑單個 deck
python3 build_hybrid.py --deck /path/to/deck.toml

# 輸出（跟 deck.toml 同層）：
# - {output_basename}.md   Marp source
# - {output_basename}.pptx / .pdf
# - img/slide-NN.{svg,png}  各 image 衍生物
```

衍生物（pptx / pdf / img/）放 .gitignore，source（deck.toml / mermaid/ /
charts/ / svg/ / source markdown）入 git。

## 4. DESIGN.md：視覺單一真理源

`DESIGN.md` 章節：

- §1 Palette（色票 token：fg / bg / accent-primary / accent-warn / accent-positive / muted / code-bg / code-fg）
- §2 Typography（fonts + scale）
- §3 Spacing & layout（含 aspect bands）
- §4 工具選擇樹（mapping）
- §5 Mermaid theme（auto-derived 到 mermaid-config.json）
- §6 matplotlib style（auto-derived 到 .mplstyle）
- §7 Gemini prompt suffix（auto-derived 到 gemini-style.txt）
- §8 Anti-patterns（硬性禁止）
- §9 Source markdown 寫法 spec
- §10 Refero 借鑑（design inspiration）
- §11 Callout palette（4 種 callout style）
- §12 Shape vocabulary（hexagon / rectangle / circle / ...）

改 DESIGN.md 後跑 `derive_assets.py` 重生衍生檔。所有用過這個 skill 的 deck
重 build 一次就自動套上新規範 — 不用一個 deck 一個 deck 改 hex 色碼。

## 5. Aspect-aware layout

很多 mermaid 出來 SVG 形狀很極端（垂直 flowchart aspect 0.2 / 寬扁 chart
aspect 2.0），全塞同一個 38/62 grid 會「圖被縮成很窄、字小到看不到」。

build_hybrid.py 在每張 image slide 出來後讀 SVG viewBox 寬高比，自動貼 class：

| Aspect (W/H) | Class | Grid | max-h | 處理對象 |
|---|---|---|---|---|
| < 0.50 | `img-very-tall` | 65 / 35 | 82vh | 鏈狀垂直 flowchart |
| 0.50 – 0.90 | `img-tall` | 50 / 50 | 78vh | sequenceDiagram、tall handshake |
| 0.90 – 1.80 | default | 38 / 62 | 65vh | 大部分 |
| > 1.80 | `img-wide` | 30 / 70 | 72vh | 寬扁 chart / panoramic |

Build 印每張的 classification + 警告：
```
[aspect]
  slide-04  aspect=0.33  → img-very-tall ← consider source rework
  slide-06  aspect=0.69  → img-tall
  slide-09  aspect=1.55  → default
```

**aspect < 0.45 印警告** — CSS 對極端 aspect 救不回來，要改源頭：
- mermaid `flowchart TD` 7-node 鏈 → 3-node 分組 box
- TD → LR
- subgraph 內 `direction TB/LR` 反向、讓整體形狀更方
- 萬不得已改 hand-SVG

## 6. Density-aware widening

左欄 content 有 code block 或超過 14 行、且圖是 default aspect 時，自動把
grid 從 38/62 收成 45/55。左欄拿到多 19% 寬給文字、圖實際大小不變
（default aspect 圖 height-bound、右欄本來就有橫向空間沒用到）。

Build 印 `[+left-dense]`：
```
slide-10  aspect=1.33  → default [+left-dense]
```

## 7. Mermaid 中文文字斷行陷阱

Mermaid 把中文當「無語意空白」處理、box 太窄時會在奇怪位置斷字：
```
Sliding window 流    ← 把「流控」拆兩行
控
```

**解法**：source `.mmd` 用 `<br/>` 顯式斷行、每項一行：
```
M["<b>TCP 加的 4 個機制</b><br/>① 連線管理<br/>② Sequence + ACK<br/>③ Sliding window<br/>④ 壅塞控制"]
```

針對 img-very-tall (aspect < 0.5) 那種超窄欄位：
- 把長英文詞中文化（`Congestion control` → `壅塞控制` 縮一半長度）
- 縮短箭頭 spacing（`App→IP` 比 `App → IP` 短 4 字元）

## 8. Cover 標題斷行

Cover 標題慣例：`{topic} —— {tagline}`。pipeline 偵測到 `——` **自動拆成**：
- `# {topic}` 乾淨 H1（PPTX slide title / PDF bookmark / file metadata 只看到主標題）
- `<p class="cover-tagline">—— {tagline}</p>` 分開元素（視覺上保留兩行排版）

```
**標題：** QUIC foundations —— 解決 TCP 哪些痛點 + 自己的 tradeoff
```
渲染後 marp 中間檔長這樣：
```html
# QUIC foundations

<p class="cover-tagline">—— 解決 TCP 哪些痛點 + 自己的 tradeoff</p>
```
視覺上仍是兩行；但 H1 文字 metadata 就是「QUIC foundations」乾淨字串。

**為什麼這樣設計**：早期版本把 `<br>` 插進 H1（如 `# topic<br>—— tagline`），
渲染視覺對、但 PPTX outline pane / PDF bookmark / 「另存為圖片」suggested
filename 會出現字面 `<br>` 字串。現在改成兩個獨立元素 → 視覺一樣 + metadata
乾淨。

## 9. 源頭 overflow 處理三輪

字級放大 + 暖底 + 大 padding 後，dense 頁面會 overflow。處理順序：

1. **第一輪自動回吐**：micro-tune 字級（body -2 / li -1 / code -1 / padding 微縮）
   → 跑 build、看還有哪幾頁 overflow
2. **第二輪 source trim**：對溢出的頁面 trim 1-3 行。常見策略：
   - 多個短 bullet 合併成 inline list（`(a) X · (b) Y · (c) Z`）
   - 刪 redundant explanation（已經在圖 / 副標 / 核心觀念講過的）
   - 壓 code block 行數（合併連續說明、移除 trailing comments）
3. **第三輪 callout 壓字**：design-rationale strip 字級可以再小（14→13）

如果 ~70% 頁面 overflow 表示第一輪字級回吐沒做夠、不是源頭問題。

## 10. Subagent prompt template — SVG batch generation

當主 agent delegate 給 subagent 寫多個 hand-SVG（如 cover / 量測示意圖 / chart），
**prompt 必須含下列所有規格**。漏掉任一條都會踩到 Check 3 / 7。

```markdown
為 [deck 主題] 生成 N 個 hand-written SVG 檔案。

**輸出路徑：** [絕對路徑/svg/]

**SVG 規格（所有檔案嚴格遵守）：**

- **viewBox：** `0 0 800 600`
- **背景：** 不填（讓 slide 背景透出）
- **Safe area（絕對遵守，避免 Check 7）：**
  - `<text>` 元素：x ∈ [40, 760]，y ∈ [40, 560]
  - `<rect>`：x ≥ 20 且 x+width ≤ 780；y ≥ 20 且 y+height ≤ 580
  - 群組 / box 內**最後一行 text**：y ≤ 540（給 line height 留 20px buffer）
- **字級 floor（avoid Check 3）：**
  - 用在 default 38/62 grid 右欄：title ≥ 22 / body ≥ 18 / caption ≥ 16；**絕對 floor 16px**
  - 用在 cover / recap 滿版：title ≥ 30 / body ≥ 20 / caption ≥ 18；floor 16px
  - 用在 img-tall 50/50 右欄：title ≥ 20 / body ≥ 16 / caption ≥ 14；floor 14px
- **色票（嚴格只用，token from DESIGN.md）：**
  - `#1A1A1A` text、`#FAF6EE` bg、`#D9633E` accent、`#B82E2E` warn
  - `#3F7F4C` positive、`#6B6258` muted、`#E5DDC9` border、`#1F2329` panel-bg、`#E8E2D3` panel-fg
- **字型：** `font-family="Inter Tight, Noto Sans TC, sans-serif"`
- **不可：** gradient（waterfall 例外）/ shadow / 3D / placeholder text / 多 stroke layer

**寫完每個 SVG 後自我 trace：**
1. grep 自己的 SVG 內所有 `y="(\d+)"` 確認沒有 > 560
2. grep 自己的 SVG 內所有 `font-size="(\d+)"` 確認最小值 ≥ 該 layout floor
3. 用視覺心算確認 `<rect>` 的 x+width / y+height 沒超 viewBox

**完成後回報：** 列每檔行數 + font-size 最小值 + 最後一行 y 座標。
**不要 dump SVG 內容**（節省 context）。
```

**何時不該 delegate**：每個 SVG < 50 行 + 主 agent 上下文充裕時、自己寫更快。
delegate 適合：5+ SVG batch、概念清楚的 schematic visuals、主 agent context 緊張時。

## 已知坑

| 症狀 | 原因 | 解法 |
|---|---|---|
| 標題被切 / 內容溢出 slide 底 | section flex 沒設 `justify-content: flex-start`、Marp 預設 center | `section { display:flex; flex-direction:column; justify-content:flex-start; overflow:hidden }` |
| Section parser 漏內容 | `_section` regex 把 `**1. ...**` (沒 colon) 當成 section header | regex 強制要 colon `[：:]` |
| matplotlib 中文渲染成方塊 | `font.sans-serif` 第一個必須是 CJK font（matplotlib 不做 char-level fallback）| `Noto Sans CJK JP` 放第一 |
| Mermaid 內中文亂碼 | mermaid 自帶 font 沒 CJK | mermaid-config.json fontFamily 加 Noto Sans TC |
| Mermaid 內中文斷字奇怪 | mermaid 不識中文語意斷詞 | `<br/>` 顯式換行 / 每項一行（見 §7）|
| Gemini 圖內中文亂寫 | Flash 對中文不穩 | **改 hand-SVG**，不要硬 retry Gemini |
| 圖太窄 / 太扁 字看不到 | viewBox aspect 極端 + 還沒套 aspect class | 看 build 印的 `[aspect]`、aspect < 0.45 改源頭 |
| Code block 字體被 silently 縮小 | Marp 包 `<pre is="marp-pre">` + SVG foreignObject auto-scaling | pipeline 把 ```fenced``` 改成 `<div class="codeblock">` 繞過 |
| matplotlib 顏色 parsing 出錯 | `.mplstyle` 把 `#` 當註解 | hex 去掉 `#`（`'2563EB'` 不是 `'#2563EB'`）|
| Marp 渲染 inline SVG 變成 raw text | Marp 不解析 inline SVG | 把 SVG 存檔、用 `<img>` 引用 |
| Cover 標題在奇怪位置斷行 | 瀏覽器 word-wrap 不認 em-dash 語意 | pipeline 自動偵測 `——` 插 `<br>` |

## 跟其他 skill 的關係

- **`notebooklm-marp-deck`（上游）** — Phase 1-3 做 deep research + markdown outline +
  三邊核實，最後把 5 段式 markdown + deck.toml 交給這個 skill 出檔。
- 直接餵 markdown 也行 — 不必經過 notebooklm-marp-deck 研究階段。已有 outline 的話
  跳過上游、直接用這個 skill。

## 給團隊：怎麼裝

```bash
# 1. 複製到自己的 ~/.claude/skills/
cp -r /path/to/marp-deck ~/.claude/skills/

# 2. 安裝依賴
pip install matplotlib
[ "$(python3 -c 'import sys;print(sys.version_info<(3,11))')" = "True" ] && pip install tomli
sudo apt install fonts-noto-cjk

# marp + mmdc：兩條路選一條
# (A) 全域裝
npm install -g @marp-team/marp-cli @mermaid-js/mermaid-cli
# (B) skill 內 local 裝（build_hybrid.py 會優先用這個）
cd ~/.claude/skills/marp-deck && npm install @marp-team/marp-cli @mermaid-js/mermaid-cli

# 3. 試跑 derive_assets
cd ~/.claude/skills/marp-deck && python3 derive_assets.py
# 應看到 [emit] theme.css / mermaid-config.json / gemini-style.txt / marp-deck.mplstyle
```

### Skill 資訊

- **Name**: `marp-deck`
- **Path**: `~/.claude/skills/marp-deck/`
- **Files**:
  - `SKILL.md` — 這份說明
  - `DESIGN.md` — 視覺單一真理源（色 / 字 / spacing / aspect bands / callout / shape vocab）
  - `derive_assets.py` — 從 DESIGN.md 衍生 4 個 asset
  - `build_hybrid.py` — 主 pipeline
  - `theme.css`, `mermaid-config.json`, `gemini-style.txt`, `marp-deck.mplstyle` — 衍生 asset
