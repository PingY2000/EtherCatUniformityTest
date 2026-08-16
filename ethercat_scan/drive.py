"""YKD2205PE 驱动器封装 (CiA 402, PP 模式)。

默认用 SDO 控制逐点定位，简单可靠、适合 step & measure。
对象字典索引与位定义详见 docs/ykd2205pe_ci402.md。
"""
from __future__ import annotations

import struct
import time

from .config import AxisConfig
from .motion import Axis

# ---- CiA 402 对象: (索引, 子索引, struct 格式) ----
_OBJ = {
    "control_word": (0x6040, 0x00, "H"),
    "status_word": (0x6041, 0x00, "H"),
    "mode_of_op": (0x6060, 0x00, "b"),
    "mode_display": (0x6061, 0x00, "b"),
    "actual_pos": (0x6064, 0x00, "i"),
    "target_pos": (0x607A, 0x00, "I"),
    "home_offset": (0x607C, 0x00, "i"),
    "profile_vel": (0x6081, 0x00, "I"),
    "profile_acc": (0x6083, 0x00, "I"),
    "profile_dec": (0x6084, 0x00, "I"),
    "home_method": (0x6098, 0x00, "b"),
    "home_speed": (0x6099, 0x00, "I"),   # 子索引 1=找开关(快) 2=找零(慢)
    "home_acc": (0x609A, 0x00, "I"),
}

MODE_PP, MODE_PV, MODE_HM, MODE_CSP = 1, 3, 6, 8

# 控制字 (6040h) 位
CW_SWITCH_ON = 1 << 0
CW_ENABLE_VOLT = 1 << 1
CW_QUICK_STOP = 1 << 2
CW_ENABLE_OP = 1 << 3
CW_NEW_SETPOINT = 1 << 4
CW_CHANGE_IMMED = 1 << 5
CW_ABS_REL = 1 << 6      # 0=绝对, 1=相对
CW_FAULT_RESET = 1 << 7
CW_HALT = 1 << 8

# 状态字 (6041h) 位
SW_READY = 1 << 0
SW_SWITCHED_ON = 1 << 1
SW_OP_ENABLED = 1 << 2
SW_FAULT = 1 << 3
SW_TARGET_REACHED = 1 << 10
SW_SETPOINT_ACK = 1 << 12

# 使能后的控制字基础值 (bit0~3 = 1)
_OP_BASE = CW_SWITCH_ON | CW_ENABLE_VOLT | CW_QUICK_STOP | CW_ENABLE_OP  # 0x0F


class DriveError(RuntimeError):
    pass


class YkdDrive(Axis):
    """一台 YKD2205PE 驱动器 = 一个轴。"""

    def __init__(self, slave, config: AxisConfig):
        super().__init__(config.name, config.pulses_per_mm, config.direction)
        self.slave = slave
        self.cfg = config

    # ---------- SDO 底层 ----------
    def _read(self, key, sub=None):
        idx, s, fmt = _OBJ[key]
        data = self.slave.sdo_read(idx, s if sub is None else sub)
        n = struct.calcsize(fmt)
        if not data or len(data) < n:
            raise DriveError(f"{self.name}: SDO 读取 {key}({idx:#x}) 失败")
        return struct.unpack("<" + fmt, data[:n])[0]

    def _write(self, key, value, sub=None):
        idx, s, fmt = _OBJ[key]
        self.slave.sdo_write(idx, s if sub is None else sub, struct.pack("<" + fmt, value))

    def _write_cw(self, value: int):
        self._write("control_word", value & 0xFFFF)

    def _wait(self, cond, timeout: float, what: str):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if cond():
                return True
            time.sleep(0.01)
        raise DriveError(f"{self.name}: 等待 {what} 超时 ({timeout:.1f}s)")

    @property
    def status(self) -> int:
        return self._read("status_word")

    @property
    def is_enabled(self) -> bool:
        return bool(self.status & SW_OP_ENABLED)

    @property
    def is_fault(self) -> bool:
        return bool(self.status & SW_FAULT)

    # ---------- 使能 ----------
    def enable(self, timeout: float = 3.0):
        if self.is_fault:
            self._write_cw(CW_FAULT_RESET)
            time.sleep(0.05)
            self._write_cw(CW_ENABLE_VOLT | CW_QUICK_STOP)  # 0x06
            time.sleep(0.05)
        if not (self.status & SW_READY):
            self._write_cw(CW_ENABLE_VOLT | CW_QUICK_STOP)
            self._wait(lambda: bool(self.status & SW_READY), 1.0, "ReadyToSwitchOn")
        if not (self.status & SW_SWITCHED_ON):
            self._write_cw(CW_SWITCH_ON | CW_ENABLE_VOLT | CW_QUICK_STOP)  # 0x07
            self._wait(lambda: bool(self.status & SW_SWITCHED_ON), 1.0, "SwitchedOn")
        if not self.is_enabled:
            self._write_cw(_OP_BASE)  # 0x0F
            self._wait(lambda: self.is_enabled, timeout, "OperationEnabled")

    def disable(self):
        self._write_cw(CW_ENABLE_VOLT | CW_QUICK_STOP)  # 0x06 断电

    # ---------- 模式与运动 ----------
    def set_mode(self, mode: int):
        self._write("mode_of_op", mode)
        time.sleep(0.02)

    def configure_profile(self, velocity=None, accel=None, decel=None):
        if velocity is not None:
            self._write("profile_vel", int(velocity))
        if accel is not None:
            self._write("profile_acc", int(accel))
        if decel is not None:
            self._write("profile_dec", int(decel))

    def setup_pp(self):
        """配置并切换到 Profile Position 模式。"""
        self.set_mode(MODE_PP)
        self.configure_profile(self.cfg.max_velocity, self.cfg.acceleration, self.cfg.deceleration)

    def move_abs(self, position: int):
        """绝对定位 (PP)。position 单位: 脉冲。"""
        self._write("target_pos", int(position))
        self._write_cw(_OP_BASE | CW_CHANGE_IMMED)                       # 清 bit4
        self._write_cw(_OP_BASE | CW_CHANGE_IMMED | CW_NEW_SETPOINT)     # 置 bit4 触发

    def move_rel(self, delta: int):
        """相对定位 (PP)。"""
        self._write("target_pos", int(delta))
        self._write_cw(_OP_BASE | CW_CHANGE_IMMED | CW_ABS_REL)                       # bit6=1 相对
        self._write_cw(_OP_BASE | CW_CHANGE_IMMED | CW_ABS_REL | CW_NEW_SETPOINT)

    def wait_target_reached(self, timeout: float = 10.0) -> bool:
        # 1) 等驱动器确认新目标(bit12)或直接到位(bit10)
        self._wait(lambda: bool(self.status & (SW_SETPOINT_ACK | SW_TARGET_REACHED)),
                   timeout, "新目标确认")
        # 2) 清 new set-point(bit4)，驱动器随之清 bit12
        self._write_cw(_OP_BASE | CW_CHANGE_IMMED)
        # 3) 等到位(bit10)
        self._wait(lambda: bool(self.status & SW_TARGET_REACHED), timeout, "到位")
        return True

    def read_actual_position(self) -> int:
        return self._read("actual_pos")

    # ---------- 回零 (HM) ----------
    def home(self, timeout: float = 30.0):
        self.set_mode(MODE_HM)
        self._write("home_method", self.cfg.home_method)
        self._write("home_speed", self.cfg.home_speed_fast, sub=0x01)   # 找开关(快)
        self._write("home_speed", self.cfg.home_speed_slow, sub=0x02)   # 找零(慢)
        self._write("home_acc", self.cfg.home_accel)
        self._write("home_offset", self.cfg.home_offset)
        self.enable()
        self._write_cw(_OP_BASE)                          # 清 bit4
        self._write_cw(_OP_BASE | CW_NEW_SETPOINT)        # bit4=1 启动回零
        return self._wait(lambda: bool(self.status & SW_TARGET_REACHED), timeout, "回零完成")
