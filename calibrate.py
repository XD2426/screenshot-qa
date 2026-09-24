#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""calibrate.py — 拖框标定截图区域, 以"相对百分比坐标"写入 region_config.json

用法:
    python calibrate.py
    python calibrate.py --config "D:\\screenshot-qa\\region_config.json"

操作:
    左键拖拽         选取区域
    Enter / 双击 / 右键   确认并保存
    Esc              取消退出
    Shift(拖拽时)    锁定为正方形

说明:
    - 坐标按"虚拟桌面(所有显示器拼起来的整体)"的宽高换算成百分比,
      因此换分辨率/换窗口位置后依然可用(前提是题目区在屏幕上的相对位置不变)。
    - 只会更新 region_config.json 里的 region 字段, 其它配置保持不变。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path

try:  # 统一路径解析(源码运行 / PyInstaller 打包后都能用)
    from paths import default_config_path as _default_config_path
except Exception:  # 单文件使用时兜底
    def _default_config_path() -> Path:
        return Path(__file__).resolve().with_name("region_config.json")


DEFAULT_CONFIG = _default_config_path()
MIN_SIZE = 8  # 小于该像素的选区视为无效


def set_dpi_aware() -> None:
    """按物理像素工作, 保证 Tk 坐标与 mss 抓屏坐标 1:1 对齐。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def load_config(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] 配置文件解析失败, 将重建: {exc}")
    return {}


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Selector:
    def __init__(self, config_path: Path):
        import tkinter as tk
        from PIL import Image, ImageTk
        import mss as mss_mod

        self.tk = tk
        self.config_path = config_path

        sct_cls = getattr(mss_mod, "MSS", None) or getattr(mss_mod, "mss")
        with sct_cls() as sct:
            mon = sct.monitors[0]  # 0 = 虚拟桌面(所有显示器)
            shot = sct.grab(mon)
        self.mon = dict(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        self.root.configure(bg="black")

        self.photo = ImageTk.PhotoImage(img)
        self.canvas = tk.Canvas(
            self.root, width=mon["width"], height=mon["height"],
            highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        self.hint_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#101418", outline="")
        self.hint = self.canvas.create_text(
            0, 0, anchor="nw", fill="#e8eef5", font=("Microsoft YaHei UI", 12),
            text=(
                "拖拽鼠标选择“题目区域” —— 回车/双击/右键 = 保存   Esc = 取消   Shift = 正方形\n"
                "提示: 只框住题干和选项本身, 尽量不含无关界面, 识别更准"
            ),
        )
        self.band = self.canvas.create_rectangle(0, 0, 0, 0, outline="#ff3b30", width=2, fill="")
        self.shade = [
            self.canvas.create_rectangle(0, 0, 0, 0, fill="#000000", stipple="gray50", outline="")
            for _ in range(4)
        ]
        self.size_tag = self.canvas.create_text(
            0, 0, anchor="nw", fill="#ff3b30", font=("Consolas", 12),
            text="", state="hidden",
        )

        self.x0 = self.y0 = self.x1 = self.y1 = 0
        self.dragging = False
        self.rect = None

        # 让提示条居中
        self.root.update_idletasks()
        bbox = self.canvas.bbox(self.hint)
        w = bbox[2] - bbox[0] + 24
        h = bbox[3] - bbox[1] + 18
        x = (mon["width"] - w) / 2
        self.canvas.coords(self.hint_bg, x, 18, x + w, 18 + h)
        self.canvas.coords(self.hint, x + 12, 27)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.confirm())
        self.canvas.bind("<Button-3>", lambda _e: self.confirm())
        self.root.bind("<Escape>", lambda _e: self.cancel())
        self.root.bind("<Return>", lambda _e: self.confirm())
        self.root.focus_force()

    # ---------- 事件 ----------
    def on_press(self, event) -> None:
        self.dragging = True
        self.x0, self.y0 = event.x, event.y
        self.x1, self.y1 = event.x, event.y
        self.update_view()

    def on_drag(self, event) -> None:
        if not self.dragging:
            return
        if event.state & 0x0001:  # Shift 锁正方形
            dx, dy = event.x - self.x0, event.y - self.y0
            side = max(abs(dx), abs(dy))
            self.x1 = self.x0 + (side if dx >= 0 else -side)
            self.y1 = self.y0 + (side if dy >= 0 else -side)
        else:
            self.x1, self.y1 = event.x, event.y
        self.update_view()

    def on_release(self, event) -> None:
        self.dragging = False
        self.update_view()

    def norm(self):
        x1, x2 = sorted((self.x0, self.x1))
        y1, y2 = sorted((self.y0, self.y1))
        return x1, y1, x2, y2

    def update_view(self) -> None:
        x1, y1, x2, y2 = self.norm()
        w, h = x2 - x1, y2 - y1
        W, H = self.mon["width"], self.mon["height"]
        self.canvas.coords(self.band, x1, y1, x2, y2)
        # 四块遮罩, 只留选区透亮
        self.canvas.coords(self.shade[0], 0, 0, W, y1)
        self.canvas.coords(self.shade[1], 0, y2, W, H)
        self.canvas.coords(self.shade[2], 0, y1, x1, y2)
        self.canvas.coords(self.shade[3], x2, y1, W, y2)
        # 尺寸标签
        tx, ty = x1, y1 - 22 if y1 > 30 else y2 + 6
        self.canvas.coords(self.size_tag, tx, ty)
        self.canvas.itemconfigure(self.size_tag, text=f"{w} x {h}  ({x1},{y1})", state="normal")
        self.canvas.tag_raise(self.band)
        self.canvas.tag_raise(self.size_tag)
        self.rect = (x1, y1, x2, y2)

    def confirm(self) -> None:
        if not self.rect:
            return
        x1, y1, x2, y2 = self.rect
        w, h = x2 - x1, y2 - y1
        if w < MIN_SIZE or h < MIN_SIZE:
            print("[x] 选区太小, 请重新拖拽")
            return
        mon = self.mon
        region = {
            "left_pct": round(x1 / mon["width"], 6),
            "top_pct": round(y1 / mon["height"], 6),
            "width_pct": round(w / mon["width"], 6),
            "height_pct": round(h / mon["height"], 6),
            "screen_ref": {
                "left": mon["left"], "top": mon["top"],
                "width": mon["width"], "height": mon["height"],
            },
            "pixel_rect_ref": {
                "left": x1 + mon["left"], "top": y1 + mon["top"],
                "width": w, "height": h,
            },
            "calibrated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        cfg = load_config(self.config_path)
        cfg["region"] = region
        save_config(self.config_path, cfg)

        print(f"[OK] 已写入 {self.config_path}")
        print(f"     相对选区: left={region['left_pct']:.4f} top={region['top_pct']:.4f} "
              f"w={region['width_pct']:.4f} h={region['height_pct']:.4f}")
        print(f"     当前分辨率下绝对像素: {region['pixel_rect_ref']}")
        self.root.destroy()

    def cancel(self) -> None:
        print("[i] 已取消, 配置未修改")
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    ap = argparse.ArgumentParser(description="拖框标定截图区域(相对百分比坐标)")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="region_config.json 路径")
    args = ap.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    set_dpi_aware()

    try:
        sel = Selector(config_path)
    except ImportError as exc:
        print(f"[x] 缺少依赖: {exc}\n    请先执行: pip install mss pillow")
        return 1
    except Exception as exc:
        print(f"[x] 无法启动标定窗口: {exc}")
        return 1

    sel.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
