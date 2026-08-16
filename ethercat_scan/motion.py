"""轴抽象接口与模拟轴。

真实驱动器 (drive.YkdDrive) 与模拟轴 (SimulatedAxis) 实现同一接口，
扫描逻辑只依赖本接口，因此无硬件时也能跑通全流程 (dry-run)。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod


class Axis(ABC):
    """一个运动轴需要实现的最小接口。"""

    def __init__(self, name: str, pulses_per_mm: float = 1.0, direction: int = 1):
        self.name = name
        self.pulses_per_mm = pulses_per_mm
        self.direction = direction

    @abstractmethod
    def enable(self) -> None:
        """使能 (CiA 402 Operation Enabled)。"""

    @abstractmethod
    def home(self) -> None:
        """回零。"""

    @abstractmethod
    def move_abs(self, position: int) -> None:
        """绝对定位。position 单位: 脉冲。"""

    @abstractmethod
    def wait_target_reached(self, timeout: float = 10.0) -> bool:
        """等待到位。"""

    @abstractmethod
    def read_actual_position(self) -> int:
        """读实际位置 (脉冲)。"""


class SimulatedAxis(Axis):
    """模拟轴: 无硬件时验证框架逻辑 (dry-run)。立即"到位"。"""

    def __init__(self, name: str = "X", pulses_per_mm: float = 1.0, direction: int = 1,
                 travel_time: float = 0.0):
        super().__init__(name, pulses_per_mm, direction)
        self.travel_time = travel_time
        self._pos = 0

    def enable(self) -> None:
        pass

    def home(self) -> None:
        self._pos = 0

    def move_abs(self, position: int) -> None:
        if self.travel_time > 0:
            time.sleep(self.travel_time)
        self._pos = position

    def wait_target_reached(self, timeout: float = 10.0) -> bool:
        return True

    def read_actual_position(self) -> int:
        return self._pos
