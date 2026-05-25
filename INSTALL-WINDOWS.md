# marp-deck — Windows 安裝指南

> Porting 到新 Windows 主機時的雷區紀錄與解法。
> 第一次配置從 50 分鐘踩 4 個雷，全部 patch 完之後 build 一份 deck 約 15 秒。

## 一次裝好（複製貼上）

```powershell
# 0. 前置：Python 3.11+ / Node.js 18+ / Chrome（marp render 需要）
python --version    # 應 >= 3.11
node --version      # 應 >= 18
# Chrome 是任一版（marp 透過 puppeteer 自動找）

# 1. 進 skill 目錄
cd "$env:USERPROFILE\.claude\skills\marp-deck"

# 2. 補 package.json 並安裝 marp + mmdc（雷 A 解法）
npm init -y | Out-Null
npm install --save @marp-team/marp-cli @mermaid-js/mermaid-cli

# 3. 裝 Python 依賴
pip install matplotlib

# 4. 確認本機 CJK 字型可用（雷 D 解法依賴此）
python -c "import matplotlib.font_manager as fm; cjk = [f.name for f in fm.fontManager.ttflist if any(k in f.name for k in ['JhengHei', 'YaHei', 'Noto'])]; print('CJK fonts:', sorted(set(cjk)))"
# 期望輸出至少包含：Microsoft JhengHei / Microsoft YaHei / Noto Sans TC

# 5. 生成衍生檔（theme.css / mermaid-config.json / mplstyle / gemini suffix）
python derive_assets.py

# 6. 確認 build_hybrid.py 已 patch（雷 B + C 解法）
findstr /C:"win_mmdc = SKILL_DIR" build_hybrid.py
findstr /C:"--no-stdin" build_hybrid.py
# 兩條都該有輸出；都沒有就沒 patch、見下面雷 B/C
```

完成後跑一份範例 deck 確認：

```powershell
# 進專案 docs 目錄
cd path\to\your\deck-folder
python "$env:USERPROFILE\.claude\skills\marp-deck\build_hybrid.py" --deck deck.toml
# 應在 15-60 秒內看到 [pptx] 跟 [pdf] 輸出
```

---

## 4 個 Windows 雷區（已全部 patch 過）

### 雷 A：`marp-deck/` 缺 `package.json` → npm install 沒實際裝套件

**症狀：**
- `npm install @marp-team/...` 跑完顯示「up to date, audited 636 packages」
- 但 `node_modules/.bin/` 目錄根本不存在
- build_hybrid.py 報 `FileNotFoundError: [WinError 2] 系統找不到指定的檔案`

**原因：** repo 內只 commit `package-lock.json`、沒 commit `package.json`（git 設成 ignore 或從未 add）。npm 看到 lock file 沒 manifest 時，會 silently 假裝「已安裝」、實際不做事。

**解法：** 先 `npm init -y` 補回 package.json、再裝套件：

```powershell
cd "$env:USERPROFILE\.claude\skills\marp-deck"
npm init -y
npm install --save @marp-team/marp-cli @mermaid-js/mermaid-cli
```

**驗證：**
```powershell
Test-Path node_modules\.bin\mmdc.cmd  # 應為 True
Test-Path node_modules\.bin\marp.cmd  # 應為 True
```

---

### 雷 B：subprocess.run 找不到 Windows `.cmd` shim

**症狀：**
- 即使 `node_modules/.bin/mmdc.cmd` 存在
- build_hybrid.py 仍報 `[WinError 2] 系統找不到指定的檔案`
- 對 `marp` 也一樣

**原因：** npm 在 Windows 上建立 3 個 shim：`mmdc`（bash 腳本，Windows 跑不了）、`mmdc.cmd`（Windows 批次）、`mmdc.ps1`。Python `subprocess.run` 不會像 cmd shell 那樣自動加 `.exe`/`.cmd` 後綴。原始 build_hybrid.py 只找 `mmdc`（無副檔名），在 Linux/macOS OK、Windows fail。

**解法：** build_hybrid.py 已 patch 兩處（mermaid + marp）優先用 `.cmd`：

```python
# mermaid 那段
win_mmdc = SKILL_DIR / "node_modules/.bin/mmdc.cmd"
nix_mmdc = SKILL_DIR / "node_modules/.bin/mmdc"
if win_mmdc.exists():
    mmdc = str(win_mmdc)
elif nix_mmdc.exists():
    mmdc = str(nix_mmdc)
else:
    mmdc = "mmdc"

# marp 那段（同樣模式）
win_marp = SKILL_DIR / "node_modules/.bin/marp.cmd"
nix_marp = SKILL_DIR / "node_modules/.bin/marp"
# ... 同 mmdc 邏輯
```

**驗證 patch 是否在：**
```powershell
findstr /C:"win_mmdc = SKILL_DIR" build_hybrid.py
findstr /C:"win_marp = SKILL_DIR" build_hybrid.py
# 都應有輸出（行號 + 內容）
```

---

### 雷 C：Marp CLI 預設等 stdin → 卡死

**症狀：**
- 跑 build 後 node 進程開始（CPU 一兩秒高）然後 idle 至幾乎為 0
- 等 10+ 分鐘也不結束
- 直接從 PowerShell 跑 marp 會看到：`[INFO] Currently waiting data from stdin stream. Conversion will start after finished reading. (Pass --no-stdin option if it was not intended)`

**原因：** marp-cli v4 預設啟用 stdin 模式（接受 pipe 輸入）。從 Python `subprocess.run` 呼叫時、stdin 是 open 但沒資料、marp 會無限等待。

**解法：** 加 `--no-stdin` flag。build_hybrid.py 已 patch：

```python
cmd = [*marp_cmd, "--no-stdin", str(deck_md_abs), "--theme", str(theme_abs),
       f"--{fmt}", "--allow-local-files", "-o", str(out)]
```

**驗證：**
```powershell
findstr /C:"--no-stdin" build_hybrid.py
# 應有輸出（line 內含 "--no-stdin"）
```

---

### 雷 D：matplotlib 中文渲染成方塊（unicode boxes）

**症狀：**
- matplotlib 產生的 chart SVG 中、中文字變成 `▫▫▫▫`
- 例：「兩個距離 8 kHz 的 carrier」變「兩個▫▫▫ 8 kHz 的 carrier」

**原因：** `marp-deck.mplstyle` 第一順位字型是 `Noto Sans CJK JP`（Google 出的 CJK 整合包），但 Windows 系統預裝沒這個字型（macOS 也通常沒有）。matplotlib 找不到第一順位、找下一個，但若 stylesheet fallback 列表也沒到本機有的字型，就用 fallback 字型畫不出 CJK 字符 → 方塊。

**Windows 上實際有什麼 CJK 字型：**
- `Microsoft JhengHei`（繁中，預裝）
- `Microsoft YaHei`（簡中，預裝）
- `Noto Sans TC`（如果裝過 Office 365 / Adobe / Google Fonts 才會有）

**解法：** 每個 matplotlib chart 範本（`charts/slide-XX.py`）開頭加：

```python
import matplotlib

# 套用 marp-deck 樣式
mpl_style = os.environ.get('MPL_STYLE')
if mpl_style and os.path.exists(mpl_style):
    plt.style.use(mpl_style)

# Windows / macOS CJK fallback（蓋掉 mplstyle 預設）
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = [
    'Microsoft JhengHei',   # Windows 繁中
    'Microsoft YaHei',      # Windows 簡中
    'Noto Sans TC',
    'Noto Sans CJK JP',     # Linux 上 fonts-noto-cjk 安裝後才有
    'Noto Sans CJK TC',
    'sans-serif',
]
matplotlib.rcParams['axes.unicode_minus'] = False
```

**驗證本機有什麼字型可用：**

```powershell
python -c "import matplotlib.font_manager as fm; cjk = [f.name for f in fm.fontManager.ttflist if any(k in f.name for k in ['JhengHei', 'YaHei', 'Noto', 'CJK'])]; print('\n'.join(sorted(set(cjk))))"
```

至少要看到 `Microsoft JhengHei` 跟 `Microsoft YaHei` 其中之一。

---

## 症狀 → 解法 對照（快速排錯）

| 症狀 | 看哪個雷 |
|---|---|
| `npm install` 後 `node_modules` 沒建 | 雷 A |
| `[WinError 2] 系統找不到指定的檔案` | 雷 B |
| build 卡 10+ 分鐘 CPU 接近 0 | 雷 C |
| chart 中文變方塊 | 雷 D |
| `npm install` 真的有裝、但 `.bin/` 仍空 | 確認 PowerShell 在正確目錄；用 `Get-Location` |
| matplotlib import 失敗 | `pip install matplotlib` 沒裝；確認用對的 python（系統 vs venv） |
| `python derive_assets.py` 報缺 `tomllib` | Python < 3.11；`pip install tomli` 也可 |

---

## Porting checklist

把這份 skill 移到新 Windows 主機時：

- [ ] 複製 `~/.claude/skills/marp-deck/` 整個目錄到新主機相同位置
- [ ] **不要**複製 `node_modules/`（容量大、且 native module 可能跨機不相容）
- [ ] 跑「一次裝好」段落的 6 個步驟
- [ ] 從本 repo 找一份 `deck.toml` 試跑、確認 < 60 秒出 pptx + pdf
- [ ] 第一份 deck 若 build > 5 分鐘，看「症狀 → 解法」對照

---

## 修改紀錄

- **2026-05-18** — 初版。對應 flc-spectrum-visualizer 專案的 spectrum-primer + playwright-claude 兩份 deck 第一次 Windows 上跑通的全部地雷紀錄。
