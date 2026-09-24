#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_icon.py — 生成 app.ico(多尺寸)。仅打包时需要, 运行时不需要。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def render(size: int) -> Image.Image:
    s = 1024  # 先在 1024 上画, 再缩放, 保证边缘平滑
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底
    bg = (24, 32, 44, 255)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=bg)
    # 顶部高光渐变
    for i in range(int(s * 0.5)):
        a = int(26 * (1 - i / (s * 0.5)))
        d.line([(0, i), (s, i)], fill=(90, 150, 230, a))

    # 四角取景框
    m = int(s * 0.20)
    arm = int(s * 0.16)
    w = int(s * 0.058)
    c = (235, 243, 252, 255)
    for (cx, cy, dx, dy) in ((m, m, 1, 1), (s - m, m, -1, 1), (m, s - m, 1, -1), (s - m, s - m, -1, -1)):
        d.line([(cx, cy), (cx + dx * arm, cy)], fill=c, width=w)
        d.line([(cx, cy), (cx, cy + dy * arm)], fill=c, width=w)

    # 中央红点(录制/自动)
    r = int(s * 0.115)
    cx = cy = s // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 66, 62, 255))

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "app.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = render(1024)
    base.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"[OK] {out}  ({out.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
