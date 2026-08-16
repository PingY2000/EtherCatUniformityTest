"""EtherCAT 主站封装 (基于 pysoem)。"""
from __future__ import annotations

import time
from typing import List, Optional

try:
    import pysoem
except ImportError:  # 允许 --dry-run 在未装 pysoem 时也能运行
    pysoem = None

from .config import AxisConfig

# YKD2205PE 识别信息 (见 docs/ykd2205pe_ci402.md, 1018h)
YKD_VENDOR_ID = 0x0994
YKD_PRODUCT_CODE = 0x2000


class EtherCATError(RuntimeError):
    pass


class EtherCATMaster:
    """打开网卡、配置从站、进入运行状态、按站号/位置定位驱动器。"""

    def __init__(self, ifname: str):
        if pysoem is None:
            raise EtherCATError("未安装 pysoem，请先 `pip install pysoem` 并安装 Npcap。")
        self.ifname = ifname
        self.master = None

    def open(self) -> int:
        """打开网卡并初始化从站配置，返回从站数量。"""
        self.master = pysoem.Master()
        self.master.open(self.ifname)
        n = self.master.config_init()
        if n <= 0:
            raise EtherCATError(f"总线上未发现从站 (config_init={n})，检查网卡/线缆/供电。")
        self.master.config_map()
        return n

    def find_drives(self) -> List:
        """按 product code 识别所有 YKD2205PE 驱动器。"""
        return [
            s for s in self.master.slaves
            if getattr(s, "man", None) == YKD_VENDOR_ID
            and getattr(s, "id", None) == YKD_PRODUCT_CODE
        ]

    @staticmethod
    def _slave_alias(slave) -> Optional[int]:
        """从站配置站号 (SII/0012h, 由拨码设定)。"""
        alias = getattr(slave, "configalias", None)
        if alias is None:
            alias = getattr(slave, "alias", None)
        return int(alias) if alias not in (None, 0) else None

    def resolve_slave(self, cfg: AxisConfig):
        """根据 AxisConfig 定位从站: 优先站号(alias)，其次总线位置(position)。"""
        if cfg.alias is not None:
            for s in self.master.slaves:
                if self._slave_alias(s) == cfg.alias:
                    return s
            raise EtherCATError(f"未找到站号={cfg.alias} 的从站，请检查拨码")
        if cfg.position is not None and 0 <= cfg.position < len(self.master.slaves):
            return self.master.slaves[cfg.position]
        raise EtherCATError(f"轴 {cfg.name} 既未配置 alias 也未配置有效 position")

    def make_drive(self, cfg: AxisConfig):
        from .drive import YkdDrive
        return YkdDrive(self.resolve_slave(cfg), cfg)

    # ---------- 状态机 ----------
    def _wait_state(self, state, timeout_s: float) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            self.master.read_state()
            if all(s.state == state for s in self.master.slaves):
                return True
            time.sleep(0.02)
        return False

    def go_op(self, timeout_s: float = 2.0) -> str:
        """尝试进入 OP，失败则回退 SAFEOP/PREOP (SDO 仍可用)。返回实际状态名。"""
        for state, name in [(pysoem.OP_STATE, "OP"),
                            (pysoem.SAFEOP_STATE, "SAFEOP"),
                            (pysoem.PREOP_STATE, "PREOP")]:
            self.master.state = state
            self.master.write_state()
            if self._wait_state(state, timeout_s):
                if state != pysoem.OP_STATE:
                    print(f"[warn] 从站未进入 OP，当前 {name} (SDO 控制仍可用)")
                return name
        raise EtherCATError("从站无法进入 OP/SAFEOP/PREOP")

    def close(self):
        if self.master is not None:
            self.master.close()
