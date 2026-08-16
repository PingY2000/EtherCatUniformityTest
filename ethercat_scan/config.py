"""扫描采集框架的配置。

所有可调参数集中在这里，避免散落在逻辑代码里。
坐标统一用 mm；驱动器内部用脉冲 (pulses)，换算见 AxisConfig.pulses_per_mm。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AxisConfig:
    """单轴 (YKD2205PE 驱动器 + 滑台轴) 配置。

    脉冲数与毫米换算:
        pulses = mm * pulses_per_mm * direction
        pulses_per_mm 由丝杠导程、细分、电子齿轮(2408h/2409h)决定，按实际标定。

    软限位 (soft_limit_min_mm / soft_limit_max_mm) 以回零原点为 0 定义物理行程边界
    (mm)，扫描前用于校验范围、防止撞左右限位；None 表示该方向不校验。
    """

    name: str = "X"
    alias: Optional[int] = None       # 驱动器站号 (拨码 0~63, 存于 0012h)。None=按总线顺序
    position: Optional[int] = None    # 按 EtherCAT 总线顺序 (0-based) 定位；alias 未命中时使用
    direction: int = 1                # 方向 ±1，用于翻转坐标正负
    pulses_per_mm: float = 1000.0     # 脉冲/mm

    # PP 模式运动参数 (CiA 402)
    max_velocity: int = 10000         # 6081h  速度 (pulses/s)
    acceleration: int = 50000         # 6083h  加速度 (pulses/s^2)
    deceleration: int = 50000         # 6084h  减速度 (pulses/s^2)

    # 回零 (HM 模式)
    home_method: int = 17             # 6098h  回零方式 (见 docs/ykd2205pe_ci402.md)
    home_speed_fast: int = 2000       # 6099h:01  找开关速度 (快)
    home_speed_slow: int = 200        # 6099h:02  找零速度 (慢)
    home_accel: int = 50000           # 609Ah  回零加速度
    home_offset: int = 0              # 607Ch  回零后偏移 (pulses)

    # 软限位 (mm, 相对回零原点；None=不校验)
    soft_limit_min_mm: Optional[float] = None   # 负限位(左)软限位位置
    soft_limit_max_mm: Optional[float] = None   # 正限位(右)软限位位置


@dataclass
class ScanConfig:
    """逐点停测 (step & measure) 扫描配置。"""

    # 扫描范围 (mm)
    x_start: float = 0.0
    x_stop: float = 10.0
    x_step: float = 1.0
    y_start: float = 0.0
    y_stop: float = 10.0
    y_step: float = 1.0

    # 采集
    dwell: float = 0.1                # 每点停留/稳定时间 (s)
    n_samples_per_point: int = 1      # 每点采样次数 (取平均)
    sample_interval: float = 0.01     # 多次采样间隔 (s)

    snake: bool = True                # 蛇形往返扫描 (节省回程)
    timeout: float = 10.0             # 单次到位超时 (s)

    # 输出
    output_csv: str = "scan_result.csv"
    output_heatmap: Optional[str] = "scan_result.png"
