"""功率计抽象接口与实现。

采集目标设备尚未最终确定，这里提供:
- PowerMeter           抽象基类 (measure() 返回功率, 单位 W)
- SimulatedPowerMeter  模拟二维高斯光斑功率，用于 dry-run
- ScpiPowerMeter       基于 pyvisa 的 SCPI 功率计骨架 (Thorlabs/Newport/Keysight)
- SerialPowerMeter     串口 SCPI 功率计骨架

接入真实设备时，继承 PowerMeter 或直接照 Scpi/Serial 骨架填指令即可。
"""
from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod


class PowerMeter(ABC):
    @abstractmethod
    def open(self) -> None:
        """打开/连接设备。"""

    @abstractmethod
    def measure(self) -> float:
        """读一次功率，返回 W。"""

    @abstractmethod
    def close(self) -> None:
        """关闭/释放设备。"""


class SimulatedPowerMeter(PowerMeter):
    """模拟一个二维高斯光斑的功率分布，便于无硬件跑通全流程。"""

    def __init__(self, center=(5.0, 5.0), sigma=2.0, peak=1.0, noise=0.005):
        self.cx, self.cy = center
        self.sigma = sigma
        self.peak = peak
        self.noise = noise
        self._x = self._y = 0.0

    def open(self) -> None:
        pass

    def set_position(self, x_mm: float, y_mm: float) -> None:
        """供 Scanner 在采样前告知当前坐标 (真实功率计不需要)。"""
        self._x, self._y = x_mm, y_mm

    def measure(self) -> float:
        r2 = (self._x - self.cx) ** 2 + (self._y - self.cy) ** 2
        v = self.peak * math.exp(-r2 / (2 * self.sigma ** 2))
        if self.noise:
            v += random.uniform(-self.noise, self.noise)
        return max(0.0, v)

    def close(self) -> None:
        pass


class ScpiPowerMeter(PowerMeter):
    """基于 pyvisa 的 SCPI 功率计 (骨架)。

    TODO: 按实际仪器填 measure_cmd。示例 (Thorlabs PM100D):
        "MEASure:POWer?"  -> 返回当前功率 (W)
    """

    def __init__(self, resource: str, measure_cmd: str = "MEASure:POWer?"):
        self.resource = resource
        self.measure_cmd = measure_cmd
        self._instr = None

    def open(self) -> None:
        import pyvisa
        rm = pyvisa.ResourceManager()
        self._instr = rm.open_resource(self.resource)
        self._instr.timeout = 3000

    def measure(self) -> float:
        return float(self._instr.query(self.measure_cmd))

    def close(self) -> None:
        if self._instr is not None:
            self._instr.close()


class SerialPowerMeter(PowerMeter):
    """串口 SCPI 功率计 (骨架)。

    TODO: 按实际仪器填波特率与指令。用 pyserial 收发，指令以换行终结。
    """

    def __init__(self, port: str, baudrate: int = 9600, measure_cmd: str = "MEAS:POW?\n"):
        self.port = port
        self.baudrate = baudrate
        self.measure_cmd = measure_cmd
        self._ser = None

    def open(self) -> None:
        import serial
        self._ser = serial.Serial(self.port, self.baudrate, timeout=1)

    def measure(self) -> float:
        self._ser.reset_input_buffer()
        self._ser.write(self.measure_cmd.encode())
        line = self._ser.readline().decode().strip()
        return float(line)

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
