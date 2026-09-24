#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""capture.py — 常驻后台: 快捷键开关「定时自动截图」+ 手动抓图

用法:
    python capture.py                          # 使用同目录 region_config.json
    pythonw capture.py                         # 无控制台窗口后台运行
    python capture.py --auto                   # 启动即开启自动截图(不用按 F8)
    python capture.py --once                   # 只抓一张就退出(自检)
    python capture.py --debug                  # 打印收到的每个按键

快捷键(可在配置里改):
    hotkey        默认 f8  -> **开关自动截图**(按一次开, 再按一次关; 开启后每 auto_interval 秒抓一张)
    hotkey_full   默认 f9  -> 手动抓整个虚拟桌面(备用)
    hotkey_shot   默认空   -> 手动抓一次固定区域(留空=禁用)

说明:
    - 每次保存 shot_YYYYmmdd_HHMMSS_mmm.png, 同时用最新一张覆盖 latest.png
      (latest.png 路径固定, 方便 MCP / Agent 直接读取, 不用翻目录找最新文件)。
    - 自动截图期间不响提示音(只在开关切换时响), 避免每 5 秒叫一声。
    - 每次抓图前会检查 region_config.json 是否被改动, 改了会自动热加载(含间隔、热键)。
    - 退出: 控制台里按 Ctrl+C (pythonw 后台运行时用任务管理器结束 pythonw.exe)。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:  # 统一路径解析(源码运行 / PyInstaller 打包后都能用)
    from paths import default_config_path as _default_config_path
except Exception:  # 单文件使用时兜底
    def _default_config_path() -> Path:
        return Path(__file__).resolve().with_name("region_config.json")


DEFAULT_CONFIG = _default_config_path()

DEFAULTS = {
    "hotkey": "f8",              # 自动截图的开关
    "hotkey_full": "f9",         # 手动抓整屏
    "hotkey_shot": "",           # 手动抓一次固定区域(留空=禁用)
    "auto_interval": 5,          # 自动截图间隔(秒), 最小 1
    "auto_on_start": False,      # 启动就开启自动截图
    "auto_skip_identical": False,  # True = 画面没变就不落新文件(省磁盘)
    "output_dir": r"D:\screenshots",
    "filename_prefix": "shot",
    "write_latest_alias": True,
    "max_keep": 500,
    "beep": True,
    "log_file": r"D:\screenshots\_capture.log",
}


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def load_config(path: Path) -> dict:
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def open_sct(mss_mod):
    """mss>=10 用 MSS(), 旧版本用 mss()。"""
    cls = getattr(mss_mod, "MSS", None) or getattr(mss_mod, "mss")
    return cls()


def resolve_region(cfg: dict, mon: dict) -> dict:
    """百分比 -> 当前虚拟桌面下的绝对像素矩形。"""
    r = cfg.get("region")
    if not r:
        raise ValueError("配置里没有 region, 请先运行 calibrate.py 标定一次")
    left = round(mon["left"] + float(r["left_pct"]) * mon["width"])
    top = round(mon["top"] + float(r["top_pct"]) * mon["height"])
    width = max(1, round(float(r["width_pct"]) * mon["width"]))
    height = max(1, round(float(r["height_pct"]) * mon["height"]))
    # 夹到屏幕范围内, 避免越界
    left = max(mon["left"], min(left, mon["left"] + mon["width"] - 1))
    top = max(mon["top"], min(top, mon["top"] + mon["height"] - 1))
    width = min(width, mon["left"] + mon["width"] - left)
    height = min(height, mon["top"] + mon["height"] - top)
    return {"left": left, "top": top, "width": width, "height": height}


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
def make_logger(log_path: str | None):
    handle = None
    if log_path:
        try:
            p = Path(log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            # 简单轮转: 超过 2MB 换名为 .1(自动截图会写很多行, 防止无限增长)
            try:
                if p.exists() and p.stat().st_size > 2 * 1024 * 1024:
                    backup = p.with_suffix(p.suffix + ".1")
                    os.replace(p, backup)
            except Exception:
                pass
            handle = open(p, "a", encoding="utf-8")
        except Exception:
            handle = None

    def log(msg: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        print(line, flush=True)
        if handle:
            try:
                handle.write(line + "\n")
                handle.flush()
            except Exception:
                pass

    return log


def beep(times: int = 1) -> None:
    try:
        import winsound

        for _ in range(max(1, times)):
            winsound.MessageBeep(-1)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 抓图
# --------------------------------------------------------------------------- #
def save_shot(mss_mod, cfg: dict, log, kind: str = "region",
              dedup_state: dict | None = None, quiet: bool = False) -> Path | None:
    """抓一张并落盘。dedup_state 不为空且开启去重时, 画面没变则返回 None。"""
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    with open_sct(mss_mod) as sct:
        mon = dict(sct.monitors[0])
        if kind != "full":
            mon = resolve_region(cfg, mon)
        shot = sct.grab(mon)

    from PIL import Image

    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    if dedup_state is not None and cfg.get("auto_skip_identical"):
        digest = hashlib.sha1(img.tobytes()).hexdigest()
        if dedup_state.get("h") == digest:
            dedup_state["skipped"] = dedup_state.get("skipped", 0) + 1
            return None
        dedup_state["h"] = digest

    now = datetime.now()
    prefix = cfg.get("filename_prefix") or "shot"
    name = f"{prefix}_{now:%Y%m%d_%H%M%S}_{now.microsecond // 1000:03d}.png"
    target = out_dir / name

    # 原子写: 先写临时文件再改名, 避免 MCP 侧读到半张图
    tmp = target.with_suffix(".png.part")
    img.save(tmp, "PNG", optimize=False)
    os.replace(tmp, target)

    if cfg.get("write_latest_alias", True):
        alias = out_dir / "latest.png"
        alias_tmp = out_dir / "_latest.png.part"
        img.save(alias_tmp, "PNG", optimize=False)
        os.replace(alias_tmp, alias)

    if cfg.get("beep", True) and not quiet:
        beep(1)

    prune(out_dir, prefix, int(cfg.get("max_keep") or 500))
    log(f"已保存 {target}  ({img.width}x{img.height}, {target.stat().st_size / 1024:.1f} KB)")
    return target


def prune(out_dir: Path, prefix: str, max_keep: int) -> None:
    if max_keep <= 0:
        return
    try:
        shots = sorted(out_dir.glob(f"{prefix}_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in shots[max_keep:]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass


def alive_pid(lock_path: Path):
    """读取锁文件里的 PID, 若进程仍存活则返回 PID, 否则 None。"""
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        k32.CloseHandle(handle)
        return pid
    return None


class AutoShooter:
    """定时自动抓图: 一个线程, 可随时开关、改间隔。"""

    MIN_INTERVAL = 1.0

    def __init__(self, capture_fn, logger, interval: float = 5.0, skip_identical: bool = False):
        self._fn = capture_fn
        self._log = logger
        self.interval = self._clamp(interval)
        self.skip_identical = bool(skip_identical)
        self._on = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._dedup: dict = {}
        self._turns = 0

    @classmethod
    def _clamp(cls, v) -> float:
        try:
            return max(cls.MIN_INTERVAL, float(v))
        except Exception:
            return 5.0

    # ---------- 状态 ----------
    @property
    def enabled(self) -> bool:
        return self._on.is_set()

    def toggle(self) -> bool:
        if self.enabled:
            self._on.clear()
        else:
            self._dedup.clear()   # 重新开启时, 第一张一定落盘
            self._turns += 1
            self._on.set()
        return self.enabled

    def set_interval(self, v) -> None:
        self.interval = self._clamp(v)

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="auto-shot")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._on.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._on.wait(0.3):      # 未开启就空转等待
                continue
            turn = self._turns
            self._shot()                     # 开启瞬间立刻先抓一张
            next_at = time.time() + self.interval
            while self._on.is_set() and not self._stop.is_set() and turn == self._turns:
                remain = next_at - time.time()
                if remain > 0:
                    self._stop.wait(min(0.2, remain))
                    continue
                self._shot()
                next_at = time.time() + self.interval

    def _shot(self) -> None:
        try:
            saved = self._fn(self._dedup)
            if saved is None and self.skip_identical:
                self._dedup["skipped"] = self._dedup.get("skipped", 0) + 1
                n = self._dedup["skipped"]
                if n % 12 == 1:              # 别每 5 秒刷一行日志
                    self._log(f"[i] 画面未变化, 已跳过 {n} 次 (auto_skip_identical=true)")
        except Exception as exc:
            self._log(f"[x] 自动抓图失败: {exc}")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="快捷键截屏到固定目录")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="region_config.json 路径")
    ap.add_argument("--once", action="store_true", help="只抓一张然后退出(用于自检)")
    ap.add_argument("--auto", action="store_true", help="启动即开启定时自动截图(不必按 F8)")
    ap.add_argument("--debug", action="store_true", help="打印收到的每一个按键(排查热键用)")
    ap.add_argument("--force", action="store_true", help="忽略「已有实例在跑」的检查")
    args = ap.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        print(f"[x] 读取配置失败: {exc}")
        return 1
    # 相对 output_dir 以配置文件所在目录为基准
    if not Path(cfg["output_dir"]).is_absolute():
        cfg["output_dir"] = str((config_path.parent / cfg["output_dir"]).resolve())

    log = make_logger(cfg.get("log_file"))

    try:
        import mss as mss_mod
    except ImportError as exc:
        print(f"[x] 缺少依赖: {exc}\n    请先执行: pip install mss pillow")
        return 1

    # 自检: 不装键盘钩子, 直接抓一张
    if args.once:
        try:
            path = save_shot(mss_mod, cfg, log)
            print(f"[OK] 自检截图完成: {path}")
            return 0
        except Exception as exc:
            print(f"[x] 抓图失败: {exc}")
            return 1

    # 单实例检查: 避免重复装钩子(重复按一次 F8 会连抓两张)
    lock_path = config_path.parent / "capture.pid"
    if not args.force:
        old_pid = alive_pid(lock_path)
        if old_pid:
            print(f"[!] 已有实例在运行 (PID {old_pid})。重复运行会重复截图, 已退出。")
            print("    确实要再开一个请加 --force;  要停掉旧的: taskkill /PID " + str(old_pid) + " /F")
            return 1
    try:
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    # 热键: 零依赖的 ctypes 钩子(keyboard 库在 py3.13+ 上会静默失效)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hotkey import HotkeyListener

    state = {"combos": (), "cfg": cfg, "mtime": 0.0}
    try:
        state["mtime"] = config_path.stat().st_mtime
    except Exception:
        pass

    def reload_if_changed(verbose: bool = False) -> dict:
        """配置热加载: 文件变了就重读(区域/目录改动无需重启, 热键由 apply_hotkeys 重挂)。"""
        try:
            mt = config_path.stat().st_mtime
        except Exception:
            return state["cfg"]
        if mt == state["mtime"]:
            return state["cfg"]
        state["mtime"] = mt
        try:
            fresh = load_config(config_path)
        except Exception as exc:
            log(f"[!] 配置解析失败, 继续用旧配置: {exc}")
            return state["cfg"]
        if not Path(fresh["output_dir"]).is_absolute():
            fresh["output_dir"] = str((config_path.parent / fresh["output_dir"]).resolve())
        state["cfg"] = fresh
        if verbose:
            log("检测到 region_config.json 变化, 已热加载")
        return fresh

    def on_shot(kind: str) -> None:
        """手动抓一张(F9 整屏 / hotkey_shot 区域), 带提示音。"""
        try:
            save_shot(mss_mod, reload_if_changed(), log, kind)
        except Exception as exc:
            log(f"[x] 抓图失败: {exc}")

    auto = AutoShooter(
        capture_fn=lambda dedup: save_shot(
            mss_mod, reload_if_changed(), log, "region", dedup_state=dedup, quiet=True
        ),
        logger=log,
        interval=cfg.get("auto_interval", 5),
        skip_identical=cfg.get("auto_skip_identical", False),
    )
    auto.start()

    last_toggle = {"t": 0.0}

    def on_toggle() -> None:
        """F8: 开/关自动截图。"""
        now = time.time()
        if now - last_toggle["t"] < 0.4:      # 防手抖连按导致开了又关
            return
        last_toggle["t"] = now
        cfg_now = reload_if_changed()
        auto.set_interval(cfg_now.get("auto_interval", 5))
        auto.skip_identical = bool(cfg_now.get("auto_skip_identical", False))
        on_now = auto.toggle()
        beep(2 if on_now else 1)
        if on_now:
            log(f"自动截图 -> 开启 (每 {auto.interval:g} 秒一张 -> {cfg_now['output_dir']})")
        else:
            log("自动截图 -> 关闭")

    listener = HotkeyListener(logger=log, debug=args.debug)
    listener.start()
    time.sleep(0.3)
    if not listener.alive():
        print(f"[x] 无法安装全局键盘钩子: {listener.last_error}")
        print("    常见原因: 安全软件拦截 / 以受限沙箱身份运行。试试【管理员身份】重新运行。")
        return 1

    def apply_hotkeys(cfg_now: dict) -> None:
        specs = (
            ("hotkey", "toggle", "自动截图开关"),
            ("hotkey_full", "full", "手动抓整屏"),
            ("hotkey_shot", "region", "手动抓固定区域"),
        )
        mapping, combos = {}, []
        for field, action, label in specs:
            combo = (cfg_now.get(field) or "").strip()
            if not combo:
                continue
            mapping[combo] = on_toggle if action == "toggle" else (lambda k=action: on_shot(k))
            combos.append((combo, action, label))
        listener.set_hotkeys(mapping)
        state["combos"] = tuple(combo for combo, _, _ in combos)
        for combo, action, label in combos:
            suffix = f"(按一次开, 再按一次关; 间隔 {auto.interval:g}s)" if action == "toggle" else ""
            log(f"快捷键 {combo.upper()} -> {label}{suffix}")

    try:
        apply_hotkeys(cfg)
    except Exception as exc:
        print(f"[x] 热键配置有误: {exc}")
        return 1

    # 启动时检查一次区域是否已标定
    try:
        with open_sct(mss_mod) as sct:
            resolve_region(cfg, dict(sct.monitors[0]))
    except Exception as exc:
        log(f"[!] {exc}")

    if args.auto or cfg.get("auto_on_start"):
        auto.toggle()
        beep(2)
        log(f"自动截图 -> 开启 (每 {auto.interval:g} 秒一张) [启动即开启]")

    log(f"监听中... 截图目录: {cfg['output_dir']}   (Ctrl+C 退出)")
    try:
        while True:
            time.sleep(0.5)
            before = state["combos"]
            fresh = reload_if_changed(verbose=True)
            auto.set_interval(fresh.get("auto_interval", 5))
            auto.skip_identical = bool(fresh.get("auto_skip_identical", False))
            fresh_combos = tuple(
                (fresh.get(f) or "").strip()
                for f in ("hotkey", "hotkey_full", "hotkey_shot")
                if (fresh.get(f) or "").strip()
            )
            if fresh_combos != before:
                try:
                    apply_hotkeys(fresh)
                except Exception as exc:
                    log(f"[x] 新热键无效, 保持旧热键: {exc}")
    except KeyboardInterrupt:
        pass
    finally:
        auto.stop()
        listener.stop()
        try:
            lock_path.unlink(missing_ok=True)   # 不用 atexit(见 app.py 的强制退出说明)
        except Exception:
            pass
        log("已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
