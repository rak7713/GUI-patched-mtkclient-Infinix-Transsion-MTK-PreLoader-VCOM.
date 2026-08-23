#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X6833B Unbrick Tool v2 — удобный GUI для восстановления Infinix Note 30 (MT6789).

Запуск:  python UnbrickTool.py
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unbrick_settings.json")

# этапы: ключ, подпись
STAGES = [
    ("detect",   "🔍", "Поиск PreLoader VCOM"),
    ("sync",     "🤝", "Хендшейк"),
    ("da1",      "📦", "Загрузка DA"),
    ("jump",     "🚀", "Прыжок в DA"),
    ("cmdstart", "📡", "CMD:START от DA"),
    ("sla",      "🔑", "SLA Transsion"),
    ("da2",      "📦", "DA stage 2"),
    ("gpt",      "🗂", "Таблица разделов"),
    ("write",    "✍", "Запись vendor_boot_a"),
    ("done",     "🏁", "Готово!"),
]

HINTS = {
    "idle":     "Нажмите «ПОЧИНИТЬ» — программа сама ловит окна PreLoader и повторяет попытки.",
    "detect":   "Жду окно PreLoader… Телефон циклится? Если чёрный экран — зажмите питание на 10 сек.",
    "sync":     "Связываюсь с прелоадером…",
    "da1":      "Загружаю Download Agent (~400 КБ, пару секунд)…",
    "jump":     "Прыжок в DA…",
    "cmdstart": "Жду приветствие DA…",
    "sla":      "Проходим защиту Transsion встроенной подписью…",
    "da2":      "Загружаю основной DA…",
    "write":    "ПИШУ vendor_boot_a! НЕ ОТКЛЮЧАЙТЕ КАБЕЛЬ!",
    "done":     "ГОТОВО! Отключите кабель и включите телефон кнопкой.",
}


def patch_specs():
    specs = {}

    specs["seriallib"] = [
        {"name": "WinError31 fix: timeout guard",
         "old": "        self.device.timeout = timeout\n",
         "new": ("        if self.device.timeout != timeout:\n"
                 "            self.device.timeout = timeout\n"),
         "marker": "if self.device.timeout != timeout:"},
        {"name": "connect(): быстрое открытие без скана comports",
         "old": ('        ports = self.detectdevices()\n'
                 '        if ports:\n'
                 '            if self.portname != "DETECT":\n'
                 '                if self.portname not in ports:\n'
                 '                    self.info("{} not in detected ports: {}".format(self.portname, ports))\n'
                 '                    return False\n'
                 '                else:\n'
                 '                    port = ports[ports.index(self.portname)]\n'
                 '            else:\n'
                 '                port = ports[0]\n'
                 '            self.debug("Got port: {}, initializing".format(port))\n'
                 '            self.device = serial.Serial(port=port, baudrate=115200, bytesize=serial.EIGHTBITS,\n'
                 '                                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,\n'
                 '                                        timeout=500,\n'
                 '                                        xonxoff=False, dsrdtr=False, rtscts=False)\n'
                 '            self.portname = port\n'
                 '        else:\n'
                 '            return False\n'),
         "new": ('        port = None\n'
                 '        if self.portname not in (None, "", "DETECT"):\n'
                 '            port = self.portname\n'
                 '        else:\n'
                 '            ports = self.detectdevices()\n'
                 '            if ports:\n'
                 '                port = ports[0]\n'
                 '        if port is None:\n'
                 '            return False\n'
                 '        self.debug("Got port: {}, initializing".format(port))\n'
                 '        dev = None\n'
                 '        for attempt in range(20):\n'
                 '            try:\n'
                 '                dev = serial.Serial(port=port, baudrate=115200, bytesize=serial.EIGHTBITS,\n'
                 '                                    parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,\n'
                 '                                    timeout=500,\n'
                 '                                    xonxoff=False, dsrdtr=False, rtscts=False)\n'
                 '                break\n'
                 '            except Exception as e:\n'
                 '                self.debug(f"Port {port} open attempt {attempt} failed: {e}")\n'
                 '                time.sleep(0.02)\n'
                 '        if dev is None:\n'
                 '            return False\n'
                 '        self.device = dev\n'
                 '        self.portname = port\n'),
         "marker": "for attempt in range(20):"},
    ]

    specs["port"] = [
        {"name": "Port.serialportname сохраняется",
         "old": ('            self.cdc = SerialClass(portconfig=portconfig, loglevel=loglevel, devclass=10)\n'
                 '            self.cdc.setportname(serialportname)\n'),
         "new": ('            self.cdc = SerialClass(portconfig=portconfig, loglevel=loglevel, devclass=10)\n'
                 '            self.cdc.setportname(serialportname)\n'
                 '            self.serialportname = serialportname\n'),
         "marker": "self.serialportname = serialportname"},
    ]

    gr_old = (
        "    def get_response(self, raw: bool = False) -> str:\n"
        "        sync = self.usbread(4 * 3)\n"
        "        if len(sync) == 4 * 3:\n"
        "            if int.from_bytes(sync[:4], 'little') == 0xfeeeeeef:\n"
        "                if int.from_bytes(sync[4:8], 'little') == 0x1:\n"
        "                    length = int.from_bytes(sync[8:12], 'little')\n"
        "                    data = self.usbread(length)\n"
        "                    if len(data) == length:\n"
        "                        if raw:\n"
        "                            return data\n"
        "                        return data.rstrip(b\"\\x00\").decode('utf-8')\n"
        "        return \"\"\n"
    )
    gr_new = (
        "    def get_response(self, raw: bool = False) -> str:\n"
        "        import time as _t\n"
        "        cdc = self.mtk.port.cdc\n"
        "        def _waiting():\n"
        "            try:\n"
        "                return cdc.device.in_waiting if cdc.device is not None else 0\n"
        "            except Exception:\n"
        "                return 0\n"
        "        sync = bytearray()\n"
        "        deadline = _t.time() + 8\n"
        "        while len(sync) < 12:\n"
        "            n = _waiting()\n"
        "            if n:\n"
        "                sync.extend(self.usbread(min(n, 12 - len(sync))))\n"
        "                continue\n"
        "            if _t.time() > deadline:\n"
        "                break\n"
        "            _t.sleep(0.02)\n"
        "        if len(sync) == 12 and int.from_bytes(sync[:4], 'little') == 0xfeeeeeef \\\n"
        "                and int.from_bytes(sync[4:8], 'little') == 0x1:\n"
        "            length = int.from_bytes(sync[8:12], 'little')\n"
        "            data = bytearray()\n"
        "            ddeadline = _t.time() + 15\n"
        "            while len(data) < length and _t.time() < ddeadline:\n"
        "                n = _waiting()\n"
        "                if n:\n"
        "                    data.extend(self.usbread(min(n, length - len(data))))\n"
        "                    continue\n"
        "                _t.sleep(0.02)\n"
        "            if len(data) == length:\n"
        "                if raw:\n"
        "                    return data\n"
        "                return data.rstrip(b\"\\x00\").decode('utf-8')\n"
        "        return \"\"\n"
    )
    specs["xml_lib"] = [
        {"name": "get_response(): байтовый поллинг",
         "old": gr_old, "new": gr_new,
         "marker": "deadline = _t.time() + 8"},
        {"name": "upload_da1(): ожидание CMD:START",
         "old": ('                if self.mtk.preloader.jump_da(da1address):\n'
                 '                    cmd, result = self.get_command_result()\n'
                 '                    if cmd == "CMD:START":\n'
                 '                        self.setup_env()\n'
                 '                        self.setup_hw_init()\n'
                 '                        self.setup_host_info()\n'
                 '                        return True\n'
                 '                    else:\n'
                 '                        return False\n'),
         "new": ('                if self.mtk.preloader.jump_da(da1address):\n'
                 '                    import time as _t\n'
                 '                    cdc = self.mtk.port.cdc\n'
                 '                    got_start = False\n'
                 '                    deadline = _t.time() + 20\n'
                 '                    while _t.time() < deadline:\n'
                 '                        try:\n'
                 '                            n = cdc.device.in_waiting\n'
                 '                        except Exception:\n'
                 '                            n = 0\n'
                 '                        if n >= 12:\n'
                 '                            _t.sleep(0.05)\n'
                 '                            cmd, result = self.get_command_result()\n'
                 '                            if cmd == "CMD:START":\n'
                 '                                got_start = True\n'
                 '                                break\n'
                 '                        _t.sleep(0.05)\n'
                 '                    if got_start:\n'
                 '                        self.setup_env()\n'
                 '                        self.setup_hw_init()\n'
                 '                        self.setup_host_info()\n'
                 '                        return True\n'
                 '                    else:\n'
                 '                        self.error("No CMD:START from DA within 20s.")\n'
                 '                        return False\n'),
         "marker": "got_start = True"},
        {"name": "check_sla(): защита от bool",
         "old": ('        data = self.get_sys_property(key="DA.SLA", length=0x200000)\n'
                 '        data = data.decode(\'utf-8\')\n'),
         "new": ('        data = self.get_sys_property(key="DA.SLA", length=0x200000)\n'
                 '        if data is None or data is False:\n'
                 '            return False\n'
                 '        data = data.decode(\'utf-8\')\n'),
         "marker": "if data is None or data is False:"},
    ]
    return specs


PATCH_FILES = {
    "seriallib": ("mtkclient", "Library", "Connection", "seriallib.py"),
    "port":      ("mtkclient", "Library", "Port.py"),
    "xml_lib":   ("mtkclient", "Library", "DA", "xmlflash", "xml_lib.py"),
}


def apply_patches(mtk_dir):
    applied, skipped, failed = [], [], []
    specs = patch_specs()
    for key, pairs in specs.items():
        path = os.path.join(mtk_dir, *PATCH_FILES[key])
        if not os.path.exists(path):
            for p in pairs:
                failed.append(p["name"] + f" (нет файла {path})")
            continue
        with open(path, "r", encoding="utf-8") as rf:
            src = rf.read()
        orig = src
        for p in pairs:
            if p["marker"] in src:
                skipped.append(p["name"])
            elif p["old"] in src:
                src = src.replace(p["old"], p["new"], 1)
                applied.append(p["name"])
            else:
                failed.append(p["name"] + " (шаблон не найден)")
        if src != orig:
            bak = path + ".orig"
            if not os.path.exists(bak):
                with open(bak, "w", encoding="utf-8") as wf:
                    wf.write(orig)
            with open(path, "w", encoding="utf-8") as wf:
                wf.write(src)
    return applied, skipped, failed


# ============================================================================

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("X6833B Unbrick Tool")
        root.geometry("980x760")
        root.minsize(900, 680)
        root.configure(bg="#1e1f24")

        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.stop_flag = threading.Event()
        self.proc = None
        self.attempt = 0
        self.t_attempt = None
        self.current_stage = "idle"

        self.stage_rows = {}
        self.pct_var = tk.DoubleVar(value=0)

        self._build_style()
        self._build_ui()
        self._load_settings()
        self.root.after(120, self._poll_queue)
        self.root.after(500, self._auto_phone_poll)

    # ------------------------------- style ----------------------------------
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        BG = "#1e1f24"; CARD = "#272930"; FG = "#e8e8ec"; ACC = "#4da3ff"
        root = self.root
        root.configure(bg=BG)
        st.configure(".", background=BG, foreground=FG, fieldbackground=CARD)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Card.TLabel", background=CARD, foreground=FG)
        st.configure("TButton", background="#33363f", foreground=FG, borderwidth=0, padding=8)
        st.map("TButton", background=[("active", "#40444d")])
        st.configure("Go.TButton", background="#2e7d32", foreground="white", padding=(18, 10),
                     font=("Segoe UI", 11, "bold"))
        st.map("Go.TButton", background=[("active", "#388e3c")])
        st.configure("Stop.TButton", background="#b34700", foreground="white", padding=(14, 10))
        st.map("Stop.TButton", background=[("active", "#c9560a")])
        st.configure("TEntry", fieldbackground="#15161a", foreground=FG, insertcolor=FG)
        st.configure("Horizontal.TProgressbar", background=ACC, troughbackground="#15161a",
                     borderwidth=0)
        st.configure("TLabelframe", background=BG, foreground=FG, borderwidth=0)
        st.configure("TLabelframe.Label", background=BG, foreground="#9aa0aa")

    # -------------------------------- ui ------------------------------------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # --- верхняя панель: телефон / попытка / таймер ---
        topbar = tk.Frame(self.root, bg="#1e1f24")
        topbar.pack(fill="x", padx=12, pady=(10, 2))
        self.lbl_phone_dot = tk.Label(topbar, text="⚪", font=("Segoe UI", 13), bg=topbar["bg"], fg="#888888")
        self.lbl_phone_dot.pack(side="left")
        self.lbl_phone = tk.Label(topbar, text="Телефон: проверяю…", font=("Segoe UI", 11, "bold"),
                                  bg=topbar["bg"], fg="#cccccc")
        self.lbl_phone.pack(side="left", padx=(6, 20))
        self.lbl_attempt = tk.Label(topbar, text="", font=("Segoe UI", 10), bg=topbar["bg"], fg="#9aa0aa")
        self.lbl_attempt.pack(side="right")
        self.lbl_timer = tk.Label(topbar, text="", font=("Consolas", 10), bg=topbar["bg"], fg="#9aa0aa")
        self.lbl_timer.pack(side="right", padx=20)

        # --- большой статус-баннер ---
        self.banner = tk.Frame(self.root, bg="#33363f", height=64)
        self.banner.pack(fill="x", padx=12, pady=6)
        self.lbl_banner = tk.Label(self.banner, text="ГОТОВ К РАБОТЕ", font=("Segoe UI", 17, "bold"),
                                   bg=self.banner["bg"], fg="white")
        self.lbl_banner.pack(expand=True)
        self.set_banner("ГОТОВ К РАБОТЕ", "#33363f")

        # прогресс
        pbframe = tk.Frame(self.root, bg="#1e1f24")
        pbframe.pack(fill="x", padx=16)
        self.pb = ttk.Progressbar(pbframe, variable=self.pct_var, maximum=100)
        self.pb.pack(fill="x")
        self.lbl_pct = tk.Label(pbframe, text="0%", font=("Consolas", 9), bg="#1e1f24", fg="#9aa0aa")
        self.lbl_pct.pack(anchor="e")

        # --- середина: слева этапы, справа лог ---
        mid = tk.Frame(self.root, bg="#1e1f24")
        mid.pack(fill="both", expand=True, padx=12, pady=6)

        left = tk.Frame(mid, bg="#272930", width=300)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text="ХОД ОПЕРАЦИИ", font=("Segoe UI", 9, "bold"), bg="#272930",
                 fg="#9aa0aa").pack(anchor="w", padx=14, pady=(10, 6))

        self.stage_rows = {}
        for i, (key, icon, title) in enumerate(STAGES):
            row = tk.Frame(left, bg="#272930")
            row.pack(fill="x", padx=10, pady=1)
            dot = tk.Label(row, text="○", font=("Segoe UI", 11), width=2, bg=row["bg"], fg="#666666")
            dot.pack(side="left")
            lbl_icon = tk.Label(row, text=icon, font=("Segoe UI Emoji", 11), width=2, bg=row["bg"])
            lbl_icon.pack(side="left")
            lbl_title = tk.Label(row, text=title, font=("Segoe UI", 10), bg=row["bg"],
                                 fg="#777777", anchor="w")
            lbl_title.pack(side="left", fill="x", expand=True)
            self.stage_rows[key] = {"dot": dot, "title": lbl_title}

        hintbox = tk.Frame(left, bg="#202227")
        hintbox.pack(side="bottom", fill="x", padx=8, pady=8)
        tk.Label(hintbox, text="ПОДСКАЗКА", font=("Segoe UI", 8, "bold"), bg=hintbox["bg"],
                 fg="#7f8794").pack(anchor="w", padx=8, pady=(6, 0))
        self.lbl_hint = tk.Label(hintbox, text=HINTS["idle"], font=("Segoe UI", 9), wraplength=250,
                                 justify="left", bg=hintbox["bg"], fg="#c3c8cf")
        self.lbl_hint.pack(anchor="w", padx=8, pady=(2, 8))

        right = tk.LabelFrame(mid, text=" Лог ", bg="#1e1f24", fg="#9aa0aa")
        right.pack(side="left", fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(right, font=("Consolas", 9), bg="#15161a", fg="#d6d6dc",
                                             insertbackground="#ffffff", relief="flat")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.configure(state="disabled")

        # --- пути ---
        paths = ttk.LabelFrame(self.root, text="Файлы")
        paths.pack(fill="x", padx=12, pady=(6, 2))
        self.var_mtk = tk.StringVar(); self.var_da = tk.StringVar(); self.var_vb = tk.StringVar()
        for i, (lbl, var, fn) in enumerate([
            ("Папка mtkclient:", self.var_mtk, lambda: self._pick_dir(self.var_mtk)),
            ("DA_BR.bin:", self.var_da, lambda: self._pick_file(self.var_da)),
            ("vendor_boot.img:", self.var_vb, lambda: self._pick_file(self.var_vb))]):
            ttk.Label(paths, text=lbl).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            ttk.Entry(paths, textvariable=var, width=90).grid(row=i, column=1, sticky="we", padx=6)
            ttk.Button(paths, text="…", width=3, command=fn).grid(row=i, column=2)
        paths.columnconfigure(1, weight=1)

        # --- кнопки ---
        btns = tk.Frame(self.root, bg="#1e1f24")
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text="Проверить телефон", command=self.check_device).pack(side="left")
        ttk.Button(btns, text="Пропатчить mtkclient", command=self.patch_now).pack(side="left", padx=8)
        self.btn_stop = ttk.Button(btns, text="■ Стоп", style="Stop.TButton",
                                   command=self.stop_fix, state="disabled")
        self.btn_stop.pack(side="right")
        self.btn_start = ttk.Button(btns, text="▶  ПОЧИНИТЬ ТЕЛЕФОН", style="Go.TButton",
                                    command=self.start_fix)
        self.btn_start.pack(side="right", padx=10)

    # ------------------------------ helpers ---------------------------------
    def set_banner(self, text, color):
        self.banner.configure(bg=color)
        self.lbl_banner.configure(bg=color, text=text)

    def set_stage(self, key, state):
        self.q.put(("stage", key, state))
        if key in HINTS and state == "active":
            self.q.put(("hint", HINTS[key]))

    def set_hint(self, text):
        self.q.put(("hint", text))

    def logln(self, msg, tag=None):
        self.q.put(("log", msg, tag))

    def set_phone(self, present):
        self.q.put(("phone", present))

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, msg, tag = item
                    color = {"err": "#ff6b6b", "ok": "#69db7c", "warn": "#ffa94d",
                             "big": "#74c0fc"}.get(tag, "#d6d6dc")
                    ts = time.strftime("%H:%M:%S")
                    self.log.configure(state="normal")
                    self.log.insert("end", f"[{ts}] ", "#7f8794")
                    self.log.tag_config("#7f8794", foreground="#7f8794")
                    self.log.insert("end", msg + "\n", tag or "norm")
                    self.log.tag_config(tag or "norm", foreground=color)
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "stage":
                    _, key, state = item
                    if key in self.stage_rows:
                        r = self.stage_rows[key]
                        cfg = {"idle": ("○", "#666666", "#777777"),
                               "active": ("◉", "#4da3ff", "#e8e8ec"),
                               "ok": ("●", "#51cf66", "#51cf66"),
                               "fail": ("✖", "#ff6b6b", "#ff6b6b")}[state]
                        r["dot"].configure(text=cfg[0], fg=cfg[1])
                        r["title"].configure(fg=cfg[2])
                    self.current_stage = key
                elif kind == "pct":
                    self.pct_var.set(item[1])
                    self.lbl_pct.configure(text=f"{item[1]:.1f}%")
                elif kind == "phone":
                    present = item[1]
                    self.lbl_phone_dot.configure(text="🟢" if present else "🔴",
                                                 fg="#51cf66" if present else "#ff6b6b")
                    self.lbl_phone.configure(
                        text="Телефон: ПОДКЛЮЧЁН (PreLoader VCOM)" if present
                        else "Телефон: не найден (выключен / нет окна)",
                        fg="#51cf66" if present else "#ff6b6b")
                elif kind == "hint":
                    self.lbl_hint.configure(text=item[1])
                elif kind == "banner":
                    self.set_banner(item[1], item[2])
                elif kind == "attempt":
                    self.lbl_attempt.configure(text=f"Попытка: #{item[1]}")
                elif kind == "timer":
                    self.lbl_timer.configure(text=item[1])
                elif kind == "buttons":
                    running = item[1]
                    self.btn_start.configure(state="disabled" if running else "normal")
                    self.btn_stop.configure(state="normal" if running else "disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _auto_phone_poll(self):
        def run():
            present = self.phone_present()
            self.set_phone(present)
        threading.Thread(target=run, daemon=True).start()
        self.root.after(5000, self._auto_phone_poll)

    def _tick_timer(self):
        if self.t_attempt and not self.stop_flag.is_set():
            el = int(time.time() - self.t_attempt)
            self.q.put(("timer", f"⏱ {el//60:02d}:{el%60:02d}"))
            self.root.after(1000, self._tick_timer)

    # --------------------------- device check -------------------------------
    def phone_present(self):
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_PnPEntity | ? { $_.PNPDeviceID -like '*VID_0E8D*' } "
                 "| Measure-Object).Count"],
                capture_output=True, text=True, timeout=15)
            s = out.stdout.strip()
            return s.isdigit() and int(s) > 0
        except Exception:
            return False

    def check_device(self):
        def run():
            present = self.phone_present()
            self.logln("Телефон: " + ("ПОДКЛЮЧЁН (PreLoader VCOM)" if present else "НЕ НАЙДЕН"),
                       "ok" if present else "warn")
            self.set_phone(present)
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------- patcher --------------------------------
    def patch_now(self):
        mtk_dir = self.var_mtk.get().strip()
        if not os.path.exists(os.path.join(mtk_dir, "mtk.py")):
            messagebox.showerror("Ошибка", "Сначала укажите папку mtkclient (где лежит mtk.py)!")
            return
        self._save_settings()

        def run():
            self.logln("Применяю патчи к mtkclient…", "big")
            a, s, f = apply_patches(mtk_dir)
            for n in a:
                self.logln(f"  ✔ применён: {n}", "ok")
            for n in s:
                self.logln(f"  • уже стоит: {n}")
            for n in f:
                self.logln(f"  ✖ НЕ УДАЛОСЬ: {n}", "err")
            if not f:
                self.logln("Все патчи на месте — mtkclient готов к работе.", "ok")

        threading.Thread(target=run, daemon=True).start()

    # --------------------------------- fix ----------------------------------
    MARKERS = [
        (re.compile(r"Handshake successful"), "sync"),
        (re.compile(r"Successfully uploaded stage 1"), "da1"),
        (re.compile(r"Jumping to 0x[0-9a-f]+: ok"), "jump"),
        (re.compile(r"DA Stage 1 successfully loaded|CMD:START"), "cmdstart"),
        (re.compile(r"SLA Signature was accepted|DA XML SLA is disabled"), "sla"),
        (re.compile(r"Uploading stage 2|Successfully uploaded stage 2"), "da2"),
        (re.compile(r"Wrote .*to sector"), "write"),
        (re.compile(r"All is done"), "done"),
    ]

    ACTIVATE_ORDER = [
        ("Waiting for PreLoader VCOM", "detect"),
        ("Disabling Watchdog", "sync"),
        ("Uploading xflash stage 1", "da1"),
        ("jumping ..", "jump"),
        ("Running sla auth", "sla"),
        ("Uploading stage 2", "da2"),
        ("Handling da commands", "write"),
    ]

    def start_fix(self):
        mtk_dir = self.var_mtk.get().strip()
        da = self.var_da.get().strip()
        vb = self.var_vb.get().strip()
        if not (os.path.exists(os.path.join(mtk_dir, "mtk.py")) and os.path.exists(da) and os.path.exists(vb)):
            messagebox.showerror("Ошибка", "Заполните все три пути!")
            return
        self._save_settings()
        self.stop_flag.clear()
        self.attempt = 0
        self.q.put(("buttons", True))
        for key, _, _ in STAGES:
            self.set_stage(key, "idle")
        t = threading.Thread(target=self._fix_loop, args=(mtk_dir, da, vb), daemon=True)
        t.start()

    def stop_fix(self):
        self.stop_flag.set()
        self.logln("Останавливаю по запросу…", "warn")
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        self.q.put(("buttons", False))

    def _fix_loop(self, mtk_dir, da, vb):
        mtk_py = os.path.join(mtk_dir, "mtk.py")
        workdir = os.path.dirname(vb) or "."
        while not self.stop_flag.is_set():
            self.attempt += 1
            self.q.put(("attempt", self.attempt))
            self.t_attempt = time.time()
            self.root.after(0, self._tick_timer)
            self.logln(f"— Попытка #{self.attempt} —", "big")
            ok = self._one_attempt(mtk_py, da, vb, workdir)
            if ok:
                self.set_banner("🎉 ГОТОВО! ТЕЛЕФОН ПОЧИНЕН!", "#2e7d32")
                self.set_stage("done", "ok")
                self.set_hint(HINTS["done"])
                self.logln("*** vendor_boot записан. Отключите кабель, включите телефон. ***", "ok")
                break
            if self.stop_flag.is_set():
                break
            self.logln("Тишина. Жду появления PreLoader (или power-cycle от вас)…")
            waited = 0
            while not self.phone_present() and waited < 300 and not self.stop_flag.is_set():
                time.sleep(3); waited += 3
        self.q.put(("buttons", False))

    def _one_attempt(self, mtk_py, da, vb, workdir) -> bool:
        cmd = [sys.executable, "-u", mtk_py, "w", "vendor_boot_a", vb,
               "--loader", da, "--stock", "--serialport", "COM3", "--loglevel", "1"]
        env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"
        try:
            self.proc = subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         env=env, text=True, encoding="utf-8", errors="replace",
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except Exception as e:
            self.logln(f"Не удалось запустить mtkclient: {e}", "err")
            return False

        success = False
        start = time.time()
        assert self.proc.stdout is not None
        for line in iter(self.proc.stdout.readline, ""):
            if self.stop_flag.is_set():
                self.proc.kill(); break
            line = line.rstrip("\r\n")
            if not line:
                continue
            mp = re.search(r"(\d+(?:\.\d+)?)%\s*(?:Upload|Writ)", line)
            if mp:
                self.set_pct(float(mp.group(1)))
                continue
            if line.startswith("Progress:") or line.startswith("Done |"):
                continue
            self.logln(line)

            hit_stage = None
            for pat, st in self.ACTIVATE_ORDER:
                if pat in line:
                    hit_stage = st; break
            if hit_stage:
                self.set_stage(hit_stage, "active")
                banners = {"detect": ("🔍 ЛОВЛЮ ОКНО PRELOADER…", "#1c6ea4"),
                           "da1":    ("📦 ЗАГРУЗКА DA…", "#1c6ea4"),
                           "jump":   ("🚀 ПРЫЖОК В DA…", "#1c6ea4"),
                           "sla":    ("🔑 ОБХОД SLA…", "#7048a8"),
                           "da2":    ("📦 ЗАГРУЗКА DA STAGE 2…", "#1c6ea4"),
                           "write":  ("✍ ЗАПИСЬ VENDOR_BOOT — НЕ ТРОГАЙТЕ!", "#b34700")}
                if hit_stage in banners:
                    self.q.put(("banner", *banners[hit_stage]))

            for rx, key in self.MARKERS:
                if rx.search(line):
                    self.set_stage(key, "ok")
                    msgs = {"sync": "Хендшейк OK", "da1": "DA загружен", "jump": "Прыжок подтверждён!",
                            "cmdstart": "CMD:START получен!", "sla": "SLA пройден!",
                            "da2": "Stage 2 готов", "write": "*** ЗАПИСЬ ВЫПОЛНЕНА ***",
                            "done": "Сеанс завершён"}
                    self.logln("✔ " + msgs[key], "ok")
                    if key == "cmdstart":
                        self.set_banner("📡 DA ЖИВОЙ — ПРОДОЛЖАЮ…", "#1c6ea4")
                    if key == "sla":
                        self.set_banner("🔑 SLA ПРОЙДЕН!", "#2e7d32")
                    if key == "write":
                        self.set_pct(100)
                        success = True
                        self.set_banner("✅ ЗАПИСАНО! ПЕРЕЗАГРУЖАЮ ТЕЛЕФОН…", "#2e7d32")
                    break

            if "Error" in line or "Failed" in line or "Wrong" in line:
                self.logln("   ↑ проблема в этой попытке", "warn")

            if time.time() - start > 600 and not success:
                self.logln(">10 мин на попытку — убиваю процесс.", "warn")
                self.proc.kill(); break
        try:
            self.proc.wait(timeout=10)
        except Exception:
            try: self.proc.kill()
            except Exception: pass
        return success

    # ------------------------------ settings --------------------------------
    def _pick_dir(self, var):
        d = filedialog.askdirectory(title="Выбрать папку")
        if d: var.set(d); self._save_settings()

    def _pick_file(self, var):
        f = filedialog.askopenfilename()
        if f: var.set(f); self._save_settings()

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as rf:
                s = json.load(rf)
            self.var_mtk.set(s.get("mtk", ""))
            self.var_da.set(s.get("da", ""))
            self.var_vb.set(s.get("vb", ""))
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as wf:
                json.dump({"mtk": self.var_mtk.get(), "da": self.var_da.get(),
                           "vb": self.var_vb.get()}, wf)
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
