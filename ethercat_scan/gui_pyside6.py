"""PySide6 图形界面 (gui.py 的 Qt 版本)。

功能与 Tkinter 版 (gui.py) 完全一致，只是控件换成 PySide6：
- 无第三方依赖即可运行本体；热力图需 numpy+matplotlib (QtAgg 后端)，缺失时自动降级。
- 扫描在后台线程运行，通过 queue 把结果回传给主线程刷新界面 (Qt 控件同样非线程安全)，
  用 QTimer 周期轮询事件队列 (对应 Tk 的 root.after)。
- 配置文件与 Tk 版共用 ~/.ethercat_scan_config.json，两套 UI 设置互通。

用法:
    pip install PySide6
    python examples/run_gui_pyside6.py
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QVBoxLayout,
    QWidget,
)

from .config import AxisConfig, ScanConfig
from .motion import SimulatedAxis
from .power_meter import Pm100usbPowerMeter, SimulatedPowerMeter
from .scanner import Scanner, ScanResult

try:
    import numpy as np
    import matplotlib
    matplotlib.use("QtAgg")
    # 使用系统中文字体，避免标题/标签中的中文渲染成乱码方框
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


class RulerWidget(QWidget):
    """位置标尺：显示软限位区间与当前位置 (对应 Tk 版的 tk.Canvas 标尺)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(110)
        self.setFixedHeight(30)
        self._cur = 0.0
        self._rng = None

    def set_state(self, cur: float, rng):
        self._cur = cur
        self._rng = rng
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        lo = hi = None
        if self._rng:
            lo, hi = self._rng
        f = QFont(self.font())
        f.setPointSize(8)
        p.setFont(f)
        if lo is None or hi is None or hi <= lo:
            p.setPen(QColor("#888888"))
            p.drawText(self.rect(), Qt.AlignCenter, "软限位未设置")
            p.end()
            return
        m = 28
        x0, x1, y = m, w - m, h // 2
        p.setPen(QPen(QColor("#bbbbbb"), 1))
        p.drawLine(x0, y, x1, y)
        p.setPen(QPen(QColor("#666666"), 1))
        p.drawLine(x0, y - 4, x0, y + 4)
        p.drawLine(x1, y - 4, x1, y + 4)
        p.setPen(QColor("#666666"))
        p.drawText(int(x0) - 20, y + 2, 40, 12,
                   Qt.AlignHCenter | Qt.AlignTop, f"{lo:g}")
        p.drawText(int(x1) - 20, y + 2, 40, 12,
                   Qt.AlignHCenter | Qt.AlignTop, f"{hi:g}")
        cur = self._cur
        out = cur < lo or cur > hi
        clamped = max(lo, min(hi, cur))
        xc = x0 + (clamped - lo) / (hi - lo) * (x1 - x0)
        color = QColor("#cc0000") if out else QColor("#0066cc")
        p.setPen(QPen(color, 2))
        p.drawLine(xc, y - 5, xc, y + 5)
        p.setPen(color)
        p.drawText(int(xc) - 25, 0, 50, 12,
                   Qt.AlignHCenter | Qt.AlignTop, f"{cur:.2f}")
        p.end()


class ScanAppQt(QWidget):
    # 需要持久化的配置项 (status/progress/pos/limits 为运行时状态，不保存)
    # 与 Tk 版 (gui.ScanApp._CONFIG_KEYS) 保持一致，配置文件互通。
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EtherCAT 双轴滑台扫描采集 (PySide6)")
        self.resize(1100, 840)
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
        self._heat_cfg = None
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
        self._defaults = self._collect_values()
        self._build_ui()
        self._load_config()
        self._init_heatmap()

        self._log("就绪。默认模拟运行(dry-run)；接真实硬件时取消勾选并填网卡名。")
        self._timer_poll = QTimer(self)
        self._timer_poll.timeout.connect(self._poll)
        self._timer_poll.start(50)
        self._timer_pos = QTimer(self)
        self._timer_pos.timeout.connect(self._refresh_pos)
        self._timer_pos.start(200)

    # ---------------- 变量 ----------------
    def _build_vars(self):
        """创建各配置项对应的控件 (通过 _g/_s 读写，普通控件不是线程安全的)。"""
        self.w = {}
        w = self.w
        w["ifname"] = QLineEdit("")
        w["dry_run"] = QCheckBox("模拟运行 (dry-run)")
        w["dry_run"].setChecked(True)
        w["x_alias"] = QLineEdit("0")
        w["y_alias"] = QLineEdit("1")
        w["x_ppmm"] = QLineEdit("200")
        w["y_ppmm"] = QLineEdit("200")
        w["x_reverse"] = QCheckBox("X 反向")
        w["y_reverse"] = QCheckBox("Y 反向")
        w["x_home_method"] = QComboBox()
        w["y_home_method"] = QComboBox()
        for c in (w["x_home_method"], w["y_home_method"]):
            c.addItems(["17", "18", "24", "29"])
            c.setCurrentText("17")
        w["x_min"] = QLineEdit("")
        w["x_max"] = QLineEdit("")
        w["y_min"] = QLineEdit("")
        w["y_max"] = QLineEdit("")
        w["x_start"] = QLineEdit("-10")
        w["x_stop"] = QLineEdit("10")
        w["x_step"] = QLineEdit("1")
        w["y_start"] = QLineEdit("-10")
        w["y_stop"] = QLineEdit("10")
        w["y_step"] = QLineEdit("1")
        w["dwell"] = QLineEdit("0.1")
        w["samples"] = QLineEdit("1")
        w["snake"] = QCheckBox("蛇形")
        w["snake"].setChecked(True)
        w["home"] = QCheckBox("扫描前回零")
        w["show_pos_on_map"] = QCheckBox("热力图显示位置标记")
        w["show_pos_on_map"].setChecked(True)
        w["pm_use_real"] = QCheckBox("真实功率计 (PM100USB)")
        w["pm_resource"] = QLineEdit("")
        w["pm_wavelength"] = QLineEdit("")
        w["jog_step"] = QLineEdit("1")

        # 运行时状态显示 (不持久化)
        self.lbl_status = QLabel("未连接")
        self.lbl_pos_x = QLabel("X: 0.000 mm")
        self.lbl_pos_y = QLabel("Y: 0.000 mm")
        self.lbl_range_x = QLabel("未设置")
        self.lbl_range_y = QLabel("未设置")
        self.lbl_limits = QLabel("限位: —")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

    def _g(self, key):
        """读一个配置项 (主线程内调用)。"""
        wid = self.w[key]
        if isinstance(wid, QCheckBox):
            return wid.isChecked()
        if isinstance(wid, QComboBox):
            return wid.currentText()
        return wid.text()

    def _s(self, key, value):
        """写一个配置项 (仅主线程调用)。"""
        wid = self.w[key]
        if isinstance(wid, QCheckBox):
            wid.setChecked(bool(value))
        elif isinstance(wid, QComboBox):
            wid.setCurrentText(str(value))
        else:
            wid.setText(str(value))

    def _collect_values(self):
        """把所有配置项读成普通 dict (主线程调用)。"""
        return {k: self._g(k) for k in self.w}

    def _num(self, key, default, cast=float):
        try:
            return cast(self._g(key))
        except (ValueError, TypeError):
            return default

    def _opt_num(self, key, cast=float):
        """解析可选数值：空串/非法 → None。"""
        s = self._g(key).strip()
        if not s:
            return None
        try:
            return cast(s)
        except (ValueError, TypeError):
            return None

    # ---------------- 配置持久化 ----------------
    def _config_path(self) -> Path:
        return Path.home() / ".ethercat_scan_config.json"

    def _save_config(self) -> bool:
        """把当前配置写入用户目录 JSON，供下次启动恢复。"""
        try:
            data = {k: self._g(k) for k in self._CONFIG_KEYS}
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
                if k in data:
                    self._s(k, data[k])
            self._log(f"已加载上次配置: {path}")
        except Exception as e:
            self._log(f"[警告] 加载配置失败，使用默认值: {e}")

    def _on_save_config(self):
        self._save_config()

    def _on_reset_config(self):
        """恢复默认设置：重置所有配置项为出厂默认值，并清除已保存的配置文件。"""
        if QMessageBox.question(
                self, "恢复默认设置",
                "确定将所有设置恢复为默认值并清除已保存的配置文件吗？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        for k in self._CONFIG_KEYS:
            if k in self._defaults:
                self._s(k, self._defaults[k])
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
        root = self
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 1) 硬件连接 (左) + 功率计 (右)
        row0 = QHBoxLayout()
        layout.addLayout(row0)

        fhw = QGroupBox("硬件连接")
        g = QGridLayout(fhw)
        g.addWidget(self.w["dry_run"], 0, 0, 1, 4)
        g.addWidget(QLabel("网卡"), 1, 0)
        g.addWidget(self.w["ifname"], 1, 1, 1, 3)
        g.addWidget(QLabel("X 站号"), 2, 0)
        g.addWidget(self.w["x_alias"], 2, 1)
        g.addWidget(QLabel("Y 站号"), 2, 2)
        g.addWidget(self.w["y_alias"], 2, 3)
        g.addWidget(QLabel("X 脉冲/mm"), 3, 0)
        g.addWidget(self.w["x_ppmm"], 3, 1)
        g.addWidget(QLabel("Y 脉冲/mm"), 3, 2)
        g.addWidget(self.w["y_ppmm"], 3, 3)
        g.addWidget(self.w["x_reverse"], 4, 1)
        g.addWidget(self.w["y_reverse"], 4, 3)
        row0.addWidget(fhw, 1)

        fpm = QGroupBox("功率计 (PM100USB + PD300R)")
        g = QGridLayout(fpm)
        g.addWidget(self.w["pm_use_real"], 0, 0, 1, 2)
        g.addWidget(QLabel("资源名"), 1, 0)
        g.addWidget(self.w["pm_resource"], 1, 1)
        g.addWidget(QLabel("波长(nm)"), 2, 0)
        g.addWidget(self.w["pm_wavelength"], 2, 1)
        hint = QLabel("(资源名留空自动搜索；波长留空用探头当前校准)")
        hint.setStyleSheet("color: gray;")
        g.addWidget(hint, 3, 0, 1, 2)
        row0.addWidget(fpm, 1)

        # 2) 回零与限位 (左) + 扫描参数 (右)
        row1 = QHBoxLayout()
        layout.addLayout(row1)

        fhl = QGroupBox("回零与限位 (mm，相对原点)")
        g = QGridLayout(fhl)
        for r, name in enumerate(["X", "Y"]):
            k = name.lower()
            g.addWidget(QLabel(f"{name} 回零方式"), r, 0)
            g.addWidget(self.w[f"{k}_home_method"], r, 1)
            g.addWidget(QLabel(f"{name} 软限位"), r, 2)
            g.addWidget(self.w[f"{k}_min"], r, 3)
            g.addWidget(QLabel("~"), r, 4)
            g.addWidget(self.w[f"{k}_max"], r, 5)
        row1.addWidget(fhl, 1)

        fsc = QGroupBox("扫描参数 (mm)")
        g = QGridLayout(fsc)
        for r, (key, lbl) in enumerate([("start", "起点"), ("stop", "终点"), ("step", "步长")]):
            g.addWidget(QLabel(f"X {lbl}"), r, 0)
            g.addWidget(self.w[f"x_{key}"], r, 1)
            g.addWidget(QLabel(f"Y {lbl}"), r, 2)
            g.addWidget(self.w[f"y_{key}"], r, 3)
        g.addWidget(QLabel("停留(s)"), 0, 4)
        g.addWidget(self.w["dwell"], 0, 5)
        g.addWidget(QLabel("每点采样"), 1, 4)
        g.addWidget(self.w["samples"], 1, 5)
        g.addWidget(self.w["home"], 3, 0, 1, 2)
        g.addWidget(self.w["snake"], 3, 2, 1, 2)
        g.addWidget(self.w["show_pos_on_map"], 4, 0, 1, 4)
        row1.addWidget(fsc, 1)

        # 3) 控制按钮 (运动控制 左 / 数据 右)
        fctl = QHBoxLayout()
        layout.addLayout(fctl)
        fmove = QHBoxLayout()
        self.btn_connect = QPushButton("连接")
        self.btn_home = QPushButton("回零")
        self.btn_start = QPushButton("开始扫描")
        self.btn_stop = QPushButton("停止")
        self.btn_selftest = QPushButton("自检")
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_home.clicked.connect(self._on_home)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_selftest.clicked.connect(self._on_selftest)
        for b in (self.btn_connect, self.btn_home, self.btn_start,
                  self.btn_stop, self.btn_selftest):
            fmove.addWidget(b)
        fctl.addLayout(fmove)

        fdata = QHBoxLayout()
        self.btn_save = QPushButton("保存CSV")
        self.btn_saveplot = QPushButton("保存热力图")
        self.btn_savecfg = QPushButton("保存配置")
        self.btn_resetcfg = QPushButton("恢复默认")
        self.btn_save.clicked.connect(self._on_save_csv)
        self.btn_saveplot.clicked.connect(self._on_save_plot)
        self.btn_savecfg.clicked.connect(self._on_save_config)
        self.btn_resetcfg.clicked.connect(self._on_reset_config)
        for b in (self.btn_save, self.btn_saveplot, self.btn_savecfg, self.btn_resetcfg):
            fdata.addWidget(b)
        fctl.addStretch(1)
        fctl.addLayout(fdata)
        self.btn_home.setEnabled(False)
        self.btn_start.setEnabled(False)

        # 4) 进度
        fprog = QHBoxLayout()
        layout.addLayout(fprog)
        fprog.addWidget(self.lbl_limits)
        fprog.addSpacing(16)
        fprog.addWidget(self.lbl_status)
        fprog.addStretch(1)
        fprog.addWidget(self.progress, 1)

        # 5) 实时位置与软限位 / 手动点动 (左，紧凑) + 热力图/日志 (右，占满) 同一行
        bottom = QHBoxLayout()
        layout.addLayout(bottom, 1)

        fpos = QGroupBox("实时位置与软限位 / 手动点动")
        fpos.setFixedWidth(220)
        g = QGridLayout(fpos)
        # X 轴: 名称 + 位置 + 点动按钮一行，软限位与标尺在其下方
        g.addWidget(QLabel("X"), 0, 0)
        g.addWidget(self.lbl_pos_x, 0, 1)
        btn_xn = QPushButton("-")
        btn_xp = QPushButton("+")
        btn_xn.setFixedWidth(28)
        btn_xp.setFixedWidth(28)
        btn_xn.clicked.connect(lambda: self._on_jog("X", -1))
        btn_xp.clicked.connect(lambda: self._on_jog("X", +1))
        g.addWidget(btn_xn, 0, 2)
        g.addWidget(btn_xp, 0, 3)
        g.addWidget(self.lbl_range_x, 1, 1)
        self._ruler_x = RulerWidget()
        g.addWidget(self._ruler_x, 2, 0, 1, 4)
        # Y 轴 (同 X)
        g.addWidget(QLabel("Y"), 3, 0)
        g.addWidget(self.lbl_pos_y, 3, 1)
        btn_yn = QPushButton("-")
        btn_yp = QPushButton("+")
        btn_yn.setFixedWidth(28)
        btn_yp.setFixedWidth(28)
        btn_yn.clicked.connect(lambda: self._on_jog("Y", -1))
        btn_yp.clicked.connect(lambda: self._on_jog("Y", +1))
        g.addWidget(btn_yn, 3, 2)
        g.addWidget(btn_yp, 3, 3)
        g.addWidget(self.lbl_range_y, 4, 1)
        self._ruler_y = RulerWidget()
        g.addWidget(self._ruler_y, 5, 0, 1, 4)
        self._jog_buttons = [btn_xn, btn_xp, btn_yn, btn_yp]
        # 点动步长
        g.addWidget(QLabel("点动步长(mm)"), 6, 1)
        self.w["jog_step"].setFixedWidth(56)
        g.addWidget(self.w["jog_step"], 6, 2, 1, 2)
        bottom.addWidget(fpos)

        # 6) 热力图 + 日志
        right = QSplitter(Qt.Horizontal)
        if HAVE_MPL:
            self._fig = Figure(figsize=(5, 4), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvasQTAgg(self._fig)
            right.addWidget(self._canvas)
        else:
            lbl = QLabel("(未装 numpy/matplotlib，无热力图预览)")
            lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            right.addWidget(lbl)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        right.addWidget(self.log_text)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 1)
        right.setSizes([600, 260])
        bottom.addWidget(right, 1)

    # ---------------- 日志 / 状态 ----------------
    def _log(self, msg: str):
        self.log_text.appendPlainText(f"{time.strftime('%H:%M:%S')}  {msg}")

    def _param_widgets(self):
        """返回可编辑的参数控件 (QLineEdit/QCheckBox/QComboBox)。

        硬件连接/功率计/回零限位/扫描参数四个区 + 点动步长输入框。
        """
        out = []
        for k in ("ifname", "dry_run", "x_alias", "y_alias", "x_ppmm", "y_ppmm",
                  "x_reverse", "y_reverse", "x_home_method", "y_home_method",
                  "x_min", "x_max", "y_min", "y_max",
                  "x_start", "x_stop", "x_step", "y_start", "y_stop", "y_step",
                  "dwell", "samples", "snake", "home", "show_pos_on_map",
                  "pm_use_real", "pm_resource", "pm_wavelength"):
            out.append(self.w[k])
        out.append(self.w["jog_step"])
        return out

    def _update_param_lock(self):
        """非空闲状态 (扫描/回零/点动/连接中) 锁定参数控件，防止中途修改。"""
        locked = self._state != "idle"
        for w in self._param_widgets():
            w.setEnabled(not locked)

    def _update_buttons(self):
        """集中管理按钮互锁 (单一状态源)。见 Tk 版同名方法的注释。"""
        state = self._state
        self._update_param_lock()
        connected = self.scanner is not None
        have_data = connected and len(self.scanner.result) > 0
        idle = connected and state == "idle"

        self.btn_connect.setEnabled(state == "idle")
        self.btn_connect.setText("断开" if (state == "idle" and connected) else "连接")
        self.btn_home.setEnabled(idle)
        self.btn_start.setEnabled(idle)
        self.btn_stop.setEnabled(state in ("scanning", "selftest"))
        self.btn_save.setEnabled(idle and have_data)
        self.btn_saveplot.setEnabled(idle and have_data and HAVE_MPL)
        self.btn_savecfg.setEnabled(state == "idle")
        self.btn_resetcfg.setEnabled(state == "idle")
        for b in self._jog_buttons:
            b.setEnabled(idle)
        if self.btn_selftest is not None:
            self.btn_selftest.setEnabled(idle)

    def _set_state(self, state: str):
        self._state = state
        self._update_buttons()

    # ---------------- 位置显示 ----------------
    def _axis_mm(self, ax) -> float:
        return ax.read_actual_position() / (ax.pulses_per_mm * ax.direction)

    def _set_pos(self, x_mm: float, y_mm: float):
        self._cur_pos = (x_mm, y_mm)
        self.lbl_pos_x.setText(f"X: {x_mm:8.3f} mm")
        self.lbl_pos_y.setText(f"Y: {y_mm:8.3f} mm")
        self._draw_rulers()

    def _refresh_pos(self):
        """读取两轴实际位置与限位状态。见 Tk 版同名方法注释。"""
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
        elif self._state == "scanning" and self._g("show_pos_on_map"):
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
        self.lbl_limits.setText("限位: " + "  ".join(_fmt(ax) for ax in (x_ax, y_ax)))

    def _update_ranges(self):
        """从当前轴读取软限位区间，刷新区间文本与标尺。"""
        sc = self.scanner
        self._x_range = sc.x.soft_limits if sc is not None else None
        self._y_range = sc.y.soft_limits if sc is not None else None
        for key, rng in (("range_x", self._x_range), ("range_y", self._y_range)):
            if rng and rng[0] is not None and rng[1] is not None:
                (self.lbl_range_x if key == "range_x" else self.lbl_range_y).setText(
                    f"{rng[0]:g} ~ {rng[1]:g} mm")
            else:
                (self.lbl_range_x if key == "range_x" else self.lbl_range_y).setText("未设置")
        self._draw_rulers()

    def _draw_rulers(self):
        if self._ruler_x is None or self._ruler_y is None:
            return
        x, y = self._cur_pos
        self._ruler_x.set_state(x, self._x_range)
        self._ruler_y.set_state(y, self._y_range)

    # ---------------- 构建 scanner ----------------
    def _collect_params(self):
        """在主线程读取所有界面参数为普通 dict (Qt 控件只能在主线程访问)。"""
        return {
            "dry_run": self._g("dry_run"),
            "ifname": self._g("ifname").strip(),
            "x_alias": self._num("x_alias", 0, int),
            "y_alias": self._num("y_alias", 1, int),
            "x_ppmm": self._num("x_ppmm", 1000.0),
            "y_ppmm": self._num("y_ppmm", 1000.0),
            "x_reverse": self._g("x_reverse"),
            "y_reverse": self._g("y_reverse"),
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
            "snake": self._g("snake"),
            "home": self._g("home"),
            "pm_use_real": self._g("pm_use_real"),
            "pm_resource": self._g("pm_resource").strip(),
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
        """用普通参数构建 scanner (可在工作线程调用，不碰 Qt 控件)。"""
        cfg = self._scan_config(p)
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
        self.lbl_status.setText("未连接")
        self.lbl_pos_x.setText("X: 0.000 mm")
        self.lbl_pos_y.setText("Y: 0.000 mm")
        self.lbl_limits.setText("限位: —")
        self.progress.setValue(0)
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
                self.lbl_status.setText("已连接(模拟)")
                self._update_ranges()
                self._refresh_pos()
            except Exception as e:
                self._log(f"[错误] {e}")
                self.lbl_status.setText("未连接")
                QMessageBox.critical(self, "连接失败", str(e))
            finally:
                self._update_buttons()
        else:
            self._log("正在连接 EtherCAT ...")
            self.lbl_status.setText("连接中...")
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
        self.lbl_status.setText("回零中...")
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
            QMessageBox.warning(self, "提示", "请先连接")
            return
        if self._state != "idle":
            return
        # 扫描范围等参数以当前界面为准 (连接时只建立硬件/轴对象，范围在开始时读取)
        p = self._collect_params()
        self.scanner.cfg = self._scan_config(p)
        try:
            self.scanner.validate_soft_limits()
        except RuntimeError as e:
            QMessageBox.warning(self, "软限位越界", str(e))
            return
        self.scanner.result = ScanResult()
        if isinstance(self.meter, SimulatedPowerMeter):
            self.meter.cx = (self.scanner.cfg.x_start + self.scanner.cfg.x_stop) / 2
            self.meter.cy = (self.scanner.cfg.y_start + self.scanner.cfg.y_stop) / 2
        self._init_heatmap()
        self.scanner._aborted = False
        self.progress.setValue(0)
        self.lbl_status.setText("扫描中...")
        self._set_state("scanning")
        home = self._g("home")   # 主线程读，避免工作线程访问 Qt 控件
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
            QMessageBox.warning(self, "提示", "点动步长需为正数")
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
        self.lbl_status.setText(f"{ax_name} 轴点动 {direction * step_mm:+.3f} mm ...")
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
            QMessageBox.warning(self, "提示", "当前轴无硬件开关读取能力 (模拟轴)，无法自检")
            return
        self.scanner._aborted = False
        self._set_state("selftest")
        self.lbl_status.setText("自检中...")
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
        QMessageBox.information(
            self, "自检结果 (软限位参考)",
            "\n\n".join(lines) +
            "\n\n请据此在「回零与限位」中填写软限位，并保留安全余量。\n"
            "(若自检前未先回零，位置以自检起点为参考；建议先「回零」再自检。)")

    def _on_save_csv(self):
        if self.scanner is None or not self.scanner.result:
            QMessageBox.information(self, "提示", "尚无数据")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 CSV", "scan_result.csv", "CSV (*.csv)")
        if path:
            self.scanner.save_csv(path)
            self._log(f"已保存 {path}")

    def _on_save_plot(self):
        if not HAVE_MPL:
            QMessageBox.information(self, "提示", "未安装 numpy/matplotlib，无法保存热力图")
            return
        if self.scanner is None or not self.scanner.result:
            QMessageBox.information(self, "提示", "尚无数据")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存热力图", "scan_result.png", "PNG (*.png)")
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

    def _init_heatmap(self):
        """根据当前扫描起点/终点建立默认热力图图表。见 Tk 版同名方法注释。"""
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
        # imshow 的 extent 是图像边界；要让采样点落在色块中心，各边外扩半个步长
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
            # 图例必须在标记可见时创建，否则图例只渲染文字、不渲染图标
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
            new_ax = self._ax.get_position()
            self._cbar.ax.set_position([new_ax.x1 + gap, new_ax.y0,
                                        cb_pos.width, new_ax.height])
        # 位置标记与图例的显隐始终交给 _update_map_markers (遵循 show_pos_on_map)
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
        """在热力图上叠加目标/实际位置标记 (由 show_pos_on_map 选项控制显隐)。"""
        if not HAVE_MPL or self._canvas is None or self._ax is None:
            return
        show = bool(self._g("show_pos_on_map"))
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

    def _clear_heatmap(self):
        """清空热力图数据并恢复为默认图表 (断开/重置时)。"""
        self._z = None
        self._heat_cfg = None
        self._init_heatmap()

    # ---------------- 事件循环 ----------------
    def _poll(self):
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass

    def _handle_event(self, ev):
        kind, payload = ev
        if kind == "log":
            self._log(payload)
        elif kind == "point":
            i, x, y, p, total = payload
            self.progress.setValue(int((i + 1) / total * 100) if total else 0)
            self.lbl_status.setText(f"点 {i + 1}/{total}  ({x:.3f},{y:.3f})  {p:.6f} W")
            self._set_pos(x, y)
            self._target_pos = (x, y)
            self._update_heatmap(x, y, p)
            self._update_map_markers(target=self._target_pos)
        elif kind == "connected":
            self._log("已连接")
            self.lbl_status.setText("已连接")
            self._set_state("idle")
            self._update_ranges()
            self._refresh_pos()
        elif kind == "idle":
            self.lbl_status.setText("就绪")
            self._set_state("idle")
            self._refresh_pos()
        elif kind == "done":
            self._log("扫描完成")
            self.lbl_status.setText("完成")
            self._set_state("idle")
            self._refresh_pos()
        elif kind == "selftest_done":
            self._log("自检完成")
            self.lbl_status.setText("自检完成")
            self._set_state("idle")
            self._refresh_pos()
            self._show_selftest_result(payload)
        elif kind == "error":
            self._log(f"[错误] {payload}")
            self.lbl_status.setText("出错")
            self._set_state("idle")

    # ---------------- 关闭 ----------------
    def closeEvent(self, event):
        """关闭窗口: 保存配置、中止扫描、释放设备。"""
        self._save_config()
        if self.scanner is not None:
            self.scanner.abort()
        self._close_devices()
        self._timer_poll.stop()
        self._timer_pos.stop()
        event.accept()


def main():
    """命令行入口 (等价于 python examples/run_gui_pyside6.py)。"""
    import sys
    app = QApplication(sys.argv)
    win = ScanAppQt()
    win.show()
    return app.exec()


if __name__ == "__main__":
    main()
