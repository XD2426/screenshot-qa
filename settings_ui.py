#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""settings_ui.py — 「截图保存位置」设置窗口 + 存储类配置的读写逻辑

两种用法:
    ScreenshotQA.exe settings              # 打开图形设置窗口(推荐, 双击即可)
    ScreenshotQA.exe output D:\\shots      # 命令行直接指定(见 app.py)

覆盖的配置项(都与「图存哪儿、怎么存」有关):
    output_dir          截图保存目录                <- 主要项
    filename_prefix     文件名前缀
    max_keep            最多保留张数(0 = 不限制)
    write_latest_alias  是否额外把最新一张写成 latest.png
    log_file            日志路径(保存目录变了会自动跟着搬)

设计要点:
    - 保存是「原子写」: 先写 .tmp 再 os.replace, 不会把配置写坏。
    - 只改自己负责的字段, 其余字段(热键/区域/间隔...)原样保留。
    - 保存后无需重启: capture.py 每 0.5 秒检查配置文件, 会自动热加载。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

try:
    import paths
except Exception:  # 单文件使用时兜底
    paths = None  # type: ignore[assignment]


MANAGED_FIELDS = (
    "output_dir",
    "filename_prefix",
    "write_latest_alias",
    "max_keep",
    "log_file",
)


# --------------------------------------------------------------------------- #
# 配置读写
# --------------------------------------------------------------------------- #
def _defaults() -> dict:
    import capture

    return dict(capture.DEFAULTS)


def load_raw(config_path: Path) -> dict:
    """读配置(补默认值), 不做路径解析。"""
    cfg = _defaults()
    p = Path(config_path)
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_raw(config_path: Path, cfg: dict) -> None:
    """原子写配置。"""
    p = Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def normalize_dir(raw: str, base: Path) -> Path:
    """把用户输入变成绝对路径。支持 %VAR%、~、前后引号; 相对路径以 base 为基准。"""
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        raise ValueError("保存位置不能为空")
    s = os.path.expandvars(s)
    p = Path(os.path.expanduser(s))
    if not p.is_absolute():
        p = Path(base) / p
    return Path(os.path.normpath(str(p)))


def check_dir(d: Path) -> list[str]:
    """创建并试写目录。返回警告列表; 不可用时抛异常(带中文原因)。"""
    warns: list[str] = []
    drive = d.drive
    if not drive:
        raise ValueError(f"不是合法的绝对路径: {d}")
    root = Path(drive + "\\")
    if not root.exists():
        raise ValueError(f"磁盘不存在: {drive}")

    if d == root:
        warns.append(f"{d} 是磁盘根目录, 截图会直接堆在根下, 建议换个文件夹")

    try:
        d.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(f"没有权限创建/写入: {d}(换个目录, 或以管理员身份运行)")
    except Exception as exc:
        raise ValueError(f"无法创建目录 {d}: {exc}")

    probe = d / f".write_test_{os.getpid()}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception as exc:
        raise ValueError(f"该目录不可写: {d}({exc})")

    if str(d).startswith(("C:\\Windows", "C:\\Program Files", os.environ.get("WINDIR", "\0"))):
        warns.append("系统目录不建议用来存截图(权限受限)")
    return warns


def effective_output_dir(cfg: dict, config_path: Path) -> Path:
    """与 capture.py 保持一致: 相对 output_dir 以配置文件所在目录为基准。"""
    raw = str(cfg.get("output_dir") or "")
    p = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
    if not p.is_absolute():
        p = Path(config_path).resolve().parent / p
    return Path(os.path.normpath(str(p)))


def dir_stats(d: Path, prefix: str = "shot") -> dict:
    """统计目录里的截图数量/占用/最新一张。"""
    info = {"exists": d.exists(), "count": 0, "bytes": 0, "latest": None, "latest_time": None}
    if not d.exists():
        return info
    try:
        files = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg")]
    except Exception:
        return info
    info["count"] = len(files)
    latest = None
    for f in files:
        try:
            info["bytes"] += f.stat().st_size
            st = f.stat()
        except Exception:
            continue
        if latest is None or st.st_mtime > latest[1]:
            latest = (f, st.st_mtime)
    if latest:
        info["latest"] = latest[0].name
        info["latest_time"] = datetime.fromtimestamp(latest[1])
    return info


def human(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.1f} GB"


def running_instance(config_path: Path) -> int | None:
    """若 capture 正在运行(锁文件里的 PID 仍存活), 返回 PID。"""
    try:
        from capture import alive_pid

        return alive_pid(Path(config_path).resolve().parent / "capture.pid")
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 应用设置
# --------------------------------------------------------------------------- #
def apply_storage(
    config_path: Path,
    *,
    output_dir: str | Path | None = None,
    filename_prefix: str | None = None,
    write_latest_alias: bool | None = None,
    max_keep: int | None = None,
    move_existing: bool = False,
) -> dict:
    """写入存储相关设置。返回结果摘要 dict(失败抛 ValueError)。"""
    config_path = Path(config_path)
    cfg = load_raw(config_path)
    changed: list[str] = []
    warnings: list[str] = []
    moved = 0

    old_dir = effective_output_dir(cfg, config_path)

    # --- 保存目录 ---
    if output_dir is not None:
        new_dir = normalize_dir(str(output_dir), config_path.resolve().parent)
        warnings += check_dir(new_dir)
        if new_dir != old_dir:
            cfg["output_dir"] = str(new_dir)
            changed.append(f"output_dir -> {new_dir}")
            # 日志原来跟截图同目录的话, 一起搬到新目录
            log_file = cfg.get("log_file")
            if log_file:
                try:
                    lp = Path(os.path.expandvars(str(log_file)))
                    if lp.parent.resolve() == old_dir.resolve():
                        cfg["log_file"] = str(new_dir / lp.name)
                        changed.append(f"log_file -> {cfg['log_file']}")
                except Exception:
                    pass
            if move_existing and old_dir.exists():
                moved = _move_shots(old_dir, new_dir, cfg.get("filename_prefix") or "shot")
                if moved:
                    changed.append(f"搬移已有截图 {moved} 个文件")
        else:
            cfg["output_dir"] = str(new_dir)

    # --- 文件名前缀 ---
    if filename_prefix is not None:
        s = (filename_prefix or "").strip() or "shot"
        bad = set('\\/:*?"<>|')
        if bad & set(s):
            raise ValueError('文件名前缀不能包含 \\ / : * ? " < > |')
        if s != cfg.get("filename_prefix"):
            cfg["filename_prefix"] = s
            changed.append(f"filename_prefix -> {s}")

    # --- 最多保留 ---
    if max_keep is not None:
        try:
            n = int(max_keep)
        except Exception:
            raise ValueError("「最多保留」必须是整数")
        if n < 0:
            raise ValueError("「最多保留」不能是负数")
        if n != cfg.get("max_keep"):
            cfg["max_keep"] = n
            changed.append(f"max_keep -> {n}")

    # --- latest.png ---
    if write_latest_alias is not None:
        v = bool(write_latest_alias)
        if v != bool(cfg.get("write_latest_alias", True)):
            cfg["write_latest_alias"] = v
            changed.append(f"write_latest_alias -> {v}")

    save_raw(config_path, cfg)
    new_out = effective_output_dir(cfg, config_path)
    pid = running_instance(config_path)
    if pid:
        warnings.append(f"已在运行的程序(PID {pid})会在 0.5 秒内自动生效, 不用重启")
    return {
        "ok": True,
        "config_path": str(config_path),
        "output_dir": str(new_out),
        "log_file": cfg.get("log_file"),
        "changed": changed,
        "moved": moved,
        "warnings": warnings,
        "running_pid": pid,
        "stats": dir_stats(new_out, cfg.get("filename_prefix") or "shot"),
    }


def _move_shots(src: Path, dst: Path, prefix: str) -> int:
    """把旧目录里的截图搬到新目录(同名不覆盖, 加 -1 后缀)。"""
    n = 0
    try:
        items = list(src.glob(f"{prefix}_*.png")) + list(src.glob("latest.png"))
    except Exception:
        return 0
    for f in items:
        try:
            if not f.is_file():
                continue
            target = dst / f.name
            if target.exists():
                target = dst / f"{f.stem}-{f.stat().st_mtime_ns % 100000}{f.suffix}"
            shutil.move(str(f), str(target))
            n += 1
        except Exception:
            pass
    return n


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
def run_gui(config_path: Path, version: str = "") -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:  # DPI 感知, 避免高分屏糊
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    config_path = Path(config_path)
    cfg = load_raw(config_path)
    cur_dir = effective_output_dir(cfg, config_path)

    root = tk.Tk()
    root.title("设置截图保存位置" + (f" — ScreenshotQA v{version}" if version else ""))
    try:
        if paths is not None:
            ico = Path(paths.resource_dir()) / "app.ico"
            if ico.exists():
                root.iconbitmap(default=str(ico))
    except Exception:
        pass
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    root.configure(padx=14, pady=12)

    dir_var = tk.StringVar(value=str(cur_dir))
    prefix_var = tk.StringVar(value=str(cfg.get("filename_prefix") or "shot"))
    keep_var = tk.StringVar(value=str(cfg.get("max_keep") if cfg.get("max_keep") is not None else 500))
    latest_var = tk.BooleanVar(value=bool(cfg.get("write_latest_alias", True)))
    move_var = tk.BooleanVar(value=False)

    # ---------- 保存位置 ----------
    box = ttk.LabelFrame(root, text=" 截图保存到 ", padding=10)
    box.pack(fill="x")

    row = ttk.Frame(box)
    row.pack(fill="x")
    entry = ttk.Entry(row, textvariable=dir_var, width=52)
    entry.pack(side="left", fill="x", expand=True)

    def browse() -> None:
        d = filedialog.askdirectory(title="选择截图保存文件夹", mustexist=False,
                                    initialdir=dir_var.get() or str(cur_dir))
        if d:
            dir_var.set(str(Path(os.path.normpath(d))))

    ttk.Button(row, text="浏览…", command=browse, width=8).pack(side="left", padx=(6, 0))

    def open_dir() -> None:
        try:
            d = normalize_dir(dir_var.get(), config_path.resolve().parent)
        except Exception as exc:
            set_status(f"× {exc}", error=True)
            return
        if not d.exists():
            set_status(f"目录还不存在: {d}(点「保存」会创建)")
            return
        os.startfile(str(d))  # noqa: S606

    ttk.Button(row, text="打开", width=6, command=open_dir).pack(side="left", padx=(4, 0))

    row2 = ttk.Frame(box)
    row2.pack(fill="x", pady=(6, 0))
    ttk.Label(row2, text="常用:").pack(side="left")
    presets = [
        ("D:\\screenshots", Path("D:/screenshots")),
        ("图片\\Screenshots", Path.home() / "Pictures" / "Screenshots"),
        ("文档\\Screenshots", Path.home() / "Documents" / "Screenshots"),
        ("桌面\\Screenshots", Path.home() / "Desktop" / "Screenshots"),
    ]
    for label, p in presets:
        ttk.Button(row2, text=label, width=15,
                   command=lambda p=p: dir_var.set(str(p))).pack(side="left", padx=2)

    # ---------- 存储选项 ----------
    box2 = ttk.LabelFrame(root, text=" 其它存储选项 ", padding=10)
    box2.pack(fill="x", pady=(10, 0))

    r = ttk.Frame(box2)
    r.pack(fill="x")
    ttk.Label(r, text="文件名前缀").pack(side="left")
    ttk.Entry(r, textvariable=prefix_var, width=14).pack(side="left", padx=(6, 4))
    ttk.Label(r, text="例:").pack(side="left")
    ttk.Label(r, text="shot_20260924_094130_123.png", foreground="#888").pack(side="left", padx=(4, 0))

    r = ttk.Frame(box2)
    r.pack(fill="x", pady=(8, 0))
    ttk.Label(r, text="最多保留").pack(side="left")
    ttk.Spinbox(r, textvariable=keep_var, from_=0, to=100000, increment=100, width=8).pack(
        side="left", padx=(6, 4))
    ttk.Label(r, text="张(0 = 不限制; 超出按时间删最旧)").pack(side="left")

    ttk.Checkbutton(box2, text="同时把最新一张写成 latest.png(AI/MCP 读这个固定文件名)",
                    variable=latest_var).pack(anchor="w", pady=(8, 0))
    ttk.Checkbutton(box2, text="把旧目录里已有的截图一起搬到新位置(可能较慢)",
                    variable=move_var).pack(anchor="w", pady=(4, 0))

    # ---------- 状态 ----------
    status = tk.Label(root, text="", anchor="w", justify="left", wraplength=520,
                      fg="#0a0", font=("Microsoft YaHei UI", 9))
    status.pack(fill="x", pady=(10, 0))

    def set_status(msg: str, error: bool = False) -> None:
        status.configure(text=msg, fg="#c00" if error else "#0a0")

    def refresh_status() -> None:
        try:
            d = effective_output_dir(load_raw(config_path), config_path)
        except Exception:
            d = cur_dir
        st = dir_stats(d, cfg.get("filename_prefix") or "shot")
        lines = [f"当前: {d}"]
        if st["exists"]:
            lines.append(f"          已有 {st['count']} 张, 共 {human(st['bytes'])}")
        else:
            lines.append("          目录还不存在, 点「保存」会创建")
        pid = running_instance(config_path)
        lines.append(f"运行状态: 监听中 (PID {pid}), 改完 0.5 秒自动生效" if pid else "运行状态: 未检测到运行中的实例")
        set_status("\n".join(lines))

    refresh_status()

    # ---------- 按钮 ----------
    btns = ttk.Frame(root)
    btns.pack(fill="x", pady=(12, 0))

    def do_save(close: bool) -> None:
        try:
            keep = int(keep_var.get())
        except Exception:
            set_status("× 「最多保留」必须是整数", error=True)
            return
        try:
            res = apply_storage(
                config_path,
                output_dir=dir_var.get(),
                filename_prefix=prefix_var.get(),
                write_latest_alias=latest_var.get(),
                max_keep=keep,
                move_existing=move_var.get(),
            )
        except Exception as exc:
            set_status(f"× {exc}", error=True)
            return

        dir_var.set(res["output_dir"])
        move_var.set(False)
        msg = ["√ 已保存"]
        if res["changed"]:
            msg.append("    " + "; ".join(res["changed"])[:300])
        else:
            msg.append("    配置没有变化")
        for w in res["warnings"]:
            msg.append(f"    ! {w}")
        refresh_status()
        set_status("\n".join(msg))
        if close:
            root.destroy()

    ttk.Button(btns, text="取消", width=10, command=root.destroy).pack(side="right")
    ttk.Button(btns, text="保存并关闭", width=12,
               command=lambda: do_save(True)).pack(side="right", padx=6)
    ttk.Button(btns, text="保存", width=10,
               command=lambda: do_save(False)).pack(side="right")

    root.bind("<Escape>", lambda _e: root.destroy())
    root.bind("<Return>", lambda _e: do_save(False))

    root.update_idletasks()
    # 显式按内容设定窗口尺寸(仅设位置时高 DPI 下会被裁切)
    w = max(root.winfo_reqwidth(), 600)
    h = root.winfo_reqheight()
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 3)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)   # 必须在设定尺寸之后, 否则窗口被锁在旧尺寸上

    entry.focus_set()
    root.mainloop()
    return 0


if __name__ == "__main__":  # 便于源码调试: python settings_ui.py
    import sys

    cp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("region_config.json")
    raise SystemExit(run_gui(cp))
