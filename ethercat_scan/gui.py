"""Tkinter 图形界面。

零第三方依赖即可运行；热力图需要 numpy+matplotlib，缺失时自动降级为纯日志。
扫描在后台线程运行，通过队列把结果回传给主线程刷新界面 (Tk 非线程安全)。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config import AxisConfig, ScanConfig
from .motion import SimulatedAxis
from .power_meter import Pm100usbPowerMeter, SimulatedPowerMeter
from .scanner import Scanner, ScanResult

try:
    import numpy as np
    import matplotlib
    matplotlib.use("TkAgg")
    # 使用系统中文字体，避免标题/标签中的中文渲染成乱码方框
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


class ScanApp:
    # 需要持久化的配置项 (status/progress/pos/limits 为运行时状态，不保存)
    _CONFIG_KEYS = [
        "ifname", "dry_run",
        "x_alias", "y_alias", "x_ppmm", "y_ppmm", "x_reverse", "y_reverse",
        "x_home_method", "y_home_method",
        "x_min", "x_max", "y_min", "y_max",
        "x_start", "x_stop", "x_step", "y_start", "y_stop", "y_step",
        "dwell", "samples", "snake", "home",
        "show_pos_on_map",
        "pm_use_real", "pm_resource", "pm_wavelength",
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.events = queue.Queue()
        self.master = None
        self.meter = None
        self.scanner = None
        self._state = "idle"

        # 热力图相关
        self._fig = None
        self._ax = None
        self._im = None
        self._cbar = None
        self._canvas = None
        self._z = None
        self._target_marker = None   # 热力图上的目标位置标记 (空心圆)
        self._pos_marker = None      # 热力图上的实际位置标记 (+)

        # 位置标尺相关
        self._ruler_x = None
        self._ruler_y = None
        self._x_range = None
        self._y_range = None
        self._cur_pos = (0.0, 0.0)
        self._target_pos = (0.0, 0.0)   # 目标位置 (位置同步: 点动/扫描命令的都是它)

        # 手动点动 / 自检
        self._jog_buttons = []
        self.btn_selftest = None

        self._build_vars()
        # 记录各控件出厂默认值，供"恢复默认设置"使用 (须在 _load_config 之前采集)
        self._defaults = {k: v.get() for k, v in self.v.items()}
        self._build_ui()
        # 参数控件各自的启用态 (Combobox=readonly，其余=normal)，锁定后据此恢复
        self._param_states = {id(w): w.cget("state") for w in self._param_widgets()}
        self._load_config()
        # 扫描参数变化时刷新默认热力图；位置标记开关变化时立即显隐
        self._bind_config_traces()
        self._init_heatmap()
        self._log("就绪。默认模拟运行(dry-run)；接真实硬件时取消勾选并填网卡名。")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._poll)
        self.root.after(200, self._poll_pos)

    # ---------------- 变量 ----------------
    def _build_vars(self):
        v = {
            "ifname": tk.StringVar(value=""),
            "dry_run": tk.BooleanVar(value=True),
            "x_alias": tk.StringVar(value="0"),
            "y_alias": tk.StringVar(value="1"),
            "x_ppmm": tk.StringVar(value="200"),
            "y_ppmm": tk.StringVar(value="200"),
            "x_reverse": tk.BooleanVar(value=False),
            "y_reverse": tk.BooleanVar(value=False),
            "x_home_method": tk.StringVar(value="17"),
            "y_home_method": tk.StringVar(value="17"),
            "x_min": tk.StringVar(value=""),
            "x_max": tk.StringVar(value=""),
            "y_min": tk.StringVar(value=""),
            "y_max": tk.StringVar(value=""),
            "x_start": tk.StringVar(value="-10"),
            "x_stop": tk.StringVar(value="10"),
            "x_step": tk.StringVar(value="1"),
            "y_start": tk.StringVar(value="-10"),
            "y_stop": tk.StringVar(value="10"),
            "y_step": tk.StringVar(value="1"),
            "dwell": tk.StringVar(value="0.1"),
            "samples": tk.StringVar(value="1"),
            "snake": tk.BooleanVar(value=True),
            "home": tk.BooleanVar(value=False),
            "show_pos_on_map": tk.BooleanVar(value=True),
            "pm_use_real": tk.BooleanVar(value=False),
            "pm_resource": tk.StringVar(value=""),
            "pm_wavelength": tk.StringVar(value=""),
            "jog_step": tk.StringVar(value="1"),
            "status": tk.StringVar(value="未连接"),
            "progress": tk.DoubleVar(value=0.0),
            "pos": tk.StringVar(value="X: 0.000 mm   Y: 0.000 mm"),
            "pos_x": tk.StringVar(value="X: 0.000 mm"),
            "pos_y": tk.StringVar(value="Y: 0.000 mm"),
            "range_x": tk.StringVar(value="未设置"),
            "range_y": tk.StringVar(value="未设置"),
            "limits": tk.StringVar(value="限位: —"),
        }
        self.v = v

    def _num(self, key, default, cast=float):
        try:
            return cast(self.v[key].get())
        except (ValueError, tk.TclError):
            return default

    def _opt_num(self, key, cast=float):
        """解析可选数值：空串/非法 → None。"""
        s = self.v[key].get().strip()
        if not s:
            return None
        try:
            return cast(s)
        except (ValueError, tk.TclError):
            return None

    # ---------------- 配置持久化 ----------------
    def _config_path(self) -> Path:
        return Path.home() / ".ethercat_scan_config.json"

    def _save_config(self) -> bool:
        """把当前配置写入用户目录 JSON，供下次启动恢复。"""
        try:
            data = {k: self.v[k].get() for k in self._CONFIG_KEYS}
            path = self._config_path()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"配置已保存: {path}")
            return True
        except Exception as e:
            self._log(f"[错误] 保存配置失败: {e}")
            return False

    def _load_config(self):
        """启动时从 JSON 恢复上次配置 (缺失项保持默认)。"""
        try:
            path = self._config_path()
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            for k in self._CONFIG_KEYS:
                if k not in data:
                    continue
                val = data[k]
                if isinstance(self.v[k], tk.BooleanVar):
                    self.v[k].set(bool(val))
                else:
                    self.v[k].set(str(val))
            self._log(f"已加载上次配置: {path}")
        except Exception as e:
            self._log(f"[警告] 加载配置失败，使用默认值: {e}")

    def _on_save_config(self):
        self._save_config()

    def _on_reset_config(self):
        """恢复默认设置：重置所有配置项为出厂默认值，并清除已保存的配置文件。"""
        if not messagebox.askyesno(
                "恢复默认设置",
                "确定将所有设置恢复为默认值并清除已保存的配置文件吗？"):
            return
        for k in self._CONFIG_KEYS:
            self.v[k].set(self._defaults[k])
        try:
            path = self._config_path()
            if path.exists():
                path.unlink()
                self._log(f"已清除配置文件: {path}")
        except Exception as e:
            self._log(f"[错误] 清除配置文件失败: {e}")
        self._log("已恢复默认设置")

    # ---------------- UI ----------------
    def _build_ui(self):
        root = self.root
        root.title("EtherCAT 双轴滑台扫描采集")
        root.geometry("1100x840")
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)

        # 1) 硬件连接 (左) + 功率计 (右)
        fhw = self._fhw = ttk.LabelFrame(root, text="硬件连接")
        fhw.grid(row=0, column=0, sticky="ew", padx=(6, 3), pady=4)
        ttk.Checkbutton(fhw, text="模拟运行 (dry-run)", variable=self.v["dry_run"]).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=4)
        self._lbl(fhw, "网卡", 1, 0)
        ttk.Entry(fhw, textvariable=self.v["ifname"], width=32).grid(
            row=1, column=1, columnspan=3, sticky="w", padx=2)
        self._lbl(fhw, "X 站号", 2, 0)
        ttk.Entry(fhw, textvariable=self.v["x_alias"], width=6).grid(row=2, column=1, sticky="w", padx=2)
        self._lbl(fhw, "Y 站号", 2, 2)
        ttk.Entry(fhw, textvariable=self.v["y_alias"], width=6).grid(row=2, column=3, sticky="w", padx=2)
        self._lbl(fhw, "X 脉冲/mm", 3, 0)
        ttk.Entry(fhw, textvariable=self.v["x_ppmm"], width=10).grid(row=3, column=1, sticky="w", padx=2)
        self._lbl(fhw, "Y 脉冲/mm", 3, 2)
        ttk.Entry(fhw, textvariable=self.v["y_ppmm"], width=10).grid(row=3, column=3, sticky="w", padx=2)
        ttk.Checkbutton(fhw, text="X 反向", variable=self.v["x_reverse"]).grid(row=4, column=1, sticky="w", padx=2)
        ttk.Checkbutton(fhw, text="Y 反向", variable=self.v["y_reverse"]).grid(row=4, column=3, sticky="w", padx=2)

        fpm = self._fpm = ttk.LabelFrame(root, text="功率计 (PM100USB + PD300R)")
        fpm.grid(row=0, column=1, sticky="ew", padx=(3, 6), pady=4)
        ttk.Checkbutton(fpm, text="真实功率计 (PM100USB)", variable=self.v["pm_use_real"]).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=4)
        self._lbl(fpm, "资源名", 1, 0)
        ttk.Entry(fpm, textvariable=self.v["pm_resource"], width=32).grid(row=1, column=1, sticky="w", padx=2)
        self._lbl(fpm, "波长(nm)", 2, 0)
        ttk.Entry(fpm, textvariable=self.v["pm_wavelength"], width=10).grid(row=2, column=1, sticky="w", padx=2)
        ttk.Label(fpm, text="(资源名留空自动搜索；波长留空用探头当前校准)").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=4)

        # 2) 回零与限位 (左) + 扫描参数 (右)
        fhl = self._fhl = ttk.LabelFrame(root, text="回零与限位 (mm，相对原点)")
        fhl.grid(row=1, column=0, sticky="ew", padx=(6, 3), pady=4)
        for r, name in enumerate(["X", "Y"]):
            k = name.lower()
            self._lbl(fhl, f"{name} 回零方式", r, 0)
            ttk.Combobox(fhl, textvariable=self.v[f"{k}_home_method"],
                         values=["17", "18", "24", "29"], state="readonly", width=5).grid(
                row=r, column=1, sticky="w", padx=2)
            self._lbl(fhl, f"{name} 软限位", r, 2)
            ttk.Entry(fhl, textvariable=self.v[f"{k}_min"], width=7).grid(row=r, column=3, sticky="w", padx=2)
            ttk.Label(fhl, text="~").grid(row=r, column=4, sticky="w")
            ttk.Entry(fhl, textvariable=self.v[f"{k}_max"], width=7).grid(row=r, column=5, sticky="w", padx=2)

        fsc = self._fsc = ttk.LabelFrame(root, text="扫描参数 (mm)")
        fsc.grid(row=1, column=1, sticky="ew", padx=(3, 6), pady=4)
        for r, (key, lbl) in enumerate([("start", "起点"), ("stop", "终点"), ("step", "步长")]):
            self._lbl(fsc, f"X {lbl}", r, 0)
            ttk.Entry(fsc, textvariable=self.v[f"x_{key}"], width=7).grid(row=r, column=1, sticky="w", padx=2)
            self._lbl(fsc, f"Y {lbl}", r, 2)
            ttk.Entry(fsc, textvariable=self.v[f"y_{key}"], width=7).grid(row=r, column=3, sticky="w", padx=2)
        self._lbl(fsc, "停留(s)", 0, 4)
        ttk.Entry(fsc, textvariable=self.v["dwell"], width=7).grid(row=0, column=5, sticky="w", padx=2)
        self._lbl(fsc, "每点采样", 1, 4)
        ttk.Entry(fsc, textvariable=self.v["samples"], width=7).grid(row=1, column=5, sticky="w", padx=2)
        ttk.Checkbutton(fsc, text="扫描前回零", variable=self.v["home"]).grid(row=3, column=0, columnspan=2, sticky="w", padx=2)
        ttk.Checkbutton(fsc, text="蛇形", variable=self.v["snake"]).grid(row=3, column=2, columnspan=2, sticky="w", padx=2)
        ttk.Checkbutton(fsc, text="热力图显示位置标记", variable=self.v["show_pos_on_map"]).grid(
            row=4, column=0, columnspan=4, sticky="w", padx=2)

        # 3) 控制按钮 (运动控制 左 / 数据 右)
        fctl = ttk.Frame(root)
        fctl.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        fmove = ttk.Frame(fctl)
        fmove.pack(side="left")
        self.btn_connect = ttk.Button(fmove, text="连接", command=self._on_connect)
        self.btn_home = ttk.Button(fmove, text="回零", command=self._on_home)
        self.btn_start = ttk.Button(fmove, text="开始扫描", command=self._on_start)
        self.btn_stop = ttk.Button(fmove, text="停止", command=self._on_stop, state="disabled")
        self.btn_selftest = ttk.Button(fmove, text="自检", command=self._on_selftest, state="disabled")
        for b in (self.btn_connect, self.btn_home, self.btn_start, self.btn_stop, self.btn_selftest):
            b.pack(side="left", padx=3)
        fdata = ttk.Frame(fctl)
        fdata.pack(side="right")
        self.btn_save = ttk.Button(fdata, text="保存CSV", command=self._on_save_csv, state="disabled")
        self.btn_saveplot = ttk.Button(fdata, text="保存热力图", command=self._on_save_plot, state="disabled")
        self.btn_savecfg = ttk.Button(fdata, text="保存配置", command=self._on_save_config)
        self.btn_resetcfg = ttk.Button(fdata, text="恢复默认", command=self._on_reset_config)
        for b in (self.btn_save, self.btn_saveplot, self.btn_savecfg, self.btn_resetcfg):
            b.pack(side="left", padx=3)
        self.btn_home.config(state="disabled")
        self.btn_start.config(state="disabled")

        # 4) 进度
        fprog = ttk.Frame(root)
        fprog.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
        ttk.Label(fprog, textvariable=self.v["limits"]).pack(side="left", padx=(0, 16))
        ttk.Label(fprog, textvariable=self.v["status"]).pack(side="left")
        ttk.Progressbar(fprog, variable=self.v["progress"], maximum=100).pack(
            side="right", fill="x", expand=True, padx=8)

        # 5) 实时位置与软限位 / 手动点动 (左，紧凑) + 热力图/日志 (右，占满) 同一行
        frow = ttk.Frame(root)
        frow.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)
        root.rowconfigure(4, weight=1)
        frow.columnconfigure(0, weight=0)   # 左列按内容宽度，保持紧凑
        frow.columnconfigure(1, weight=1)   # 右列(热力图+日志)占满剩余宽度
        frow.rowconfigure(0, weight=1)

        fpos = ttk.LabelFrame(frow, text="实时位置与软限位 / 手动点动")
        fpos.grid(row=0, column=0, sticky="nsw", padx=(0, 6))
        fpos.columnconfigure(1, weight=1)   # 位置/软限位列占满，点动按钮靠右
        bg = root.cget("background")

        # X 轴: 名称 + 位置 + 点动按钮一行，软限位与标尺在其下方 (纵向布局，适合窄列)
        ttk.Label(fpos, text="X", width=2).grid(row=0, column=0, sticky="w", padx=(4, 2))
        ttk.Label(fpos, textvariable=self.v["pos_x"], width=13).grid(row=0, column=1, sticky="w", padx=2)
        btn_xn = ttk.Button(fpos, text="-", width=3, command=lambda: self._on_jog("X", -1))
        btn_xn.grid(row=0, column=2, padx=(2, 1))
        btn_xp = ttk.Button(fpos, text="+", width=3, command=lambda: self._on_jog("X", +1))
        btn_xp.grid(row=0, column=3, padx=(1, 4))
        ttk.Label(fpos, textvariable=self.v["range_x"]).grid(row=1, column=1, sticky="w", padx=2)
        self._ruler_x = tk.Canvas(fpos, width=100, height=26, highlightthickness=0, bg=bg)
        self._ruler_x.grid(row=2, column=0, columnspan=4, sticky="ew", padx=(4, 6))

        # Y 轴 (同 X)
        ttk.Label(fpos, text="Y", width=2).grid(row=3, column=0, sticky="w", padx=(4, 2))
        ttk.Label(fpos, textvariable=self.v["pos_y"], width=13).grid(row=3, column=1, sticky="w", padx=2)
        btn_yn = ttk.Button(fpos, text="-", width=3, command=lambda: self._on_jog("Y", -1))
        btn_yn.grid(row=3, column=2, padx=(2, 1))
        btn_yp = ttk.Button(fpos, text="+", width=3, command=lambda: self._on_jog("Y", +1))
        btn_yp.grid(row=3, column=3, padx=(1, 4))
        ttk.Label(fpos, textvariable=self.v["range_y"]).grid(row=4, column=1, sticky="w", padx=2)
        self._ruler_y = tk.Canvas(fpos, width=100, height=26, highlightthickness=0, bg=bg)
        self._ruler_y.grid(row=5, column=0, columnspan=4, sticky="ew", padx=(4, 6))
        self._jog_buttons = [btn_xn, btn_xp, btn_yn, btn_yp]

        # 点动步长
        ttk.Label(fpos, text="点动步长(mm)").grid(row=6, column=1, sticky="e", padx=2)
        self._jog_step_entry = ttk.Entry(fpos, textvariable=self.v["jog_step"], width=8)
        self._jog_step_entry.grid(row=6, column=2, columnspan=2, sticky="w", padx=2)

        # 6) 热力图 + 日志
        fbottom = ttk.Frame(frow)
        fbottom.grid(row=0, column=1, sticky="nsew")
        fbottom.columnconfigure(0, weight=1)
        fbottom.rowconfigure(0, weight=1)

        if HAVE_MPL:
            self._fig = Figure(figsize=(5, 4), dpi=100)
            self._ax = self._fig.add_subplot(111)
            # imshow/色标由 _init_heatmap 只创建一次，之后复用，保证色标大小稳定
            self._canvas = FigureCanvasTkAgg(self._fig, master=fbottom)
            self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        else:
            ttk.Label(fbottom, text="(未装 numpy/matplotlib，无热力图预览)").grid(
                row=0, column=0, sticky="nw")

        self.log_text = scrolledtext.ScrolledText(fbottom, width=40, height=18, state="disabled")
        self.log_text.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        fbottom.columnconfigure(1, weight=0)

    def _lbl(self, parent, text, row, col):
        ttk.Label(parent, text=text).grid(row=row, column=col, sticky="e", padx=2, pady=2)

    # ---------------- 日志 / 状态 ----------------
    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _param_widgets(self):
        """返回可编辑的参数控件 (Entry/Checkbutton/Combobox/Spinbox)。

        硬件连接/功率计/回零限位/扫描参数四个区 + 点动步长输入框。
        """
        out = []
        for f in (self._fhw, self._fpm, self._fhl, self._fsc):
            for w in f.winfo_children():
                if w.winfo_class() in ("TEntry", "TCheckbutton", "TCombobox", "TSpinbox"):
                    out.append(w)
        out.append(self._jog_step_entry)
        return out

    def _update_param_lock(self):
        """非空闲状态 (扫描/回零/点动/连接中) 锁定参数控件，防止中途修改。"""
        locked = self._state != "idle"
        for w in self._param_widgets():
            w.config(state="disabled" if locked else self._param_states[id(w)])

    def _update_buttons(self):
        """集中管理按钮互锁 (单一状态源)。

        依据 self._state ∈ {idle, connecting, homing, jog, scanning, selftest} /
        是否已连接 / 有无数据，统一刷新各按钮的可用状态。
        参数控件同步锁定，避免扫描等运行中被改动。
        """
        state = self._state
        self._update_param_lock()
        connected = self.scanner is not None
        have_data = connected and len(self.scanner.result) > 0
        idle = connected and state == "idle"

        self.btn_connect.config(
            state="normal" if state == "idle" else "disabled",
            text="断开" if (state == "idle" and connected) else "连接")
        self.btn_home.config(state="normal" if idle else "disabled")
        self.btn_start.config(state="normal" if idle else "disabled")
        # 停止在扫描/自检中可用; 回零与点动是短促阻塞操作，不提供假停止按钮
        self.btn_stop.config(state="normal" if state in ("scanning", "selftest") else "disabled")
        self.btn_save.config(state="normal" if (idle and have_data) else "disabled")
        self.btn_saveplot.config(state="normal" if (idle and have_data and HAVE_MPL) else "disabled")
        # 保存/恢复配置会改动参数，运行中一并锁定
        self.btn_savecfg.config(state="normal" if state == "idle" else "disabled")
        self.btn_resetcfg.config(state="normal" if state == "idle" else "disabled")
        # 手动点动 + 自检 (仅空闲且已连接时可用)
        for b in self._jog_buttons:
            b.config(state="normal" if idle else "disabled")
        if self.btn_selftest is not None:
            self.btn_selftest.config(state="normal" if idle else "disabled")

    def _set_state(self, state: str):
        self._state = state
        self._update_buttons()

    # ---------------- 位置显示 ----------------
    def _axis_mm(self, ax) -> float:
        return ax.read_actual_position() / (ax.pulses_per_mm * ax.direction)

    def _set_pos(self, x_mm: float, y_mm: float):
        self._cur_pos = (x_mm, y_mm)
        self.v["pos"].set(f"X: {x_mm:.3f} mm   Y: {y_mm:.3f} mm")
        self.v["pos_x"].set(f"X: {x_mm:8.3f} mm")
        self.v["pos_y"].set(f"Y: {y_mm:8.3f} mm")
        self._draw_rulers()

    def _refresh_pos(self):
        """读取两轴实际位置与限位状态。

        空闲时刷新位置/限位/热力图标记；扫描中默认只显示 point 事件的目标坐标，
        避免争用总线，仅当"热力图显示位置标记"开启时才在扫描中读实际位置。
        """
        sc = self.scanner
        if sc is None:
            return
        if self._state == "idle":
            try:
                pos = (self._axis_mm(sc.x), self._axis_mm(sc.y))
                self._set_pos(*pos)
                self._target_pos = pos   # 位置同步: 空闲时目标位置跟随实际位置
                self._set_limits(sc.x, sc.y)
                self._update_map_markers(target=self._target_pos, actual=pos)
            except Exception:
                pass
        elif self._state == "scanning" and self.v["show_pos_on_map"].get():
            try:
                pos = (self._axis_mm(sc.x), self._axis_mm(sc.y))
                self._update_map_markers(actual=pos)
            except Exception:
                pass

    def _set_limits(self, x_ax, y_ax):
        def _fmt(ax):
            st = ax.read_limit_states()
            if st is None:
                return f"{ax.name}[模拟]"
            return (f"{ax.name}[负{'√' if st['neg'] else '·'} "
                    f"正{'√' if st['pos'] else '·'} "
                    f"原点{'√' if st['home'] else '·'}]")
        self.v["limits"].set("限位: " + "  ".join(_fmt(ax) for ax in (x_ax, y_ax)))

    def _update_ranges(self):
        """从当前轴读取软限位区间，刷新区间文本与标尺。"""
        sc = self.scanner
        self._x_range = sc.x.soft_limits if sc is not None else None
        self._y_range = sc.y.soft_limits if sc is not None else None
        for key, rng in (("range_x", self._x_range), ("range_y", self._y_range)):
            if rng and rng[0] is not None and rng[1] is not None:
                self.v[key].set(f"{rng[0]:g} ~ {rng[1]:g} mm")   # 框体标题已含"软限位"，这里不重复前缀，保持窄列
            else:
                self.v[key].set("未设置")
        self._draw_rulers()

    def _draw_rulers(self):
        if self._ruler_x is None or self._ruler_y is None:
            return
        x, y = self._cur_pos
        self._draw_ruler(self._ruler_x, x, self._x_range)
        self._draw_ruler(self._ruler_y, y, self._y_range)

    def _draw_ruler(self, canvas, cur, rng):
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 60 or h < 10:
            return
        lo = hi = None
        if rng:
            lo, hi = rng
        if lo is None or hi is None or hi <= lo:
            canvas.create_text(w // 2, h // 2, text="软限位未设置", anchor="center",
                               font=("", 8), fill="#888")
            return
        m = 28
        x0, x1, y = m, w - m, h // 2
        canvas.create_line(x0, y, x1, y, fill="#bbb")
        canvas.create_line(x0, y - 4, x0, y + 4, fill="#666")
        canvas.create_line(x1, y - 4, x1, y + 4, fill="#666")
        canvas.create_text(x0, y + 10, text=f"{lo:g}", anchor="n", font=("", 8), fill="#666")
        canvas.create_text(x1, y + 10, text=f"{hi:g}", anchor="n", font=("", 8), fill="#666")
        out = cur < lo or cur > hi
        clamped = max(lo, min(hi, cur))
        xc = x0 + (clamped - lo) / (hi - lo) * (x1 - x0)
        color = "#c00" if out else "#06c"
        canvas.create_line(xc, y - 5, xc, y + 5, fill=color, width=2)
        canvas.create_text(xc, y - 8, text=f"{cur:.2f}", anchor="s", font=("", 8), fill=color)

    def _poll_pos(self):
        self._refresh_pos()
        self.root.after(200, self._poll_pos)

    # ---------------- 构建 scanner ----------------
    def _collect_params(self):
        """在主线程读取所有界面参数为普通 dict (Tk 变量只能在主线程访问)。"""
        v = self.v
        return {
            "dry_run": v["dry_run"].get(),
            "ifname": v["ifname"].get().strip(),
            "x_alias": self._num("x_alias", 0, int),
            "y_alias": self._num("y_alias", 1, int),
            "x_ppmm": self._num("x_ppmm", 1000.0),
            "y_ppmm": self._num("y_ppmm", 1000.0),
            "x_reverse": v["x_reverse"].get(),
            "y_reverse": v["y_reverse"].get(),
            "x_home_method": self._num("x_home_method", 17, int),
            "y_home_method": self._num("y_home_method", 17, int),
            "x_min": self._opt_num("x_min"),
            "x_max": self._opt_num("x_max"),
            "y_min": self._opt_num("y_min"),
            "y_max": self._opt_num("y_max"),
            "x_start": self._num("x_start", -10.0),
            "x_stop": self._num("x_stop", 10.0),
            "x_step": self._num("x_step", 1.0),
            "y_start": self._num("y_start", -10.0),
            "y_stop": self._num("y_stop", 10.0),
            "y_step": self._num("y_step", 1.0),
            "dwell": self._num("dwell", 0.1),
            "samples": self._num("samples", 1, int),
            "snake": v["snake"].get(),
            "home": v["home"].get(),
            "pm_use_real": v["pm_use_real"].get(),
            "pm_resource": v["pm_resource"].get().strip(),
            "pm_wavelength": self._opt_num("pm_wavelength"),
        }

    def _scan_config(self, p) -> ScanConfig:
        return ScanConfig(
            x_start=p["x_start"], x_stop=p["x_stop"], x_step=p["x_step"],
            y_start=p["y_start"], y_stop=p["y_stop"], y_step=p["y_step"],
            dwell=p["dwell"],
            n_samples_per_point=p["samples"],
            snake=p["snake"],
            timeout=10.0,
        )

    def _build_scanner(self, p):
        """用普通参数构建 scanner (可在工作线程调用，不碰 Tk)。"""
        cfg = self._scan_config(p)
        # 功率计: 按 GUI 选择模拟光斑或真实 PM100USB (PD300R 探头)
        center = ((cfg.x_start + cfg.x_stop) / 2, (cfg.y_start + cfg.y_stop) / 2)
        if p["pm_use_real"]:
            meter = Pm100usbPowerMeter(resource=p["pm_resource"],
                                       wavelength_nm=p["pm_wavelength"])
        else:
            meter = SimulatedPowerMeter(center=center)
        meter.open()
        self.meter = meter

        xdir = -1 if p["x_reverse"] else 1
        ydir = -1 if p["y_reverse"] else 1
        if p["dry_run"]:
            x = SimulatedAxis("X", pulses_per_mm=p["x_ppmm"], direction=xdir,
                              soft_limits=(p["x_min"], p["x_max"]))
            y = SimulatedAxis("Y", pulses_per_mm=p["y_ppmm"], direction=ydir,
                              soft_limits=(p["y_min"], p["y_max"]))
            self.master = None
        else:
            from .master import EtherCATMaster
            master = EtherCATMaster(p["ifname"])
            master.open()
            master.find_drives()
            master.go_op()
            x = master.make_drive(AxisConfig(name="X", alias=p["x_alias"],
                                             pulses_per_mm=p["x_ppmm"], direction=xdir,
                                             home_method=p["x_home_method"],
                                             soft_limit_min_mm=p["x_min"],
                                             soft_limit_max_mm=p["x_max"]))
            y = master.make_drive(AxisConfig(name="Y", alias=p["y_alias"],
                                             pulses_per_mm=p["y_ppmm"], direction=ydir,
                                             home_method=p["y_home_method"],
                                             soft_limit_min_mm=p["y_min"],
                                             soft_limit_max_mm=p["y_max"]))
            self.master = master

        self.scanner = Scanner(x, y, meter, cfg)

    def _close_devices(self):
        """释放当前主站/功率计，并清除 scanner 引用 (供重连与退出复用)。"""
        for obj in (self.master, self.meter):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self.master = None
        self.meter = None
        self.scanner = None

    def _disconnect(self):
        """主动断开：释放设备、复位状态显示与热力图。"""
        self._close_devices()
        self.v["status"].set("未连接")
        self.v["pos"].set("X: 0.000 mm   Y: 0.000 mm")
        self.v["pos_x"].set("X: 0.000 mm")
        self.v["pos_y"].set("Y: 0.000 mm")
        self.v["limits"].set("限位: —")
        self.v["progress"].set(0.0)
        self._x_range = self._y_range = None
        self._cur_pos = (0.0, 0.0)
        self._target_pos = (0.0, 0.0)
        self._update_ranges()
        self._clear_heatmap()
        self._log("已断开")
        self._update_buttons()

    # ---------------- 动作 ----------------
    def _on_connect(self):
        if self._state != "idle":
            return
        if self.scanner is not None:
            self._disconnect()
            return
        # 连接前先释放可能残留的旧设备，避免句柄泄漏
        self._close_devices()
        p = self._collect_params()
        if p["dry_run"]:
            try:
                self._build_scanner(p)
                self._log("已连接 (模拟轴 + 模拟功率计)")
                self.v["status"].set("已连接(模拟)")
                self._update_ranges()
                self._refresh_pos()
            except Exception as e:
                self._log(f"[错误] {e}")
                self.v["status"].set("未连接")
                messagebox.showerror("连接失败", str(e))
            finally:
                self._update_buttons()
        else:
            self._log("正在连接 EtherCAT ...")
            self.v["status"].set("连接中...")
            self._set_state("connecting")
            threading.Thread(target=self._connect_real, args=(p,), daemon=True).start()

    def _connect_real(self, p):
        try:
            self._build_scanner(p)
            self.events.put(("connected", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _on_home(self):
        if self.scanner is None or self._state != "idle":
            return
        self.scanner._aborted = False
        self._set_state("homing")
        self.v["status"].set("回零中...")
        threading.Thread(target=self._run_home, daemon=True).start()

    def _run_home(self):
        try:
            self.scanner.home()
            self.events.put(("log", "回零完成"))
            self.events.put(("idle", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _on_start(self):
        if self.scanner is None:
            messagebox.showwarning("提示", "请先连接")
            return
        if self._state != "idle":
            return
        # 扫描范围等参数以当前界面为准 (连接时只建立硬件/轴对象，范围在开始时读取)
        p = self._collect_params()
        self.scanner.cfg = self._scan_config(p)
        try:
            self.scanner.validate_soft_limits()
        except RuntimeError as e:
            messagebox.showwarning("软限位越界", str(e))
            return
        self.scanner.result = ScanResult()
        if isinstance(self.meter, SimulatedPowerMeter):
            self.meter.cx = (self.scanner.cfg.x_start + self.scanner.cfg.x_stop) / 2
            self.meter.cy = (self.scanner.cfg.y_start + self.scanner.cfg.y_stop) / 2
        self._init_heatmap()
        self.scanner._aborted = False
        self.v["progress"].set(0)
        self.v["status"].set("扫描中...")
        self._set_state("scanning")
        home = self.v["home"].get()   # 主线程读，避免工作线程访问 Tk
        threading.Thread(target=self._run_scan, args=(home,), daemon=True).start()

    def _run_scan(self, home: bool):
        try:
            self.scanner.prepare()
            if home:
                self.events.put(("log", "回零中..."))
                self.scanner.home()
            self.events.put(("log", "开始扫描..."))
            self.scanner.scan(progress_callback=self._cb_point)
            self.events.put(("done", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _cb_point(self, i, x, y, p, total):
        self.events.put(("point", (i, x, y, p, total)))

    def _on_stop(self):
        if self._state not in ("scanning", "selftest"):
            return
        if self.scanner is not None:
            self.scanner.abort()
        self._log("已请求停止，等待当前动作完成...")

    # ---------------- 手动点动 / 自检 ----------------
    def _on_jog(self, ax_name: str, direction: int):
        if self.scanner is None or self._state != "idle":
            return
        step_mm = self._num("jog_step", 1.0)
        if step_mm <= 0:
            messagebox.showwarning("提示", "点动步长需为正数")
            return
        # 手动点动同样建立在位置同步上: 更新的是目标位置，再绝对定位过去
        tx, ty = self._target_pos
        if ax_name == "X":
            tx += direction * step_mm
        else:
            ty += direction * step_mm
        self._target_pos = (tx, ty)
        self._update_map_markers(target=self._target_pos)
        self._set_state("jog")
        self.v["status"].set(f"{ax_name} 轴点动 {direction * step_mm:+.3f} mm ...")
        ax = self.scanner.x if ax_name == "X" else self.scanner.y
        target_mm = tx if ax_name == "X" else ty
        threading.Thread(target=self._run_jog, args=(ax, target_mm), daemon=True).start()

    def _run_jog(self, ax, target_mm: float):
        try:
            if hasattr(ax, "setup_pp"):
                ax.setup_pp()
            ax.enable()
            target_pul = int(round(target_mm * ax.pulses_per_mm * ax.direction))
            ax.move_abs(target_pul)
            ax.wait_target_reached(10.0)
            self.events.put(("idle", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _on_selftest(self):
        if self.scanner is None or self._state != "idle":
            return
        from .selftest import can_selftest
        if not (can_selftest(self.scanner.x) and can_selftest(self.scanner.y)):
            messagebox.showwarning("提示", "当前轴无硬件开关读取能力 (模拟轴)，无法自检")
            return
        self.scanner._aborted = False
        self._set_state("selftest")
        self.v["status"].set("自检中...")
        threading.Thread(target=self._run_selftest, daemon=True).start()

    def _run_selftest(self):
        from .selftest import run_axis_selftest
        results = []
        try:
            for ax in (self.scanner.x, self.scanner.y):
                self.events.put(("log", f"自检 {ax.name} 轴: 左限位 → 右限位 → 回零 ..."))
                res = run_axis_selftest(ax, should_stop=lambda: self.scanner._aborted)
                mark = "通过" if res.ok else "异常"
                self.events.put(("log", f"{ax.name} 轴自检[{mark}]: {res.detail}"))
                results.append(res)
            self.events.put(("selftest_done", results))
        except Exception as e:
            if self.scanner._aborted:
                self.events.put(("log", "自检已中止"))
                self.events.put(("idle", None))
            else:
                self.events.put(("error", str(e)))

    def _show_selftest_result(self, results):
        """自检完成后弹出左右限位位置，供设置软限位参考。"""
        lines = []
        for res in results:
            if res.neg_pos_mm is not None and res.pos_pos_mm is not None:
                lines.append(
                    f"{res.name} 轴\n"
                    f"  左限位位置: {res.neg_pos_mm:+.3f} mm\n"
                    f"  右限位位置: {res.pos_pos_mm:+.3f} mm\n"
                    f"  行程: {res.span_mm:.3f} mm")
            else:
                lines.append(f"{res.name} 轴\n  左右限位位置未获取 (自检异常)")
        messagebox.showinfo(
            "自检结果 (软限位参考)",
            "\n\n".join(lines) +
            "\n\n请据此在「回零与限位」中填写软限位，并保留安全余量。\n"
            "(若自检前未先回零，位置以自检起点为参考；建议先「回零」再自检。)")

    def _on_save_csv(self):
        if self.scanner is None or not self.scanner.result:
            messagebox.showinfo("提示", "尚无数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="scan_result.csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.scanner.save_csv(path)
            self._log(f"已保存 {path}")

    def _on_save_plot(self):
        if not HAVE_MPL:
            messagebox.showinfo("提示", "未安装 numpy/matplotlib，无法保存热力图")
            return
        if self.scanner is None or not self.scanner.result:
            messagebox.showinfo("提示", "尚无数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile="scan_result.png", filetypes=[("PNG", "*.png")])
        if path:
            self.scanner.save_heatmap(path)
            self._log(f"已保存 {path}")

    # ---------------- 热力图 ----------------
    def _scan_rect(self):
        """从界面扫描参数读取区域 (start/stop/step)；无效 (步长<=0) 时返回 None。"""
        xs = self._num("x_step", 1.0)
        ys = self._num("y_step", 1.0)
        if xs <= 0 or ys <= 0:
            return None
        return (self._num("x_start", 0.0), self._num("x_stop", 0.0), xs,
                self._num("y_start", 0.0), self._num("y_stop", 0.0), ys)

    def _bind_config_traces(self):
        """扫描参数变化时刷新默认热力图；位置标记开关变化时立即显隐。"""
        for k in ("x_start", "x_stop", "x_step", "y_start", "y_stop", "y_step"):
            self.v[k].trace_add("write", lambda *_: self._init_heatmap())
        self.v["show_pos_on_map"].trace_add(
            "write", lambda *_: self._update_map_markers())

    def _clear_heatmap(self):
        """清空热力图数据并恢复为默认图表 (断开/重置时)。"""
        self._z = None
        self._heat_cfg = None
        self._init_heatmap()

    def _init_heatmap(self):
        """根据当前扫描起点/终点建立默认热力图图表。

        作为常驻默认图表，范围直接由扫描参数决定，可在连接前后、参数变化时
        反复调用更新；不依赖 scanner 是否已创建。
        imshow/色标/图例只创建一次，之后仅更新数据与范围——保证色标大小不变、
        图表不会被反复重排而缩小。
        """
        if not HAVE_MPL or self._canvas is None or self._state == "scanning":
            return
        rect = self._scan_rect()
        if rect is None:
            self._z = None
            self._heat_cfg = None
            self._im = None
            self._target_marker = None
            self._pos_marker = None
            self._ax.clear()
            self._ax.text(0.5, 0.5, "扫描步长无效，无法显示热力图",
                          ha="center", va="center", transform=self._ax.transAxes)
            if self._cbar is not None:
                try:
                    self._cbar.remove()
                except Exception:
                    pass
            self._cbar = None
            self._canvas.draw_idle()
            return
        x0, x1, xs, y0, y1, ys = rect
        nx = max(1, int(round((x1 - x0) / xs)) + 1)
        ny = max(1, int(round((y1 - y0) / ys)) + 1)
        # imshow 的 extent 是图像边界；要让采样点落在色块中心，
        # 各边外扩半个步长 (start - step/2 ~ stop + step/2)
        extent = [x0 - xs / 2, x1 + xs / 2, y0 - ys / 2, y1 + ys / 2]
        self._heat_cfg = rect
        self._z = np.full((ny, nx), np.nan)
        if self._im is None:
            # 首次 (或从"步长无效"恢复): 建图 + 色标 + 图例，之后一直复用
            self._ax.clear()
            self._im = self._ax.imshow(
                self._z, origin="lower", aspect="equal", cmap="inferno",
                extent=extent)
            self._target_marker = self._ax.plot(
                [], [], marker="o", ms=9, mfc="none", mec="#1f6feb", mew=1.5,
                ls="none", label="目标位置")[0]
            self._pos_marker = self._ax.plot(
                [], [], marker="+", ms=12, mec="#d1242f", mew=2,
                ls="none", label="当前位置")[0]
            # 图例必须在标记可见时创建，否则图例只渲染文字、不渲染图标；
            # 放图表右上角外侧 (标题左移避免重叠)
            leg = self._ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.03),
                                  ncol=2, fontsize=8, framealpha=0.6)
            self._ax.set_xlabel("X (mm)")
            self._ax.set_ylabel("Y (mm)")
            self._ax.set_title("Power map", loc="left")
            self._cbar = self._fig.colorbar(self._im, ax=self._ax)
        else:
            # 复用已有 imshow/色标: 只更新数据与范围，不重建色标
            ax_pos = self._ax.get_position()
            cb_pos = self._cbar.ax.get_position()
            gap = cb_pos.x0 - ax_pos.x1   # 色标与主轴右侧的间距 (figure 比例, 恒定)
            self._im.set_data(self._z)
            self._im.set_extent(extent)
            # aspect='equal' + 新范围会让主轴重排，让色标跟随主轴对齐
            new_ax = self._ax.get_position()
            self._cbar.ax.set_position([new_ax.x1 + gap, new_ax.y0,
                                        cb_pos.width, new_ax.height])
        # 位置标记与图例的显隐始终交给 _update_map_markers (遵循 show_pos_on_map)，
        # 使标记在初始/参数变化/断开后都按默认显示，而不是开始扫描才有
        self._update_map_markers(target=self._target_pos, actual=self._cur_pos)
        self._canvas.draw_idle()

    def _update_heatmap(self, x, y, p):
        if not HAVE_MPL or self._z is None or self._heat_cfg is None:
            return
        x0, x1, xs, y0, y1, ys = self._heat_cfg
        xi = int(round((x - x0) / xs))
        yi = int(round((y - y0) / ys))
        if 0 <= yi < self._z.shape[0] and 0 <= xi < self._z.shape[1]:
            self._z[yi, xi] = p
        finite = self._z[np.isfinite(self._z)]
        if finite.size:
            self._im.set_clim(float(finite.min()), float(finite.max()))
        self._im.set_data(self._z)
        self._canvas.draw_idle()

    def _update_map_markers(self, target=None, actual=None):
        """在热力图上叠加目标/实际位置标记 (由 show_pos_on_map 选项控制显隐)。

        只要连接并处于空闲/点动/扫描，就持续刷新，而不是开始扫描才有标记。
        target: 当前目标位置 (mm)；actual: 当前实际位置 (mm)。
        """
        if not HAVE_MPL or self._canvas is None or self._ax is None:
            return
        show = self.v["show_pos_on_map"].get()
        if self._target_marker is not None:
            if target is not None:
                self._target_marker.set_data([target[0]], [target[1]])
            self._target_marker.set_visible(show)
        if self._pos_marker is not None:
            if actual is not None:
                self._pos_marker.set_data([actual[0]], [actual[1]])
            self._pos_marker.set_visible(show)
        leg = self._ax.get_legend()
        if leg is not None:
            leg.set_visible(show)
        self._canvas.draw_idle()

    # ---------------- 事件循环 ----------------
    def _poll(self):
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _handle_event(self, ev):
        kind, payload = ev
        if kind == "log":
            self._log(payload)
        elif kind == "point":
            i, x, y, p, total = payload
            self.v["progress"].set((i + 1) / total * 100 if total else 0)
            self.v["status"].set(f"点 {i + 1}/{total}  ({x:.3f},{y:.3f})  {p:.6f} W")
            self._set_pos(x, y)
            self._target_pos = (x, y)
            self._update_heatmap(x, y, p)
            self._update_map_markers(target=self._target_pos)
        elif kind == "connected":
            self._log("已连接")
            self.v["status"].set("已连接")
            self._set_state("idle")
            self._update_ranges()
            self._refresh_pos()
        elif kind == "idle":
            self.v["status"].set("就绪")
            self._set_state("idle")
            self._refresh_pos()
        elif kind == "done":
            self._log("扫描完成")
            self.v["status"].set("完成")
            self._set_state("idle")
            self._refresh_pos()
        elif kind == "selftest_done":
            self._log("自检完成")
            self.v["status"].set("自检完成")
            self._set_state("idle")
            self._refresh_pos()
            self._show_selftest_result(payload)
        elif kind == "error":
            self._log(f"[错误] {payload}")
            self.v["status"].set("出错")
            self._set_state("idle")

    def _on_close(self):
        self._save_config()
        if self.scanner is not None:
            self.scanner.abort()
        self._close_devices()
        self.root.destroy()
