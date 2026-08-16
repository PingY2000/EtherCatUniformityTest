"""双轴自检：逐项检测负限位、正限位、原点开关。

面向真实硬件 (YkdDrive)。模拟轴无开关读取能力，会被判定为不支持。
自检用慢速 + 小步长 + 最大行程保护，逐点检测开关触发。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class AxisCheckResult:
    name: str
    home_ok: bool
    neg_ok: bool
    pos_ok: bool
    detail: str

    @property
    def ok(self) -> bool:
        return self.home_ok and self.neg_ok and self.pos_ok


def can_selftest(ax) -> bool:
    """判断该轴是否具备自检所需的开关读取与相对定位能力。

    模拟轴虽有 read_limit_states 方法但返回 None (无硬件开关)，故视为不支持。
    """
    if not hasattr(ax, "move_rel"):
        return False
    try:
        return ax.read_limit_states() is not None
    except Exception:
        return False


def _seek_limit(ax, sign: int, step_mm: float, max_mm: float,
                timeout: float, should_stop: Optional[Callable[[], bool]]):
    """向 sign 方向步进，直到该侧限位开关触发。

    sign<0 找负限位、sign>0 找正限位。返回 (ok, traveled_mm)。
    """
    ppmm = ax.pulses_per_mm * ax.direction
    step_pul = int(round(step_mm * ppmm)) or 1
    traveled = 0.0
    while traveled < max_mm:
        if should_stop and should_stop():
            raise RuntimeError("自检被中止")
        ax.move_rel(sign * step_pul)
        if not ax.wait_target_reached(timeout):
            raise RuntimeError(f"{ax.name} 到位超时")
        traveled += step_mm
        st = ax.read_limit_states()
        if st is None:
            return False, traveled
        if (sign < 0 and st.get("neg")) or (sign > 0 and st.get("pos")):
            return True, traveled
    return False, traveled


def run_axis_selftest(ax, step_mm: float = 0.5, max_mm: float = 500.0,
                      timeout: float = 10.0, slow_velocity: int = 200,
                      should_stop: Optional[Callable[[], bool]] = None) -> AxisCheckResult:
    """单轴自检：回零(原点) → 负限位 → 正限位。返回 AxisCheckResult。"""
    if not can_selftest(ax):
        return AxisCheckResult(ax.name, False, False, False,
                               "该轴无 move_rel/read_limit_states (模拟轴?)，无法自检")

    # 低速 + PP 模式，降低撞限位冲击
    if hasattr(ax, "setup_pp"):
        ax.setup_pp()
    if hasattr(ax, "configure_profile"):
        ax.configure_profile(velocity=slow_velocity)
    ax.enable()

    # 1) 原点 (回零成功即认为原点开关正常)
    try:
        ax.home()
        home_ok, home_detail = True, "回零成功"
    except Exception as e:
        home_ok, home_detail = False, f"回零失败:{e}"

    # 回零切到 HM 模式，恢复 PP 低速
    if hasattr(ax, "setup_pp"):
        ax.setup_pp()
    if hasattr(ax, "configure_profile"):
        ax.configure_profile(velocity=slow_velocity)

    # 2) 负限位
    try:
        neg_ok, neg_mm = _seek_limit(ax, -1, step_mm, max_mm, timeout, should_stop)
        neg_detail = f"触发@{neg_mm:.1f}mm" if neg_ok else f"未触发(走满{max_mm}mm)"
    except Exception as e:
        neg_ok, neg_detail = False, f"异常:{e}"

    # 3) 正限位
    try:
        pos_ok, pos_mm = _seek_limit(ax, +1, step_mm, max_mm * 2, timeout, should_stop)
        pos_detail = f"触发@{pos_mm:.1f}mm" if pos_ok else "未触发"
    except Exception as e:
        pos_ok, pos_detail = False, f"异常:{e}"

    # 4) 回零复位 (把轴带回原点，恢复干净状态)
    try:
        ax.home()
        reset_detail = "已回零"
    except Exception as e:
        reset_detail = f"回零失败:{e}"

    detail = (f"原点[{home_detail}] 负限位[{neg_detail}] "
              f"正限位[{pos_detail}] 复位[{reset_detail}]")
    return AxisCheckResult(ax.name, home_ok, neg_ok, pos_ok, detail)
