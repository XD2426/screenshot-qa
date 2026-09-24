ScreenshotQA v1.2.0 — 截图答题助手
========================================

【怎么用】
1. 双击「启动 ScreenshotQA」(或桌面快捷方式), 会出现一个黑色窗口 —— 那就是程序在运行, 关掉窗口即退出。
2. 第一次使用请先运行「标定截图区域」: 屏幕变暗后拖框圈住题目区域, 按回车保存。
3. 按 F8 = 开始自动截图(默认每 5 秒一张); 再按 F8 = 停止。
   F9 = 手动抓一张整屏(备用)。
4. 截图默认存放在 D:\screenshots, 最新一张永远叫 latest.png。

【改截图保存位置】(v1.2.0 新增)
方式一(推荐): 开始菜单 → ScreenshotQA → 「设置保存位置」, 在窗口里选好文件夹点「保存」。
    窗口里还能顺手改: 文件名前缀、最多保留张数、是否生成 latest.png、是否把旧截图一起搬过去。
方式二: 命令行
    ScreenshotQA.exe output                      查看当前保存位置
    ScreenshotQA.exe output D:\my_shots          改到 D:\my_shots
    ScreenshotQA.exe output D:\my_shots --move   同时把旧目录的截图搬过去
    ScreenshotQA.exe output --pick               弹出文件夹选择框
程序正在运行也无需重启: 改完 0.5 秒内自动生效(已在跑的程序会自己去新目录)。

【配合 AI 答题】
在 WorkBuddy 里说:
    读取 D:\screenshots\latest.png, 解答图里的题目。
(保存位置改过的话, 把路径换成你自己的)

【命令行用法】
    ScreenshotQA.exe                 启动监听(等同于双击)
    ScreenshotQA.exe calibrate       重新标定截图区域
    ScreenshotQA.exe settings        图形界面设置截图保存位置
    ScreenshotQA.exe output          查看当前截图保存位置
    ScreenshotQA.exe shot            立刻抓一张固定区域
    ScreenshotQA.exe shot --full     立刻抓一张整屏
    ScreenshotQA.exe run --auto      启动后立刻开始自动截图
    ScreenshotQA.exe run --hide      后台静默运行(开机自启用的就是这个)
    ScreenshotQA.exe run --debug     打印每个按键(排查热键)
    ScreenshotQA.exe config          用记事本打开配置文件
    ScreenshotQA.exe dir             打开截图目录
    ScreenshotQA.exe logs            打开运行日志
    ScreenshotQA.exe hotkey f8       热键自检: 按 f8 会打印 HIT
    ScreenshotQA.exe version         版本与路径信息

【配置文件】
    %APPDATA%\ScreenshotQA\region_config.json
改完保存即生效(程序每 0.5 秒检查一次, 无需重启)。

    "auto_interval": 5              自动截图间隔(秒), 最小 1
    "hotkey": "f8"                  自动截图开关的热键, 如 "ctrl+alt+s"
    "hotkey_full": "f9"             手动抓整屏的热键, 留空 = 禁用
    "output_dir": "D:\\screenshots"  截图保存目录(建议用「设置保存位置」改)
    "filename_prefix": "shot"       文件名前缀
    "max_keep": 500                 最多保留多少张, 超出自动删最旧(0 = 不限制)
    "write_latest_alias": true      额外写一份 latest.png
    "auto_skip_identical": false    改 true = 画面没变化就不存新文件(省磁盘)
    "beep": true                    开关切换时响提示音
    "auto_on_start": false          改 true = 启动程序就自动开始截图

【出问题了】
- 按 F8 没反应:
    先运行 ScreenshotQA.exe hotkey f8 —— 按 F8 若打印 HIT, 说明热键正常, 去「查看运行日志」找原因;
    若没有任何输出, 说明全局键盘钩子被安全软件拦截, 加白名单或重启一次。
- 抓到的图位置偏了:
    显示器缩放比例(DPI)或分辨率变过, 重新运行一次「标定截图区域」。
- 图片全黑:
    被截的窗口是硬件加速/独占全屏(如视频播放器), 换成窗口化模式。
- 改保存位置时报「没有权限/不可写」:
    换个目录(如 D:\shots), 不要用 C:\Program Files、系统盘根目录等受保护位置。
- 提示「已有实例在运行」:
    关掉旧的那个黑窗口, 或在命令行执行 taskkill /IM ScreenshotQA.exe /F。

【卸载】
    控制面板 → 程序和功能 → ScreenshotQA
    或开始菜单 → ScreenshotQA → 卸载 ScreenshotQA
卸载时会询问是否连截图一起删除; 选「否」则保留截图和配置。
注意: 卸载询问里删除的是默认目录 D:\screenshots; 若你改过保存位置, 自己的目录不会被动。
