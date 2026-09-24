# ScreenshotQA — 屏幕固定区域定时截图工具（Windows）

`F8` 一按开启**每 5 秒自动截图**，再按一次关闭 → 图落到固定目录 → 交给本地 AI 工具（WorkBuddy 等）读图。

> **用途**：把屏幕上固定区域内不断变化的内容（题干、字幕、K 线、日志面板……）自动落盘成图片，
> 配合文件系统让 AI 助手按固定文件名读取，省去手工截图。
> 纯本地运行，不联网、不上传任何数据。请自行确认使用场景合规。

---

## 下载

| 方式 | 适合谁 | 操作 |
|---|---|---|
| **安装包**（推荐） | 不想装 Python | [ScreenshotQA-Setup-1.2.0.exe](https://github.com/XD2426/screenshot-qa/releases/latest/download/ScreenshotQA-Setup-1.2.0.exe) · ~12.5 MB，双击即装，**每用户安装免 UAC** |
| **源码** | 想改代码 / 非 Windows | `git clone` 后跑 `install.ps1`，见 [第 1 节](#1-目录结构) |

安装包只含 Windows x64 的 Python 运行时与依赖，无需预装 Python；卸载走「设置 → 应用」或「控制面板 → 程序和功能」。

---

```
   ┌──────────────┐  F8 开关 ┌────────────────────┐      ┌─────────────────┐
   │  屏幕固定区域 │ ───────► │ capture.py 常驻     │ ───► │ D:\screenshots\ │
   │ (题库/题干)   │  每5秒   │ mss 抓图 + PIL 存图 │      │  shot_*.png     │
   └──────────────┘          └────────────────────┘      │  latest.png     │
                                                          └────────┬────────┘
                                                                   │ 文件系统 MCP
                                                                   ▼
                                                        ┌─────────────────────┐
                                                        │ WorkBuddy 读图答题  │
                                                        └─────────────────────┘
```

快捷键一览（都可在 `region_config.json` 里改）：

| 键 | 作用 |
|---|---|
| `F8`（`hotkey`） | **自动截图开关**：按一下开（立刻抓一张，之后每 `auto_interval` 秒一张），再按一下关 |
| `F9`（`hotkey_full`） | 手动抓一次整屏（备用） |
| 空（`hotkey_shot`） | 手动抓一次固定区域；配成 `f10` 之类即可启用 |

关键点：**截图脚本不会主动"推送"给 WorkBuddy**，而是落到共享目录，由 WorkBuddy 去读。
`latest.png` 永远是最新一张（固定文件名），所以提示词可以写死，不用每次找文件名。
自动截图时**不响提示音**（只在开关切换时响 1~2 声），否则每 5 秒叫一次太吵。

---

## 1. 目录结构

```
D:\screenshot-qa\                 # 工具本体（路径无中文空格，建议别动）
├─ .venv\                         # 独立虚拟环境（install.ps1 自动建）
├─ calibrate.py                   # 标定：拖框选区域 → 存相对百分比坐标
├─ capture.py                     # 主脚本：常驻 + 快捷键 + 截屏存盘
├─ settings_ui.py                 # 「设置保存位置」窗口 + 存储类配置读写
├─ app.py                         # 统一入口（run/calibrate/settings/output/shot/...）
├─ paths.py                       # 源码/便携/APPDATA 三态路径解析
├─ hotkey.py                      # 零依赖全局热键（ctypes WH_KEYBOARD_LL），也可单独自测
├─ region_config.json             # 配置：快捷键 / 目录 / 区域 / 保留张数
├─ requirements.txt               # 依赖：mss pillow（不需要 keyboard）
├─ start_capture.vbs              # 双击静默后台启动（无黑窗口）
├─ install.ps1                    # 一键装环境
└─ mcp.json.example               # WorkBuddy MCP 配置示例

D:\screenshots\                   # 截图输出（WorkBuddy 只读这个目录）
├─ shot_20260923_090012_123.png
├─ latest.png                     # 始终=最新一张
└─ _capture.log                   # 抓图日志
```

---

## 2. 一次性安装

前置：Windows + Python 3.11+（建议 python.org 官方版，**必须是带 tkinter 的版本**）+ Node.js（MCP 用）。

### 方式 A：一键（推荐）

管理员 PowerShell：

```powershell
cd D:\screenshot-qa
powershell -ExecutionPolicy Bypass -File install.ps1
```

脚本做了 4 件事：找带 tkinter 的 Python → 建 `.venv` → 装依赖 → 建 `D:\screenshots`。日志在 `install.log`。

> **不要装 `keyboard` 库**。它最后更新在 2020 年，在 Python 3.13/3.14 上 `add_hotkey()`
> 不报错但回调**永不触发**（实测：注入按键时原生钩子收到 21 次事件，keyboard 库收到 0 次），
> 这正是「按 F8 没反应」的根因。本方案的热键由自带的 `hotkey.py` 用 ctypes 实现，零依赖、
> 也不需要管理员权限。

### 方式 B：手动

```powershell
cd D:\screenshot-qa
C:\Python314\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
mkdir D:\screenshots -Force
```

> 校验 tkinter：`.\.venv\Scripts\python.exe -c "import tkinter"` 不报错即可。
> 若报错说明该 Python 不带 tkinter，换 python.org 官方安装包重装（安装时保持默认勾选 tcl/tk）。

---

## 3. 标定区域（只做一次）

```powershell
cd D:\screenshot-qa
.\.venv\Scripts\python.exe calibrate.py
```

- 屏幕变暗，**左键拖拽**框住题干+选项区域
- `Enter` / 双击 / 右键 = 保存，`Esc` = 取消，拖拽时按 `Shift` = 锁正方形
- 保存的是**相对虚拟桌面的百分比坐标**，所以换分辨率后仍能对齐（前提：题目区在屏幕上的相对位置不变）

配置文件里 `region` 字段的形态：

```json
"region": {
  "left_pct": 0.26, "top_pct": 0.15, "width_pct": 0.48, "height_pct": 0.52,
  "screen_ref":      { "left": 0, "top": 0, "width": 1920, "height": 1080 },
  "pixel_rect_ref":  { "left": 499, "top": 162, "width": 921, "height": 561 },
  "calibrated_at":   "2026-09-23T09:00:12"
}
```

`screen_ref` / `pixel_rect_ref` 只是标定当时的记录，改分辨率不影响使用。

---

## 4. 常驻运行

前台（方便看日志，先这样测）：

```powershell
cd D:\screenshot-qa
.\.venv\Scripts\python.exe capture.py
```

后台无窗口：双击 `start_capture.vbs`（用 `pythonw.exe`），停止用任务管理器结束 `pythonw.exe`。

自检（不按快捷键，直接抓一张）：

```powershell
.\.venv\Scripts\python.exe capture.py --once
```

启动即开自动截图（连 F8 都不用按）：

```powershell
.\.venv\Scripts\python.exe capture.py --auto
```

### 自动截图怎么用

1. 脚本跑起来后按一次 `F8` → 日志出现 `自动截图 -> 开启 (每 5 秒一张 -> D:\screenshots)`，**马上先抓一张**，之后每 5 秒一张。
2. 再按 `F8` → `自动截图 -> 关闭`，停止。
3. 开关切换时会响提示音（开 2 声 / 关 1 声），自动抓图过程**静默**。
4. 间隔、是否去重、开关热键都能改，改完存盘 **0.5 秒内自动生效**，不用重启脚本。

| 场景 | 配置 |
|---|---|
| 想改成每 3 秒 | `"auto_interval": 3` |
| 启动就跑，不用按 F8 | `"auto_on_start": true`（或命令行加 `--auto`） |
| 画面不动时不想堆文件 | `"auto_skip_identical": true` → 画面和上一张完全一样就跳过，只记日志 |
| 换开关热键 | `"hotkey": "ctrl+alt+s"` |
| 5 秒一张太占地方 | `"max_keep": 200`（自动删最旧的，5 秒一张时 200 张 ≈ 16 分钟历史） |

> 手动抓图（F9 / `hotkey_shot`）时会响一声；自动模式不响，避免每 5 秒叫一次。

启动时若提示「已有实例在运行 (PID xxx)」，说明上次的脚本没关干净（两个实例会重复截图）。
停掉旧的：`taskkill /PID xxx /F`；确实要再开一个加 `--force`。

### 按键没反应的排查顺序

```powershell
# 1) 先确认钩子本身能不能收到按键（最关键的判断）
.\.venv\Scripts\python.exe hotkey.py f8      # 然后按 F8，应打印 HIT f8
.\.venv\Scripts\python.exe hotkey.py         # 不带参数：打印所有按键，按什么就显示什么
# 2) 再看抓图主脚本收到了什么
.\.venv\Scripts\python.exe capture.py --debug
```

- `hotkey.py f8` 有 HIT → 钩子正常，看 `D:\screenshots\_capture.log` 里的报错（如未标定 region）。
- `hotkey.py` 按什么键都不输出 → 钩子被安全软件/沙箱拦了，换管理员运行或把 `D:\screenshot-qa` 加入白名单。
- 两个都正常但按 F8 无图 → 多半是**旧实例还在跑**或用了 `keyboard` 库的旧版本脚本，见上面的说明。

### 改截图保存位置（存哪儿）

**方式 A：图形界面（推荐）**

```powershell
cd D:\screenshot-qa
.\.venv\Scripts\python.exe app.py settings      # 打开「设置保存位置」窗口
```
或装过安装包的话：开始菜单 → ScreenshotQA → **设置保存位置**（不用记路径，双击即可）。

窗口里能改：

| 项 | 说明 |
|---|---|
| 截图保存到 | 目标文件夹；`浏览…` 选路径，`打开` 直接进去看；四个快捷位置一键填 |
| 文件名前缀 | 默认 `shot`，最终文件名形如 `shot_20260924_094130_123.png` |
| 最多保留 | 超出按时间删最旧；`0` = 不限制 |
| 同时写 latest.png | AI/MCP 读的固定文件名，建议保持勾选 |
| 把旧截图一起搬过去 | 换目录时勾上，旧目录里的 `shot_*.png` + `latest.png` 一并搬走（同名不覆盖） |

点「保存」即生效 —— **程序正在运行也不用重启**（它每 0.5 秒检查配置文件，自动热加载）。
保存前会做校验：路径为空、盘符不存在、目录不可写都会在窗口底部红字提示，且**不会写坏配置**（原子写盘）。

**方式 B：命令行**

```powershell
.\.venv\Scripts\python.exe app.py output                      # 查看当前保存位置 + 已有张数/占用
.\.venv\Scripts\python.exe app.py output D:\my_shots          # 改目录
.\.venv\Scripts\python.exe app.py output D:\my_shots --move   # 改目录并搬走已有截图
.\.venv\Scripts\python.exe app.py output --pick               # 弹文件夹选择框
```

**方式 C：直接改配置** —— `region_config.json` 里的 `output_dir`（支持相对路径，相对配置文件所在目录）。
日志文件 `log_file` 原来跟截图同目录的话，改保存位置时会自动跟着搬到新目录。

---

### 开机自启（二选一）

1. `Win+R` → `shell:startup` → 把 `start_capture.vbs` 的**快捷方式**丢进去。
2. 任务计划程序：新建任务 → 触发器"登录时" → 操作"启动程序" = `.venv\Scripts\pythonw.exe`，参数 = `capture.py`，起始于 = `D:\screenshot-qa`。
   （不需要管理员权限；少数机器上被安全软件拦钩子时，再勾选「使用最高权限运行」）

---

## 5. 配置文件说明（region_config.json）

| 字段 | 默认 | 说明 |
|---|---|---|
| `hotkey` | `f8` | **自动截图开关**热键，如 `f8` / `ctrl+alt+s` / `shift+q` |
| `hotkey_full` | `f9` | 手动抓整屏的热键；留空字符串可禁用 |
| `hotkey_shot` | `""` | 手动抓一次固定区域的热键；默认空 = 禁用 |
| `auto_interval` | `5` | 自动截图间隔（秒），最小 1 |
| `auto_on_start` | `false` | `true` = 启动就开启自动截图（等同 `--auto`） |
| `auto_skip_identical` | `false` | `true` = 画面与上一张完全一致时跳过，不落新文件（省磁盘） |
| `output_dir` | `D:\screenshots` | 输出目录，支持相对路径（相对配置文件所在目录）。**建议用「设置保存位置」改**（gui/命令行见第 4 节） |
| `filename_prefix` | `shot` | 文件名前缀 |
| `write_latest_alias` | `true` | 是否额外写 `latest.png`（建议保持 true） |
| `max_keep` | `500` | 最多保留多少张 `shot_*.png`，超出的按时间删最旧；0=不清理 |
| `beep` | `true` | 手动抓图响一声；自动截图不响（只在开关切换时响） |
| `log_file` | `D:\screenshots\_capture.log` | 日志；`null` 关闭文件日志（超 2MB 自动轮转为 `.log.1`） |
| `region` | `null` | 由 `calibrate.py` 写入，**别手改**。重装/同步文件时不要用模板覆盖它，否则标定结果丢失（重标一次即可，约 10 秒） |

全部字段改完**存盘即生效**（0.5 秒内热加载），只有新增/删除实例需要重启。

---

## 6. WorkBuddy MCP 配置

编辑 `C:\Users\<你>\.workbuddy\mcp.json`（没有就新建），合并进 `mcpServers`：

```json
{
  "mcpServers": {
    "screenshot-fs": {
      "command": "cmd",
      "args": [
        "/c", "npx", "-y",
        "@modelcontextprotocol/server-filesystem",
        "D:\\screenshots",
        "D:\\screenshot-qa"
      ],
      "env": {}
    }
  }
}
```

要点：

- Windows 上 `npx` 实际是 `npx.cmd`，直接写 `"command": "npx"` 有些宿主会 ENOENT，所以统一用 `cmd /c npx`；`npx.cmd` 绝对路径是 `D:\Program Files\nodejs\npx.cmd`（已在系统 PATH 里）。
- 只暴露 `D:\screenshots`（读图）就够；再挂 `D:\screenshot-qa` 可让 Agent 直接改配置、看日志。
- 首次启动会下载 MCP 包（约十几秒），之后走 npx 缓存。
- **改完不会自动生效**：需要在 WorkBuddy **连接器管理页右上角的"自定义连接器"入口**里找到 `screenshot-fs` 并点**信任**，然后重启会话。

> 其实不配 MCP 也能干活：WorkBuddy 本身就能读本地图片，直接说"读 `D:\screenshots\latest.png`"即可。
> 配 MCP 的好处是它具备目录浏览能力（可自己按时间排序找最新图、批量读多张）。

---

## 7. 日常使用

1. 让题库窗口保持在标定时的位置（浏览器/客户端不要挪动或改缩放）。
2. 按 `F8` 开启自动截图（每 5 秒一张；不想连续抓就再按一次 F8 关掉，或用 `F9`/`hotkey_shot` 手动单张）。
3. 在 WorkBuddy 里发一句（可存为固定提示词）：

> 读取 `D:\screenshots\latest.png`（或列出该目录按修改时间取最新一张），识别图中的题目并给出答案与简要解析。

想批量答一组题：让自动截图开着切题（每 5 秒一张就是一条时间线），然后说"读取 D:\screenshots 下最近 5 张图片，逐张作答"。

---

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| **按 F8 没反应、目录没图** | ① 先跑 `hotkey.py f8` 自测（有 HIT = 钩子正常）；② 看 `D:\screenshots\_capture.log`；③ 确认没有残留旧实例（启动时会提示 PID）；④ 若装过 `keyboard` 库的旧版脚本，删掉它——该库在 Python 3.13/3.14 上钩子静默失效 |
| 按 F8 没开自动截图 | 看日志有没有 `自动截图 -> 开启`；连续快按两下会被 0.4 秒防抖吃掉一次（这是有意的） |
| 自动截图停不下来 | 再按一次 F8；或直接结束进程 `taskkill /IM pythonw.exe /F`（只杀该名字的进程，注意别误杀其它 python）；重启时用 `"auto_on_start": false` |
| 每 5 秒一张太占磁盘 | `"auto_interval": 10` 放慢，或 `"auto_skip_identical": true` 只在画面变化时落盘，或调小 `"max_keep"` |
| 想要"只在题目变化时才有新文件" | `"auto_skip_identical": true`，同时 `"max_keep": 0` 关掉清理 |
| 钩子装不上（`SetWindowsHookEx 失败`） | 安全软件拦截 → 加白名单或管理员运行；极少数沙箱环境不允许全局钩子 |
| 想换热键 | 改 `region_config.json` 的 `hotkey` / `hotkey_full` / `hotkey_shot`（如 `ctrl+alt+s`、`shift+q`），存盘后 0.5 秒自动生效 |
| `No module named 'mss'` | 用 `.venv\Scripts\python.exe` 执行，别用系统 python；或重跑 `pip install -r requirements.txt` |
| `无法启动标定窗口 / no module named tkinter` | 该 Python 不带 tkinter，换 python.org 官方版重建 venv |
| 抓到的图偏移/只抓到局部 | 显示器缩放（DPI）变化后需重新标定；标定脚本已置 DPI 感知，若你在别的缩放比例下运行过题库窗口，请重标一次 |
| 图片全黑 | 题库是硬件加速/独占全屏（如某些播放器），改用窗口化模式；或换成 F9 整屏试 |
| 改保存位置后图还在老地方 | ① 确认是真在跑的程序（`app.py output` 会显示「监听中 (PID xxx)」）；② 配置里 `output_dir` 是否真的变了（同一条命令能看）；③ 别在旧目录里找 `latest.png`——`latest.png` 只在新目录里维护 |
| 改保存位置报「不可写 / 没有权限」 | 换到用户目录（如 `D:\shots`、`图片\Screenshots`）；`C:\Program Files`、系统盘根目录、`C:\Windows` 下会被拒 |
| `settings` 打开后没有窗口 | 只有 `--console` 版 exe 才带控制台；若被安全软件拦，用 `ScreenshotQA.exe output <路径>` 直接改 |
| 图片到 WorkBuddy 里看不见新内容 | 确认是 `latest.png` 或最新时间戳文件；MCP 目录写的是 `D:\screenshots`；目录路径不能有中文或空格 |
| 想让 WorkBuddy 免手动触发 | 本机 WorkBuddy 没有对外开放 HTTP 接口，脚本无法主动唤起；可选做法是用自动化定时任务在固定时刻提示你发指令 |

---

## 9. 打包成 Windows 安装包（免 Python）

一键构建脚本：`packaging\build.ps1`。产出单文件 exe + NSIS 安装包。

```powershell
cd packaging
.\build.ps1                 # exe + 安装包
.\build.ps1 -SkipInstaller  # 只出 exe
```

构建依赖：venv 里的 `pyinstaller`、已安装的 NSIS（`C:\Program Files (x86)\NSIS\makensis.exe`）。

### 产物

| 文件 | 大小 | 说明 |
|---|---|---|
| `packaging\dist\ScreenshotQA\` | ~50 MB / exe 18.5 MB | **onedir 绿色版文件夹**（整个文件夹一起拷走用，exe 靠同目录的 `_internal\` 运行） |
| `packaging\dist\ScreenshotQA-Setup-1.2.0.exe` | ~12.5 MB | 安装包，双击即装（[Release 附件](https://github.com/XD2426/screenshot-qa/releases)） |

> **为什么不用 onefile？** 本机实测：`--onefile` 且 bundle 里含 tkinter（标定/设置窗口，约 1000 个 tcl/tk 数据文件）时，程序在**退出阶段要卡约 25 秒**才能返回（PyInstaller 单文件清理临时目录所致），空脚本 onefile 只要 2.7s、含 PIL 的 2.9s、**含 tkinter 的 onedir 只要 0.38s**。
> 所以默认改成 `--onedir`；确实需要单文件的加 `-OneFile`（会重现慢退出）。
> 另外 `app.py` 里做了兜底：打包运行时退出前 `os._exit()`，跳过可能被拖住的解释器收尾。

### 安装包行为（已实测）

- 装到 `%LOCALAPPDATA%\Programs\ScreenshotQA` —— **每用户安装，不弹 UAC**。
- 配置/日志放 `%APPDATA%\ScreenshotQA\`，卸载时保留（不会被清）。
- 开始菜单 10 个快捷方式：启动 / 标定 / **设置保存位置** / 立即抓一张 / 打开目录 / 查看日志 / 打开设置文件 / 热键自检 / 使用说明 / 卸载。
- 可选组件：桌面快捷方式、**开机自动启动**（写 `HKCU\...\Run`，命令为 `ScreenshotQA.exe run --hide`）、**导入旧版标定结果**（从 `D:\screenshot-qa\region_config.json`）。
- 安装完成页可直接勾选「设置截图保存位置」；卸载走「控制面板 → 程序和功能」，静默卸载默认**不删**截图目录，避免误删。
- 注意：卸载询问里删除的是默认目录 `D:\screenshots`；若你改过保存位置，自定义目录不会被动。

### 打包后的路径规则（`paths.py`）

| 运行形态 | 配置文件位置 |
|---|---|
| 源码 `python app.py` | 脚本同目录 `region_config.json` |
| exe，且 exe 旁有 `region_config.json` | 用 exe 旁那份（**便携模式**，整个文件夹拷走即用） |
| exe（默认） | `%APPDATA%\ScreenshotQA\region_config.json` |

### exe 的子命令

```text
ScreenshotQA.exe                 启动监听(等同于双击; 关掉控制台窗口即退出)
ScreenshotQA.exe calibrate       重新标定截图区域
ScreenshotQA.exe settings        图形界面设置截图保存位置
ScreenshotQA.exe output [路径]   查看/指定截图保存位置(可加 --move / --pick)
ScreenshotQA.exe shot [--full]   立刻抓一张(区域 / 整屏)
ScreenshotQA.exe run --auto      启动后立刻开始自动截图
ScreenshotQA.exe run --hide      后台静默运行(开机自启用)
ScreenshotQA.exe run --debug     打印每个按键(排查热键)
ScreenshotQA.exe init            初始化配置 + 建目录(可迁移旧版标定)
ScreenshotQA.exe config | dir | logs | hotkey f8 | version
```

命令行参数里的中文在真实控制台显示正常；若输出重定向到管道，请用 `chcp 65001` 或直接看日志文件。
