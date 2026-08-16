"""EtherCAT 双轴滑台扫描采集框架。

组件:
- config      轴/扫描配置 (dataclass)
- motion      轴抽象接口 + 模拟轴
- drive       YKD2205PE 驱动器封装 (CiA 402, PP 模式)
- master      EtherCAT 主站封装 (pysoem)
- power_meter 功率计抽象接口 + 模拟/SCPI/串口实现
- scanner     逐点停测 (step & measure) 扫描主循环

用法见 README.md 与 examples/run_scan.py。
"""
from .config import AxisConfig, ScanConfig
from .motion import Axis, SimulatedAxis
from .power_meter import PowerMeter, SimulatedPowerMeter
from .scanner import Scanner

__all__ = [
    "AxisConfig",
    "ScanConfig",
    "Axis",
    "SimulatedAxis",
    "PowerMeter",
    "SimulatedPowerMeter",
    "Scanner",
]
