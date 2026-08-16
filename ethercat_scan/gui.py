"""Tkinter 图形界面。

零第三方依赖即可运行；热力图需要 numpy+matplotlib，缺失时自动降级为纯日志。
扫描在后台线程运行，通过队列把结果回传给主线程刷新界面 (Tk 非线程安全)。
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config import AxisConfig, ScanConfig
from .motion import SimulatedAxis
from .power_meter import SimulatedPowerMeter
from .scanner import Scanner, ScanResult

try:
    import numpy as np
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


class ScanApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events = queue.Queue()
        self.master = None
        self.meter = None
        self.scanner = None
        self._running = False

        # 热力图相关
        self._fig = None
        self._ax = None
        self._im = None
        self._cbar = None
        self._canvas = None
        self._z = None

        self._build_vars()
        self._build_ui()
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
            "x_ppmm": tk.StringVar(value="1000"),
            "y_ppmm": tk.StringVar(value="1000"),
            "x_reverse": tk.BooleanVar(value=False),
            "y_reverse": tk.BooleanVar(value=False),
            "x_home_method": tk.StringVar(value="17"),
            "y_home_method": tk.StringVar(value="17"),
            "x_min": tk.StringVar(value=""),
            "x_max": tk.StringVar(value=""),
            "y_min": tk.StringVar(value=""),
            "y_max": tk.StringVar(value=""),
            "x_start": tk.StringVar(value="0"),
            "x_stop": tk.StringVar(value="10"),
            "x_step": tk.StringVar(value="1"),
            "y_start": tk.StringVar(value="0"),
            "y_stop": tk.StringVar(value="10"),
            "y_step": tk.StringVar(value="1"),
            "dwell": tk.StringVar(value="0.1"),
            "samples": tk.StringVar(value="1"),
            "snake": tk.BooleanVar(value=True),
            "home": tk.BooleanVar(value=False),
            "status": tk.StringVar(value="未连接"),
            "progress": tk.DoubleVar(value=0.0),
            "pos": tk.StringVar(value="X: 0.000 mm   Y: 0.000 mm"),
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

    # ---------------- UI ----------------
    def _build_ui(self):
        root = self.root
        root.title("EtherCAT 双轴滑台扫描采集")
        root.geometry("900x760")
        root.columnconfigure(0, weight=1)

        # 1) 硬件连接
        fhw = ttk.LabelFrame(root, text="硬件连接")
        fhw.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        ttk.Checkbutton(fhw, text="模拟运行 (dry-run)", variable=self.v["dry_run"]).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=4)
        self._lbl(fhw, "网卡", 1, 0)
        ttk.Entry(fhw, textvariable=self.v["ifname"], width=40).grid(row=1, column=1, columnspan=3, sticky="w", padx=2)
        # X 轴
        self._lbl(fhw, "X 站号", 2, 0)
        ttk.Entry(fhw, textvariable=self.v["x_alias"], width=6).grid(row=2, column=1, sticky="w", padx=2)
        self._lbl(fhw, "X 脉冲/mm", 3, 0)
        ttk.Entry(fhw, textvariable=self.v["x_ppmm"], width=10).grid(row=3, column=1, sticky="w", padx=2)
        ttk.Checkbutton(fhw, text="X 反向", variable=self.v["x_reverse"]).grid(row=4, column=1, sticky="w", padx=2)
        # Y 轴
        self._lbl(fhw, "Y 站号", 2, 2)
        ttk.Entry(fhw, textvariable=self.v["y_alias"], width=6).grid(row=2, column=3, sticky="w", padx=2)
        self._lbl(fhw, "Y 脉冲/mm", 3, 2)
        ttk.Entry(fhw, textvariable=self.v["y_ppmm"], width=10).grid(row=3, column=3, sticky="w", padx=2)
        ttk.Checkbutton(fhw, text="Y 反向", variable=self.v["y_reverse"]).grid(row=4, column=3, sticky="w", padx=2)

        # 1.5) 回零与限位
        fhl = ttk.LabelFrame(root, text="回零与限位 (软限位单位 mm，相对回零原点)")
        fhl.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        for col, name in enumerate(["X", "Y"]):
            base = col * 4
            self._lbl(fhl, f"{name} 回零方式", 0, base)
            ttk.Combobox(fhl, textvariable=self.v[f"{name.lower()}_home_method"],
                         values=["17", "18", "24", "29"], state="readonly", width=5).grid(
                row=0, column=base + 1, sticky="w", padx=2)
            self._lbl(fhl, f"{name} 软限位", 1, base)
            ttk.Entry(fhl, textvariable=self.v[f"{name.lower()}_min"], width=8).grid(
                row=1, column=base + 1, sticky="w", padx=2)
            ttk.Label(fhl, text="至").grid(row=1, column=base + 2, sticky="w", padx=1)
            ttk.Entry(fhl, textvariable=self.v[f"{name.lower()}_max"], width=8).grid(
                row=1, column=base + 3, sticky="w", padx=2)

        # 2) 扫描参数
        fsc = ttk.LabelFrame(root, text="扫描参数 (mm)")
        fsc.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        for col, name in enumerate(["X", "Y"]):
            base = 1 + col * 2
            self._lbl(fsc, f"{name} 起点", 0, base)
            ttk.Entry(fsc, textvariable=self.v[f"{name.lower()}_start"], width=8).grid(row=0, column=base + 1, sticky="w", padx=2)
            self._lbl(fsc, f"{name} 终点", 1, base)
            ttk.Entry(fsc, textvariable=self.v[f"{name.lower()}_stop"], width=8).grid(row=1, column=base + 1, sticky="w", padx=2)
            self._lbl(fsc, f"{name} 步长", 2, base)
            ttk.Entry(fsc, textvariable=self.v[f"{name.lower()}_step"], width=8).grid(row=2, column=base + 1, sticky="w", padx=2)
        self._lbl(fsc, "停留(s)", 0, 5)
        ttk.Entry(fsc, textvariable=self.v["dwell"], width=8).grid(row=0, column=6, sticky="w", padx=2)
        self._lbl(fsc, "每点采样", 1, 5)
        ttk.Entry(fsc, textvariable=self.v["samples"], width=8).grid(row=1, column=6, sticky="w", padx=2)
        ttk.Checkbutton(fsc, text="蛇形往返", variable=self.v["snake"]).grid(row=2, column=6, sticky="w", padx=2)
        ttk.Checkbutton(fsc, text="扫描前回零", variable=self.v["home"]).grid(row=2, column=5, sticky="w", padx=2)

        # 3) 控制按钮
        fctl = ttk.Frame(root)
        fctl.grid(row=3, column=0, sticky="ew", padx=6, pady=4)
        self.btn_connect = ttk.Button(fctl, text="连接", command=self._on_connect)
        self.btn_home = ttk.Button(fctl, text="回零", command=self._on_home)
        self.btn_start = ttk.Button(fctl, text="开始扫描", command=self._on_start)
        self.btn_stop = ttk.Button(fctl, text="停止", command=self._on_stop, state="disabled")
        self.btn_save = ttk.Button(fctl, text="保存CSV", command=self._on_save_csv, state="disabled")
        self.btn_saveplot = ttk.Button(fctl, text="保存热力图", command=self._on_save_plot, state="disabled")
        for b in (self.btn_connect, self.btn_home, self.btn_start, self.btn_stop,
                  self.btn_save, self.btn_saveplot):
            b.pack(side="left", padx=4)
        self.btn_home.config(state="disabled")
        self.btn_start.config(state="disabled")

        # 4) 进度
        fprog = ttk.Frame(root)
        fprog.grid(row=4, column=0, sticky="ew", padx=6, pady=2)
        ttk.Label(fprog, textvariable=self.v["pos"]).pack(side="left", padx=(0, 16))
        ttk.Label(fprog, textvariable=self.v["limits"]).pack(side="left", padx=(0, 16))
        ttk.Label(fprog, textvariable=self.v["status"]).pack(side="left")
        ttk.Progressbar(fprog, variable=self.v["progress"], maximum=100).pack(
            side="right", fill="x", expand=True, padx=8)

        # 5) 热力图 + 日志
        fbottom = ttk.Frame(root)
        fbottom.grid(row=5, column=0, sticky="nsew", padx=6, pady=4)
        root.rowconfigure(5, weight=1)
        fbottom.columnconfigure(0, weight=1)
        fbottom.rowconfigure(0, weight=1)

        if HAVE_MPL:
            self._fig = Figure(figsize=(5, 4), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._im = self._ax.imshow([[0.0]], origin="lower", aspect="equal", cmap="inferno")
            self._cbar = self._fig.colorbar(self._im, ax=self._ax)
            self._ax.set_xlabel("X (mm)")
            self._ax.set_ylabel("Y (mm)")
            self._ax.set_title("Power map")
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

    def _set_connected(self, ok: bool):
        state = "normal" if ok else "disabled"
        self.btn_home.config(state=state)
        self.btn_start.config(state=state)
        self.btn_save.config(state=state)
        self.btn_saveplot.config(state=state if (ok and HAVE_MPL) else "disabled")

    def _set_running(self, running: bool):
        self._running = running
        self.btn_connect.config(state="disabled" if running else "normal")
        self.btn_home.config(state="disabled" if running else ("normal" if self.scanner else "disabled"))
        self.btn_start.config(state="disabled" if running else ("normal" if self.scanner else "disabled"))
        self.btn_stop.config(state="normal" if running else "disabled")

    # ---------------- 位置显示 ----------------
    def _axis_mm(self, ax) -> float:
        return ax.read_actual_position() / (ax.pulses_per_mm * ax.direction)

    def _set_pos(self, x_mm: float, y_mm: float):
        self.v["pos"].set(f"X: {x_mm:.3f} mm   Y: {y_mm:.3f} mm")

    def _refresh_pos(self):
        """空闲时读取两轴实际位置与限位状态 (扫描中由 point 事件显示目标坐标，避免争用总线)。"""
        sc = self.scanner
        if sc is None or self._running:
            return
        try:
            self._set_pos(self._axis_mm(sc.x), self._axis_mm(sc.y))
            self._set_limits(sc.x, sc.y)
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
            "x_start": self._num("x_start", 0.0),
            "x_stop": self._num("x_stop", 10.0),
            "x_step": self._num("x_step", 1.0),
            "y_start": self._num("y_start", 0.0),
            "y_stop": self._num("y_stop", 10.0),
            "y_step": self._num("y_step", 1.0),
            "dwell": self._num("dwell", 0.1),
            "samples": self._num("samples", 1, int),
            "snake": v["snake"].get(),
            "home": v["home"].get(),
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
        # 功率计: 未接入真实设备，先占位为模拟光斑 (真实设备见 power_meter.py)
        meter = SimulatedPowerMeter(center=((cfg.x_start + cfg.x_stop) / 2,
                                            (cfg.y_start + cfg.y_stop) / 2))
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

    # ---------------- 动作 ----------------
    def _on_connect(self):
        p = self._collect_params()
        if p["dry_run"]:
            try:
                self._build_scanner(p)
                self._log("已连接 (模拟轴 + 模拟功率计)")
                self.v["status"].set("已连接(模拟)")
                self._set_connected(True)
            except Exception as e:
                messagebox.showerror("连接失败", str(e))
        else:
            self._log("正在连接 EtherCAT ...")
            self.v["status"].set("连接中...")
            self._set_connected(False)
            threading.Thread(target=self._connect_real, args=(p,), daemon=True).start()

    def _connect_real(self, p):
        try:
            self._build_scanner(p)
            self.events.put(("connected", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _on_home(self):
        if self.scanner is None:
            return
        self._set_running(True)
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
        self._set_running(True)
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
        if self.scanner is not None:
            self.scanner.abort()
        self._log("已请求停止，等待当前点完成...")

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
    def _init_heatmap(self):
        if not HAVE_MPL or self.scanner is None:
            return
        cfg = self.scanner.cfg
        nx = int(round((cfg.x_stop - cfg.x_start) / cfg.x_step)) + 1
        ny = int(round((cfg.y_stop - cfg.y_start) / cfg.y_step)) + 1
        self._z = np.full((ny, nx), np.nan)
        self._ax.clear()
        self._im = self._ax.imshow(
            self._z, origin="lower", aspect="equal", cmap="inferno",
            extent=[cfg.x_start, cfg.x_stop, cfg.y_start, cfg.y_stop])
        self._ax.set_xlabel("X (mm)")
        self._ax.set_ylabel("Y (mm)")
        self._ax.set_title("Power map (实时)")
        if self._cbar is not None:
            try:
                self._cbar.remove()
            except Exception:
                pass
        self._cbar = self._fig.colorbar(self._im, ax=self._ax)
        self._canvas.draw_idle()

    def _update_heatmap(self, x, y, p):
        if not HAVE_MPL or self._z is None or self.scanner is None:
            return
        cfg = self.scanner.cfg
        xi = int(round((x - cfg.x_start) / cfg.x_step))
        yi = int(round((y - cfg.y_start) / cfg.y_step))
        if 0 <= yi < self._z.shape[0] and 0 <= xi < self._z.shape[1]:
            self._z[yi, xi] = p
        finite = self._z[np.isfinite(self._z)]
        if finite.size:
            self._im.set_clim(float(finite.min()), float(finite.max()))
        self._im.set_data(self._z)
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
            self._update_heatmap(x, y, p)
        elif kind == "connected":
            self._log("已连接")
            self.v["status"].set("已连接")
            self._set_connected(True)
            self._refresh_pos()
        elif kind == "idle":
            self.v["status"].set("就绪")
            self._set_running(False)
            self._set_connected(True)
            self._refresh_pos()
        elif kind == "done":
            self._log("扫描完成")
            self.v["status"].set("完成")
            self._set_running(False)
            self._set_connected(True)
            self._refresh_pos()
        elif kind == "error":
            self._log(f"[错误] {payload}")
            self.v["status"].set("出错")
            self._set_running(False)
            self._set_connected(self.scanner is not None)

    def _on_close(self):
        if self.scanner is not None:
            self.scanner.abort()
        for obj in (self.master, self.meter):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self.root.destroy()
