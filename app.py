#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""app.py — ScreenshotQA 统一入口(打包成 exe 后双击/命令行都用它)

用法:
    ScreenshotQA.exe                     # = run, 启动监听(自动分配控制台看日志)
    ScreenshotQA.exe run --hide          # 后台静默运行(用于开机自启)
    ScreenshotQA.exe run --auto          # 启动即开启定时自动截图
    ScreenshotQA.exe run --debug         # 打印每个按键(排查热键)
    ScreenshotQA.exe calibrate           # 拖框标定截图区域(GUI)
    ScreenshotQA.exe shot                # 立刻抓一张固定区域(F9 等价)
    ScreenshotQA.exe shot --full         # 立刻抓一张整屏
    ScreenshotQA.exe settings            # 图形界面设置截图保存位置(推荐)
    ScreenshotQA.exe output              # 查看当前保存位置
    ScreenshotQA.exe output D:/shots     # 直接指定保存位置
    ScreenshotQA.exe output --pick       # 弹文件夹选择框指定保存位置
    ScreenshotQA.exe init                # 首次初始化: 建配置 + 建截图目录(可迁移旧配置)
    ScreenshotQA.exe config              # 用记事本打开配置文件
    ScreenshotQA.exe dir                 # 打开截图目录
    ScreenshotQA.exe logs                # 打开日志文件
    ScreenshotQA.exe hotkey f8           # 热键自检: 按 f8 打印 HIT

所有子命令都支持 --config <路径> 指定配置文件。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

__version__ = paths.VERSION

# 旧的开发机路径: 首次初始化时若存在, 直接把标定结果迁移过来
LEGACY_CONFIGS = [
    Path(r"D:\screenshot-qa\region_config.json"),
]


# --------------------------------------------------------------------------- #
# 无控制台环境下让 print 不炸 (windowed exe)
# --------------------------------------------------------------------------- #
class _NullStream:
    encoding = "utf-8"
    errors = "replace"

    def write(self, _s):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False

    def close(self):
        pass

    def fileno(self):
        raise OSError("no console")


def attach_console() -> bool:
    """确保有一个可写的控制台。返回是否可用。"""
    if sys.stdout is not None:
        set_utf8_console()
        return True
    if not paths.is_frozen():
        return False
    k32 = ctypes.windll.kernel32
    if not k32.GetConsoleWindow():
        if not k32.AllocConsole():
            return False
    try:
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1, errors="replace")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1, errors="replace")
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        ctypes.windll.kernel32.SetConsoleTitleW(f"ScreenshotQA v{__version__} — 关闭本窗口即退出")
    except Exception:
        return False
    set_utf8_console()
    return True


def set_utf8_console() -> None:
    """设置控制台标题。

    故意**不**改输出编码: Python 在真实控制台本就按 UTF-16(WriteConsoleW) 输出,
    中文正常; 改成强制 UTF-8 反而会让「重定向到管道/文件」的场景乱码
    (接收方按系统 ANSI 代码页 GBK 解码)。
    """
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(f"ScreenshotQA v{__version__} — 关闭本窗口即退出")
    except Exception:
        pass


def detach_console() -> None:
    """让控制台窗口直接消失(用于开机自启等静默场景)。"""
    if not paths.is_frozen():
        return
    try:
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass


def silence_streams(force: bool = False) -> None:
    if force or sys.stdout is None:
        sys.stdout = _NullStream()
    if force or sys.stderr is None:
        sys.stderr = _NullStream()


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def migrate_legacy_config(target: Path) -> Path | None:
    """找旧版源码目录的配置: 优先带标定结果(region)的那个。"""
    fallback = None
    for old in LEGACY_CONFIGS:
        if not old.exists() or old.resolve() == target.resolve():
            continue
        try:
            data = json.loads(old.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("region"):
            return old
        fallback = fallback or old
    return fallback


def ensure_ready(config_path: Path, migrate: bool = True) -> Path:
    """确保配置文件与截图目录存在。返回配置路径。"""
    import capture  # 延迟导入, 让 --help 快一些

    if not config_path.exists():
        seed = migrate_legacy_config(config_path) if migrate else None
        # output_dir 所在盘符不存在时回退到「图片\\Screenshots」
        defaults = dict(capture.DEFAULTS)
        out = Path(defaults["output_dir"])
        if not out.drive or not Path(out.drive + "\\").exists():
            fallback = Path.home() / "Pictures" / "Screenshots"
            defaults["output_dir"] = str(fallback)
            defaults["log_file"] = str(fallback / "_capture.log")
        paths.write_default_config(config_path, defaults, seed_from=seed)
        print(f"[i] 已生成配置文件: {config_path}" + (f"  (迁移自 {seed})" if seed else ""))
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    out_dir = Path(cfg.get("output_dir") or capture.DEFAULTS["output_dir"])
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[!] 无法创建截图目录 {out_dir}: {exc}")
    return config_path


def open_with_shell(target: Path) -> int:
    if not target.exists():
        print(f"[x] 不存在: {target}")
        return 1
    os.startfile(str(target))  # noqa: S606  (Windows only)
    return 0


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    import capture

    if args.hide:
        detach_console()
        silence_streams(force=True)
    else:
        attach_console()
        silence_streams()
    ensure_ready(Path(args.config))
    if Path(args.config).exists():
        argv = ["capture.py", "--config", str(args.config)]
        if args.auto:
            argv.append("--auto")
        if args.debug:
            argv.append("--debug")
        if args.force:
            argv.append("--force")
        sys.argv = argv
    return capture.main()


def cmd_calibrate(args) -> int:
    import calibrate

    attach_console()
    silence_streams()
    ensure_ready(Path(args.config))
    sys.argv = ["calibrate.py", "--config", str(args.config)]
    rc = calibrate.main()
    if rc == 0:
        print()
        print("标定完成。启动监听后按 F8 即可开始自动截图。")
        try:
            input("按回车键关闭本窗口...")
        except Exception:
            pass
    return rc


def cmd_shot(args) -> int:
    import capture

    attach_console()
    silence_streams()
    ensure_ready(Path(args.config))
    try:
        import mss as mss_mod
    except ImportError:
        print("[x] 缺少 mss 依赖")
        return 1
    cfg = capture.load_config(Path(args.config))
    if not Path(cfg["output_dir"]).is_absolute():
        cfg["output_dir"] = str((Path(args.config).parent / cfg["output_dir"]).resolve())
    log = capture.make_logger(cfg.get("log_file"))
    try:
        p = capture.save_shot(mss_mod, cfg, log, "full" if args.full else "region")
        print(f"[OK] 已保存 {p}")
        return 0
    except Exception as exc:
        print(f"[x] 抓图失败: {exc}")
        return 1


def cmd_settings(args) -> int:
    """打开「截图保存位置」图形设置窗口。"""
    import settings_ui

    ensure_ready(Path(args.config))
    if paths.is_frozen():
        detach_console()          # GUI 已给出全部反馈, 不要多一个黑窗口
        silence_streams(force=True)
    else:
        attach_console()
        silence_streams()
    return settings_ui.run_gui(Path(args.config), version=__version__)


def cmd_output(args) -> int:
    """查看 / 指定截图保存位置(命令行方式)。"""
    import settings_ui

    attach_console()
    silence_streams()
    config_path = Path(args.config)
    ensure_ready(config_path)

    target = args.path

    # --pick: 弹文件夹选择框
    if args.pick and not target:
        import tkinter as tk
        from tkinter import filedialog

        cfg = settings_ui.load_raw(config_path)
        cur = settings_ui.effective_output_dir(cfg, config_path)
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        picked = filedialog.askdirectory(title="选择截图保存文件夹", mustexist=False,
                                         initialdir=str(cur))
        root.destroy()
        if not picked:
            print("[i] 已取消")
            return 0
        target = picked

    # 无参数: 只显示
    if not target:
        cfg = settings_ui.load_raw(config_path)
        d = settings_ui.effective_output_dir(cfg, config_path)
        st = settings_ui.dir_stats(d, cfg.get("filename_prefix") or "shot")
        pid = settings_ui.running_instance(config_path)
        print(f"截图保存位置: {d}")
        print(f"  配置文件  : {config_path}")
        print(f"  日志文件  : {cfg.get('log_file')}")
        print(f"  已有截图  : {st['count']} 张, {settings_ui.human(st['bytes'])}"
              + (f", 最新 {st['latest']}" if st["latest"] else ""))
        print(f"  运行状态  : " + (f"监听中 (PID {pid})" if pid else "未检测到运行中的实例"))
        print("\n改位置: ScreenshotQA.exe output <新目录>   (加 --move 同时搬走已有截图)")
        return 0

    # 设置
    try:
        res = settings_ui.apply_storage(
            config_path,
            output_dir=target,
            move_existing=args.move,
            filename_prefix=args.prefix,
            max_keep=args.max_keep,
        )
    except Exception as exc:
        print(f"[x] 设置失败: {exc}")
        return 1
    print(f"[OK] 截图保存位置: {res['output_dir']}")
    if res["changed"]:
        for c in res["changed"]:
            print(f"     {c}")
    for w in res["warnings"]:
        print(f"     ! {w}")
    print(f"     目录现有 {res['stats']['count']} 张, {settings_ui.human(res['stats']['bytes'])}")
    return 0


def cmd_hotkey(args) -> int:
    import hotkey as hk

    attach_console()
    silence_streams()
    target = (args.combo or "").strip() or None
    listener = hk.HotkeyListener(debug=target is None)
    if target:
        listener.add(target, lambda: print(f"HIT {target}", flush=True))
        print(f"自测: 请按 {target}(Ctrl+C 退出)")
    else:
        print("自测: 打印所有按键(Ctrl+C 退出)")
    listener.start()
    import time

    time.sleep(0.3)
    if not listener.alive():
        print(f"[x] 钩子安装失败: {listener.last_error}")
        return 1
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        listener.stop()
    return 0


def cmd_init(args) -> int:
    attach_console()
    silence_streams()
    p = ensure_ready(Path(args.config), migrate=not args.no_migrate)
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    print(f"[OK] 配置: {p}")
    print(f"     截图目录: {cfg.get('output_dir')}")
    print(f"     auto_interval={cfg.get('auto_interval')}s  hotkey={cfg.get('hotkey')}")
    return 0


def cmd_config(args) -> int:
    attach_console()
    silence_streams()
    p = ensure_ready(Path(args.config))
    print(f"[i] 配置文件: {p}")
    return open_with_shell(p)


def cmd_dir(args) -> int:
    attach_console()
    silence_streams()
    import capture

    ensure_ready(Path(args.config))
    cfg = capture.load_config(Path(args.config))
    out = Path(cfg.get("output_dir") or capture.DEFAULTS["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    return open_with_shell(out)


def cmd_logs(args) -> int:
    attach_console()
    silence_streams()
    import capture

    ensure_ready(Path(args.config))
    cfg = capture.load_config(Path(args.config))
    log_file = cfg.get("log_file")
    if not log_file:
        print("[x] 配置里没有 log_file")
        return 1
    p = Path(log_file)
    if not p.exists():
        print(f"[i] 日志还不存在(还没抓过图): {p}")
        return 1
    # 用记事本打开并滚到末尾
    try:
        subprocess.Popen(["notepad.exe", str(p)])
    except Exception:
        return open_with_shell(p)
    return 0


def cmd_version(args) -> int:
    attach_console()
    silence_streams()
    print(f"ScreenshotQA v{__version__}")
    print(f"  frozen  : {paths.is_frozen()}")
    print(f"  程序目录: {paths.app_dir()}")
    print(f"  数据目录: {paths.data_dir()}")
    print(f"  配置文件: {paths.default_config_path()}")
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ScreenshotQA",
        description="截图 + 自动答题辅助工具(定时抓取屏幕固定区域)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default=str(paths.default_config_path()),
                        help="region_config.json 路径")

    ap.add_argument("-c", "--config", default=argparse.SUPPRESS,
                    help="region_config.json 路径")
    ap.add_argument("-v", "--version", action="version", version=f"ScreenshotQA {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run", parents=[common], help="启动监听(F8=自动截图开关, F9=手动整屏)")
    p.add_argument("--hide", action="store_true", help="不开控制台窗口(后台静默)")
    p.add_argument("--auto", action="store_true", help="启动即开启自动截图")
    p.add_argument("--debug", action="store_true", help="打印收到的每个按键")
    p.add_argument("--force", action="store_true", help="忽略「已有实例在跑」检查")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("calibrate", parents=[common], help="拖框标定截图区域")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("shot", parents=[common], help="立刻抓一张")
    p.add_argument("--full", action="store_true", help="抓整个虚拟桌面(默认只抓标定区域)")
    p.set_defaults(func=cmd_shot)

    p = sub.add_parser("init", parents=[common], help="首次初始化: 生成配置 + 建目录")
    p.add_argument("--no-migrate", action="store_true", help="不迁移旧版标定结果")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("settings", parents=[common], help="图形界面设置截图保存位置")
    p.set_defaults(func=cmd_settings)

    p = sub.add_parser("output", parents=[common],
                       help="查看/指定截图保存位置(例: output D:\\shots --move)")
    p.add_argument("path", nargs="?", default="", help="新的保存目录; 不填=只查看")
    p.add_argument("--pick", action="store_true", help="弹文件夹选择框")
    p.add_argument("--move", action="store_true", help="把旧目录里已有的截图一起搬过去")
    p.add_argument("--prefix", default=None, help="同时改文件名前缀(如 shot)")
    p.add_argument("--max-keep", dest="max_keep", type=int, default=None,
                   help="同时改「最多保留张数」, 0=不限制")
    p.set_defaults(func=cmd_output)

    p = sub.add_parser("config", parents=[common], help="打开配置文件")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("dir", parents=[common], help="打开截图目录")
    p.set_defaults(func=cmd_dir)

    p = sub.add_parser("logs", parents=[common], help="打开日志")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("hotkey", parents=[common], help="热键自检(例: hotkey f8)")
    p.add_argument("combo", nargs="?", default="", help="要测试的组合键, 如 f8 / ctrl+alt+s")
    p.set_defaults(func=cmd_hotkey)

    p = sub.add_parser("version", parents=[common], help="显示版本与路径信息")
    p.set_defaults(func=cmd_version)

    return ap


def flush_streams() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            if s is not None:
                s.flush()
        except Exception:
            pass


def hard_exit(rc: int) -> None:
    """退出前强制结束进程。

    打包成 exe 后(尤其 bundle 里含 tkinter/Pillow 时), 解释器正常退出会被拖住
    几十秒(实测约 26s: 进程已无输出但迟迟不返回), 命令行/计划任务体验很差。
    这里 flush 之后直接 _exit: 跳过线程 join 与 atexit。
    源码运行时保持正常退出, 便于调试与单测。
    """
    if not paths.is_frozen():
        return
    flush_streams()
    os._exit(rc)


def main() -> int:
    argv = sys.argv[1:]
    # 双击 exe(无参数) -> 默认 run, 且显示控制台
    parser = build_parser()
    if not argv:
        argv = ["run"]
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        rc = args.func(args)
    except KeyboardInterrupt:
        rc = 0
    except Exception as exc:
        attach_console()
        silence_streams()
        import traceback

        traceback.print_exc()
        print(f"[x] {exc}")
        try:  # 只在真控制台里等回车, 避免管道/计划任务里永久挂住
            if sys.stdin is not None and sys.stdin.isatty():
                input("按回车键关闭...")
        except Exception:
            pass
        rc = 1
    hard_exit(rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
