"""逐点停测 (step & measure) 扫描采集主循环。"""
from __future__ import annotations

import csv
import statistics
import time
from typing import Optional

from .config import ScanConfig
from .motion import Axis
from .power_meter import PowerMeter


class ScanResult:
    def __init__(self):
        self.x_mm = []
        self.y_mm = []
        self.power = []
        self.t = []

    def append(self, x, y, p, t):
        self.x_mm.append(x)
        self.y_mm.append(y)
        self.power.append(p)
        self.t.append(t)

    def __len__(self):
        return len(self.power)


def _linspace_points(start, stop, step):
    """生成 start..stop (含端点) 的等距点，用索引计算避免累计浮点误差。"""
    i = 0
    while True:
        v = start + i * step
        if v > stop + 1e-9:
            break
        yield v
        i += 1


def raster_points(cfg: ScanConfig):
    """生成扫描点序列 (可选蛇形往返)。yield (x_mm, y_mm)。"""
    xs = list(_linspace_points(cfg.x_start, cfg.x_stop, cfg.x_step))
    for j, y in enumerate(_linspace_points(cfg.y_start, cfg.y_stop, cfg.y_step)):
        row = xs if (j % 2 == 0 or not cfg.snake) else list(reversed(xs))
        for x in row:
            yield float(x), float(y)


class Scanner:
    """两轴滑台 + 功率计，逐点扫描采集。"""

    def __init__(self, x_axis: Axis, y_axis: Axis, meter: PowerMeter, cfg: ScanConfig):
        self.x = x_axis
        self.y = y_axis
        self.meter = meter
        self.cfg = cfg
        self.result = ScanResult()
        self._aborted = False

    # ---------- 准备 ----------
    def prepare(self):
        """使能两轴并配置 PP 模式 (真实驱动器)。模拟轴为 no-op。"""
        for ax in (self.x, self.y):
            if hasattr(ax, "setup_pp"):
                ax.setup_pp()
            ax.enable()

    def home(self):
        for ax in (self.x, self.y):
            if self._aborted:
                break
            ax.home()

    # ---------- 坐标换算 ----------
    def _to_pulses(self, x_mm: float, y_mm: float):
        x_pul = int(round(x_mm * self.x.pulses_per_mm * self.x.direction))
        y_pul = int(round(y_mm * self.y.pulses_per_mm * self.y.direction))
        return x_pul, y_pul

    # ---------- 软限位校验 ----------
    def validate_soft_limits(self, cfg: Optional[ScanConfig] = None):
        """校验扫描范围是否落在各轴软限位内 (mm，相对回零原点)。越界抛 RuntimeError。"""
        cfg = cfg or self.cfg
        for ax, start_mm, stop_mm in ((self.x, cfg.x_start, cfg.x_stop),
                                      (self.y, cfg.y_start, cfg.y_stop)):
            lim = ax.soft_limits
            if not lim:
                continue
            lo_mm, hi_mm = lim
            lo = min(start_mm, stop_mm)
            hi = max(start_mm, stop_mm)
            if lo_mm is not None and lo < lo_mm:
                raise RuntimeError(
                    f"{ax.name} 轴扫描范围下限 {lo:.3f} mm 低于软限位 {lo_mm:.3f} mm")
            if hi_mm is not None and hi > hi_mm:
                raise RuntimeError(
                    f"{ax.name} 轴扫描范围上限 {hi:.3f} mm 超过软限位 {hi_mm:.3f} mm")

    # ---------- 单点采集 ----------
    def _move_and_settle(self, x_pul: int, y_pul: int):
        self.x.move_abs(x_pul)
        self.y.move_abs(y_pul)
        if not self.x.wait_target_reached(self.cfg.timeout):
            raise RuntimeError("X 轴到位超时")
        if not self.y.wait_target_reached(self.cfg.timeout):
            raise RuntimeError("Y 轴到位超时")
        if self.cfg.dwell > 0:
            time.sleep(self.cfg.dwell)

    def _measure(self, x_mm: float, y_mm: float) -> float:
        # 模拟功率计需要知道当前位置；真实功率计无此接口，忽略
        if hasattr(self.meter, "set_position"):
            self.meter.set_position(x_mm, y_mm)
        vals = []
        for _ in range(self.cfg.n_samples_per_point):
            vals.append(self.meter.measure())
            if self.cfg.n_samples_per_point > 1 and self.cfg.sample_interval > 0:
                time.sleep(self.cfg.sample_interval)
        return float(statistics.mean(vals))

    # ---------- 主循环 ----------
    def scan(self, progress_callback=None) -> ScanResult:
        """逐点扫描。progress_callback(i, x_mm, y_mm, power, total) 每点调用一次。"""
        t0 = time.monotonic()
        self.validate_soft_limits()
        total = sum(1 for _ in raster_points(self.cfg))
        for i, (x_mm, y_mm) in enumerate(raster_points(self.cfg)):
            if self._aborted:
                break
            x_pul, y_pul = self._to_pulses(x_mm, y_mm)
            self._move_and_settle(x_pul, y_pul)
            power = self._measure(x_mm, y_mm)
            self.result.append(x_mm, y_mm, power, time.monotonic() - t0)
            print(f"[{i:4d}] x={x_mm:8.3f} y={y_mm:8.3f}  P={power:.6f} W")
            if progress_callback is not None:
                progress_callback(i, x_mm, y_mm, power, total)
        return self.result

    def abort(self):
        self._aborted = True

    # ---------- 导出 ----------
    def save_csv(self, path: Optional[str] = None) -> str:
        path = path or self.cfg.output_csv
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["x_mm", "y_mm", "power_W", "t_s"])
            for x, y, p, t in zip(self.result.x_mm, self.result.y_mm,
                                  self.result.power, self.result.t):
                w.writerow([x, y, p, t])
        print(f"已保存 CSV: {path}")
        return path

    def save_heatmap(self, path: Optional[str] = None) -> str:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        path = path or self.cfg.output_heatmap
        cfg = self.cfg
        nx = int(round((cfg.x_stop - cfg.x_start) / cfg.x_step)) + 1
        ny = int(round((cfg.y_stop - cfg.y_start) / cfg.y_step)) + 1
        if nx * ny != len(self.result.power):
            print("[warn] 采样点数与网格尺寸不符，跳过热力图 (可能扫描被中断)")
            return path

        z = np.reshape(np.array(self.result.power), (ny, nx))
        plt.figure()
        plt.imshow(z, extent=[cfg.x_start, cfg.x_stop, cfg.y_start, cfg.y_stop],
                   origin="lower", aspect="auto", cmap="inferno")
        plt.colorbar(label="Power (W)")
        plt.xlabel("X (mm)")
        plt.ylabel("Y (mm)")
        plt.title("Power map")
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"已保存热力图: {path}")
        return path
