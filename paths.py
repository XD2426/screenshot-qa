#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""paths.py — 统一解析「配置 / 数据 / 资源」路径。

同时支持两种运行形态:
    1. 源码运行 (python app.py)          -> 用脚本所在目录
    2. PyInstaller 打包 (ScreenshotQA.exe) -> 用 %APPDATA%\\ScreenshotQA

约定:
    - 配置文件查找顺序: exe/脚本 同目录 region_config.json  ->  %APPDATA%\\ScreenshotQA\\region_config.json
      (前者存在即"便携模式", 把配置放 exe 旁边就能整体拷走)
    - 只读资源 (图标/默认配置模板) 打进 exe, 用 resource_dir() 取。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ScreenshotQA"
VERSION = "1.2.0"
CONFIG_FILENAME = "region_config.json"
DEFAULT_TEMPLATE = "region_config.default.json"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打出的 exe 里。"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """exe 所在目录(打包后) / 源码目录(开发时)。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """只读资源目录: 打包后是 PyInstaller 解包出的临时目录 (_MEIPASS)。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """用户可写数据目录: %APPDATA%\\ScreenshotQA (打包后), 脚本目录(开发时)。"""
    if not is_frozen():
        return Path(__file__).resolve().parent
    roaming = os.environ.get("APPDATA")
    if roaming:
        return Path(roaming) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def default_config_path() -> Path:
    """配置文件路径(见模块头部的查找顺序)。"""
    portable = app_dir() / CONFIG_FILENAME
    if portable.exists():
        return portable
    return data_dir() / CONFIG_FILENAME


def template_path() -> Path | None:
    """打包时随 exe 一起带的默认配置模板(用于「首次初始化」)。"""
    p = resource_dir() / DEFAULT_TEMPLATE
    return p if p.exists() else None


def write_default_config(target: Path, defaults: dict, seed_from: Path | None = None) -> Path:
    """把默认配置写到 target; seed_from 存在时优先用它(迁移旧版标定结果)。"""
    import json

    target.parent.mkdir(parents=True, exist_ok=True)
    cfg = dict(defaults)
    cfg.setdefault("region", None)
    if seed_from is not None and seed_from.exists():
        try:
            old = json.loads(seed_from.read_text(encoding="utf-8"))
            for k, v in old.items():
                if k in cfg and v is not None:
                    cfg[k] = v
        except Exception:
            pass
    target.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
