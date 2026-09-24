#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""hotkey.py — 纯 ctypes 实现的 Windows 全局热键（零第三方依赖）

为什么不用 keyboard 库：
    keyboard 0.13.5（2020 年后未更新）在 Python 3.13/3.14 上钩子会**静默失效** ——
    add_hotkey() 不报错，但回调永远不会被触发（实测：注入按键时原生钩子收到 21 次事件，
    keyboard 库收到 0 次）。本模块用 WH_KEYBOARD_LL 自己实现，不依赖任何第三方包。

自测（不装任何东西，直接跑）：
    python hotkey.py            # 打印所有按键
    python hotkey.py f8         # 只打印 f8 / ctrl+alt+s 等指定组合
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
PM_REMOVE = 0x0001

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

# --------------------------------------------------------------------------- #
# 键名 -> 虚拟键码
# --------------------------------------------------------------------------- #
MODIFIER_VKS = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "shift": 0x10,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
}

_NAME2VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "spacebar": 0x20, "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22, "pagedown": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "prtsc": 0x2C, "printscreen": 0x2C, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64, "num5": 0x65,
    "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _i in range(1, 25):
    _NAME2VK[f"f{_i}"] = 0x6F + _i  # f1=0x70 ... f24=0x87
for _c in "abcdefghijklmnopqrstuvwxyz":
    _NAME2VK[_c] = ord(_c.upper())
for _d in "0123456789":
    _NAME2VK[_d] = ord(_d)

MODIFIER_VKS_LIST = (0x10, 0x11, 0x12, 0x5B, 0x5C)


def parse_combo(combo: str):
    """'ctrl+alt+s' -> (frozenset({0x11,0x12}), 0x53)"""
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not parts:
        raise ValueError("空热键")
    mods, main = set(), None
    for p in parts:
        if p in MODIFIER_VKS:
            mods.add(MODIFIER_VKS[p])
        elif p in _NAME2VK:
            main = _NAME2VK[p]
        else:
            raise ValueError(f"无法识别的键名: {p!r} (可用: f1-f24 / a-z / 0-9 / ctrl / alt / shift / win 等)")
    if main is None:
        raise ValueError(f"热键 {combo!r} 只有修饰键, 缺少主键")
    if main in MODIFIER_VKS_LIST:
        raise ValueError(f"热键 {combo!r} 的主键不能是修饰键")
    return frozenset(mods), main


def modifiers_down() -> set:
    """当前真实按下的修饰键(不依赖钩子里的 flags, 更可靠)。"""
    down = set()
    for vk in MODIFIER_VKS_LIST:
        if user32.GetAsyncKeyState(vk) & 0x8000:
            down.add(vk)
    return down


class HotkeyListener:
    """在独立线程里装 WH_KEYBOARD_LL, 命中的热键丢进队列由工作线程执行。"""

    def __init__(self, logger=None, debug: bool = False):
        self._log = logger or (lambda m: print(m, flush=True))
        self.debug = debug
        self._rules: dict[str, tuple[frozenset, int, object]] = {}  # combo -> (mods, vk, cb)
        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._hook = None
        self._proc = None          # 必须持有引用, 否则回调被 GC
        self._thread = None
        self._worker = None
        self._stop = threading.Event()
        self._down: set = set()    # 已按下的主键, 用于吃掉自动重复
        self._lock = threading.Lock()
        self.last_error: str | None = None

    # ---------------- 对外 API ----------------
    def add(self, combo: str, callback) -> None:
        mods, vk = parse_combo(combo)
        with self._lock:
            self._rules[str(combo).strip().lower()] = (mods, vk, callback)

    def remove(self, combo: str) -> None:
        with self._lock:
            self._rules.pop(str(combo).strip().lower(), None)

    def set_hotkeys(self, mapping: dict) -> None:
        with self._lock:
            self._rules.clear()
        for combo, cb in (mapping or {}).items():
            if combo:
                self.add(combo, cb)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._work, daemon=True, name="hotkey-worker")
        self._worker.start()
        self._thread = threading.Thread(target=self._install, daemon=True, name="hotkey-hook")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._hook)

    # ---------------- 内部 ----------------
    def _install(self) -> None:
        @HOOKPROC
        def proc(n_code, w_param, l_param):
            if n_code == 0:
                try:
                    kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    self._dispatch(w_param, kb.vkCode)
                except Exception as exc:  # 钩子里绝不抛异常
                    self._log(f"[hotkey] 回调异常: {exc}")
                return user32.CallNextHookEx(None, n_code, w_param, l_param)
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = proc
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not self._hook:
            self.last_error = f"SetWindowsHookEx 失败, GetLastError={ctypes.get_last_error()}（多为权限/安全软件拦截）"
            self._log(f"[hotkey] {self.last_error}")
            return
        self._log("[hotkey] 全局键盘钩子已安装")
        msg = wintypes.MSG()
        while not self._stop.is_set():
            # 低层键盘钩子必须在装钩子的线程里跑消息循环
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.005)

    def _dispatch(self, w_param: int, vk: int) -> None:
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        if self.debug:
            self._log(f"[key] vk=0x{vk:02X} {'down' if is_down else 'up'}")
        if not is_down:
            self._down.discard(vk)
            return
        if vk in self._down:  # 自动重复
            return
        self._down.add(vk)
        mods_now = modifiers_down()
        with self._lock:
            rules = list(self._rules.items())
        for combo, (mods, rule_vk, cb) in rules:
            if vk == rule_vk and mods_now == mods:
                self._queue.put((combo, cb))
                break

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                combo, cb = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                cb()
            except Exception as exc:
                self._log(f"[hotkey] 执行 {combo} 的处理函数出错: {exc}")


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    listener = HotkeyListener(debug=target is None)
    if target:
        listener.add(target, lambda: print(f"HIT {target} @ {time.strftime('%H:%M:%S')}", flush=True))
        print(f"自测: 请按 {target}（Ctrl+C 退出）")
    else:
        print("自测: 直接打印所有按键（Ctrl+C 退出）")
    listener.start()
    time.sleep(0.3)
    if not listener.alive():
        print(f"[x] 钩子安装失败: {listener.last_error}")
        return 1
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        listener.stop()
        print("已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
