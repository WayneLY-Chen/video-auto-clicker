# Copyright (C) 2026 Wayne Chen
# SPDX-License-Identifier: GPL-3.0-or-later
# 本程式以 GNU GPL v3 授權，詳見 LICENSE 檔案。

"""
影片播放/暫停 定時連點器

流程（影片先自己按播放，再按「開始」）：
    播放 N 分鐘 → 點一下（暫停）→ 等 M 秒 → 點一下（播放）→ 重複

快捷鍵（全域，視窗不在前面也有效）：
    F6 = 開始 / 停止
    F8 = 記錄目前滑鼠位置為點擊位置

只用 Python 內建模組，不需要安裝任何套件。
"""

import ctypes
import json
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk

# ---------- Windows API ----------
user32 = ctypes.windll.user32

# 讓座標在有縮放（125%、150%）的螢幕上也正確
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_SPACE = 0x20
VK_F6 = 0x75
VK_F8 = 0x77

# 打包成 exe 時存在 exe 旁邊，否則存在 .pyw 旁邊
_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
SETTINGS_FILE = _BASE_DIR / "settings.json"
# 圖示：打包時會被包進 exe（sys._MEIPASS），沒打包時讀 .pyw 旁邊的 icon.ico
ICON_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.ico"


def get_cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_at(x, y, restore_cursor):
    old = get_cursor_pos()
    user32.SetCursorPos(x, y)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    if restore_cursor:
        time.sleep(0.03)
        user32.SetCursorPos(*old)


def press_space():
    user32.keybd_event(VK_SPACE, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_SPACE, 0, KEYEVENTF_KEYUP, 0)


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def fmt(secs):
    secs = max(0, int(secs + 0.999))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------- 主程式 ----------
class App:
    TICK_MS = 50

    def __init__(self, root):
        self.root = root
        root.title("影片定時連點器")
        root.resizable(False, False)
        if ICON_FILE.exists():
            try:
                root.iconbitmap(default=str(ICON_FILE))
            except tk.TclError:
                pass

        self.mode = tk.StringVar(value="click")
        self.x = tk.IntVar(value=0)
        self.y = tk.IntVar(value=0)
        self.play_h = tk.IntVar(value=0)
        self.play_m = tk.IntVar(value=10)
        self.play_s = tk.IntVar(value=0)
        self.pause_s = tk.IntVar(value=2)
        self.repeat = tk.IntVar(value=0)
        self.restore = tk.BooleanVar(value=True)
        self.topmost = tk.BooleanVar(value=True)

        self.running = False
        self.phase = "play"
        self.deadline = 0.0
        self.cycles = 0
        self.pick_deadline = None
        self.prev_keys = {VK_F6: False, VK_F8: False}

        self.load_settings()
        self.build_ui()
        self.apply_topmost()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(self.TICK_MS, self.tick)

    # ----- UI -----
    def build_ui(self):
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.grid()

        # 動作方式
        box = ttk.LabelFrame(frm, text="動作方式", padding=6)
        box.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Radiobutton(box, text="滑鼠左鍵點擊指定位置", variable=self.mode,
                        value="click", command=self.update_mode).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(box, text="按鍵盤空白鍵（瀏覽器要在最前面）", variable=self.mode,
                        value="space", command=self.update_mode).grid(row=1, column=0, sticky="w")

        # 點擊位置
        self.pos_box = ttk.LabelFrame(frm, text="點擊位置", padding=6)
        self.pos_box.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(self.pos_box, text="X").grid(row=0, column=0)
        ttk.Entry(self.pos_box, textvariable=self.x, width=7).grid(row=0, column=1, padx=(2, 8))
        ttk.Label(self.pos_box, text="Y").grid(row=0, column=2)
        ttk.Entry(self.pos_box, textvariable=self.y, width=7).grid(row=0, column=3, padx=(2, 8))
        ttk.Button(self.pos_box, text="點一下選位置", command=self.start_click_pick).grid(row=0, column=4, padx=2)
        ttk.Button(self.pos_box, text="3秒後選位置", command=self.start_pick).grid(row=0, column=5, padx=2)
        ttk.Button(self.pos_box, text="測試點一下", command=self.test_action).grid(row=0, column=6, padx=2)
        ttk.Checkbutton(self.pos_box, text="點完把滑鼠移回原位", variable=self.restore).grid(
            row=1, column=0, columnspan=7, sticky="w", pady=(4, 0))
        ttk.Label(self.pos_box, text="小技巧：把滑鼠移到播放/暫停鈕上按 F8 也能記錄位置",
                  foreground="gray").grid(row=2, column=0, columnspan=7, sticky="w")

        # 時間
        tbox = ttk.LabelFrame(frm, text="時間設定", padding=6)
        tbox.grid(row=2, column=0, sticky="ew", **pad)

        ttk.Label(tbox, text="播放多久後暫停：").grid(row=0, column=0, sticky="w")
        self.spin(tbox, self.play_h, 0, 99).grid(row=0, column=1)
        ttk.Label(tbox, text="時").grid(row=0, column=2, padx=(2, 6))
        self.spin(tbox, self.play_m, 0, 59).grid(row=0, column=3)
        ttk.Label(tbox, text="分").grid(row=0, column=4, padx=(2, 6))
        self.spin(tbox, self.play_s, 0, 59).grid(row=0, column=5)
        ttk.Label(tbox, text="秒").grid(row=0, column=6, padx=(2, 6))

        ttk.Label(tbox, text="暫停多久後繼續：").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.spin(tbox, self.pause_s, 1, 3600).grid(row=1, column=5, pady=(6, 0))
        ttk.Label(tbox, text="秒").grid(row=1, column=6, padx=(2, 6), pady=(6, 0))

        ttk.Label(tbox, text="重複幾輪（0 = 無限）：").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.spin(tbox, self.repeat, 0, 9999).grid(row=2, column=5, pady=(6, 0))
        ttk.Label(tbox, text="輪").grid(row=2, column=6, padx=(2, 6), pady=(6, 0))

        # 狀態
        sbox = ttk.Frame(frm)
        sbox.grid(row=3, column=0, sticky="ew", **pad)
        self.phase_lbl = ttk.Label(sbox, text="待命中", font=("Microsoft JhengHei UI", 12, "bold"))
        self.phase_lbl.grid(row=0, column=0, sticky="w")
        self.count_lbl = ttk.Label(sbox, text="--:--", font=("Consolas", 28, "bold"))
        self.count_lbl.grid(row=1, column=0, sticky="w")
        self.info_lbl = ttk.Label(sbox, text="先讓影片開始播放，再按「開始」或 F6", foreground="gray")
        self.info_lbl.grid(row=2, column=0, sticky="w")

        # 按鈕
        bbox = ttk.Frame(frm)
        bbox.grid(row=4, column=0, sticky="ew", **pad)
        self.start_btn = ttk.Button(bbox, text="開始 (F6)", command=self.toggle, width=16)
        self.start_btn.grid(row=0, column=0)
        ttk.Checkbutton(bbox, text="視窗永遠在最上層", variable=self.topmost,
                        command=self.apply_topmost).grid(row=0, column=1, padx=12)

        self.update_mode()

    @staticmethod
    def spin(parent, var, lo, hi):
        return ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi, width=5, justify="center")

    def update_mode(self):
        state = "normal" if self.mode.get() == "click" else "disabled"
        for w in self.pos_box.winfo_children():
            try:
                w.configure(state=state)
            except tk.TclError:
                pass

    def apply_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())

    # ----- 動作 -----
    def do_action(self):
        if self.mode.get() == "click":
            click_at(self.x.get(), self.y.get(), self.restore.get())
        else:
            press_space()

    def test_action(self):
        try:
            self.do_action()
        except tk.TclError:
            messagebox.showerror("錯誤", "X / Y 要填整數")

    def start_pick(self):
        self.pick_deadline = time.monotonic() + 3

    def start_click_pick(self):
        """蓋一層半透明的全螢幕視窗，使用者點哪裡就記錄哪裡。
        點擊會被這層吃掉，不會真的點到底下的影片。"""
        vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))  # 所有螢幕合起來的範圍
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.geometry(f"{vw}x{vh}+{vx}+{vy}")
        ov.attributes("-alpha", 0.35)
        ov.attributes("-topmost", True)
        ov.configure(bg="black", cursor="crosshair")
        tip = tk.Label(ov, text="在播放/暫停鈕的位置點一下（按 Esc 或右鍵取消）",
                       fg="white", bg="black", font=("Microsoft JhengHei UI", 22, "bold"))
        tip.place(x=-vx + 40, y=-vy + 40)  # 放在主螢幕左上角

        def pick(_event):
            ov.destroy()
            self.record_pos()

        def cancel(_event):
            ov.destroy()
            self.info_lbl.config(text="已取消選取位置")

        for w in (ov, tip):
            w.bind("<Button-1>", pick)
            w.bind("<Button-3>", cancel)
        ov.bind("<Escape>", cancel)
        ov.focus_force()
        self.info_lbl.config(text="請在畫面上點一下要點擊的位置…")

    def record_pos(self):
        x, y = get_cursor_pos()
        self.x.set(x)
        self.y.set(y)
        self.info_lbl.config(text=f"已記錄點擊位置：({x}, {y})")

    # ----- 開始 / 停止 -----
    def read_settings(self):
        try:
            play = self.play_h.get() * 3600 + self.play_m.get() * 60 + self.play_s.get()
            pause = self.pause_s.get()
            repeat = self.repeat.get()
            if self.mode.get() == "click":
                self.x.get(), self.y.get()
        except tk.TclError:
            messagebox.showerror("錯誤", "欄位裡只能填整數")
            return None
        if play <= 0:
            messagebox.showerror("錯誤", "播放時間至少要 1 秒")
            return None
        if pause < 1:
            # 太短的話兩下會被當成「連點兩下」，很多播放器會變全螢幕
            messagebox.showerror("錯誤", "暫停時間至少要 1 秒")
            return None
        if repeat < 0:
            messagebox.showerror("錯誤", "重複次數不能是負數")
            return None
        return play, pause, repeat

    def toggle(self):
        if self.running:
            self.stop("已手動停止")
        else:
            self.start()

    def start(self):
        cfg = self.read_settings()
        if cfg is None:
            return
        self.play_secs, self.pause_secs, self.repeat_n = cfg
        self.save_settings()
        self.running = True
        self.cycles = 0
        self.phase = "play"
        self.deadline = time.monotonic() + self.play_secs
        self.start_btn.config(text="停止 (F6)")
        self.update_info()

    def stop(self, msg):
        self.running = False
        self.start_btn.config(text="開始 (F6)")
        self.phase_lbl.config(text="待命中", foreground="")
        self.count_lbl.config(text="--:--")
        self.info_lbl.config(text=msg)

    def update_info(self):
        total = "無限" if self.repeat_n == 0 else str(self.repeat_n)
        self.info_lbl.config(text=f"已完成 {self.cycles} / {total} 輪")

    # ----- 每 50ms 執行一次 -----
    def tick(self):
        now = time.monotonic()

        # 全域快捷鍵（偵測按下的那一瞬間）
        for vk in (VK_F6, VK_F8):
            down = key_down(vk)
            if down and not self.prev_keys[vk]:
                if vk == VK_F6:
                    self.toggle()
                elif self.mode.get() == "click":
                    self.record_pos()
            self.prev_keys[vk] = down

        # 選取位置倒數
        if self.pick_deadline is not None:
            left = self.pick_deadline - now
            if left <= 0:
                self.pick_deadline = None
                self.record_pos()
            else:
                self.info_lbl.config(text=f"把滑鼠移到播放/暫停鈕上…{left:.1f} 秒")

        # 主計時
        if self.running:
            if now >= self.deadline:
                self.do_action()
                if self.phase == "play":
                    self.phase = "pause"
                    self.deadline = now + self.pause_secs
                else:
                    self.cycles += 1
                    if self.repeat_n and self.cycles >= self.repeat_n:
                        self.stop(f"完成 {self.cycles} 輪，已停止")
                    else:
                        self.phase = "play"
                        self.deadline = now + self.play_secs
                        self.update_info()
            if self.running:
                if self.phase == "play":
                    self.phase_lbl.config(text="▶ 播放中，倒數後暫停", foreground="#1a7f37")
                else:
                    self.phase_lbl.config(text="⏸ 暫停中，倒數後繼續播放", foreground="#c2410c")
                self.count_lbl.config(text=fmt(self.deadline - now))

        self.root.after(self.TICK_MS, self.tick)

    # ----- 設定存檔 -----
    def settings_vars(self):
        return {
            "mode": self.mode, "x": self.x, "y": self.y,
            "play_h": self.play_h, "play_m": self.play_m, "play_s": self.play_s,
            "pause_s": self.pause_s, "repeat": self.repeat,
            "restore": self.restore, "topmost": self.topmost,
        }

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, var in self.settings_vars().items():
            if key in data:
                try:
                    var.set(data[key])
                except tk.TclError:
                    pass

    def save_settings(self):
        data = {}
        for key, var in self.settings_vars().items():
            try:
                data[key] = var.get()
            except tk.TclError:
                pass
        try:
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def on_close(self):
        self.save_settings()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
