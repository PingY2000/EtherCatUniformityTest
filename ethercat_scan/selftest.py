"""双轴自检：先找左右(正/负)限位，再回零。

流程: 负限位(左) → 正限位(右) → 回零复位。
自检用慢速 + 小步长 + 最大行程保护，逐点检测开关触发；
左右限位触发时的轴实际位置会被记录并返回，供界面显示，
作为设置软限位 (soft_limit_min_mm / soft_limit_max_mm) 的参考。
面向真实硬件 (YkdDrive)。模拟轴无开关读取能力，会被判定为不支持。
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
    neg_pos_mm: Optional[float] = None   # 左(负)限位触发时轴位置 (mm, 软限位参考)
    pos_pos_mm: Optional[float] = None   # 右(正)限位触发时轴位置 (mm)
    span_mm: Optional[float] = None      # 左右限位间距 = |pos - neg| (mm)

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


def _axis_pos_mm(ax) -> float:
    """读轴实际位置并换算成 mm (与 GUI/扫描坐标同一参考)。"""
    return ax.read_actual_position() / (ax.pulses_per_mm * ax.direction)


def _seek_limit(ax, sign: int, step_mm: float, max_mm: float,
                timeout: float, should_stop: Optional[Callable[[], bool]]):
    """向 sign 方向步进，直到该侧限位开关触发。

    sign<0 找负限位(左)、sign>0 找正限位(右)。
    返回 (ok, pos_mm): pos_mm 为触发时 (或搜索终止时) 的轴实际位置 (mm)。
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
            return False, _axis_pos_mm(ax)
        if (sign < 0 and st.get("neg")) or (sign > 0 and st.get("pos")):
            return True, _axis_pos_mm(ax)
    return False, _axis_pos_mm(ax)


def run_axis_selftest(ax, step_mm: float = 0.5, max_mm: float = 500.0,
                      timeout: float = 10.0, slow_velocity: int = 200,
                      should_stop: Optional[Callable[[], bool]] = None) -> AxisCheckResult:
    """单轴自检：负限位(左) → 正限位(右) → 回零。返回 AxisCheckResult。

    左右限位触发时轴的实际位置记录在 neg_pos_mm / pos_pos_mm (mm)，
    供界面显示并作为软限位参考；自检结束时轴已回零复位。
    """
    if not can_selftest(ax):
        return AxisCheckResult(ax.name, False, False, False,
                               "该轴无 move_rel/read_limit_states (模拟轴?)，无法自检")

    # 低速 + PP 模式，降低撞限位冲击
    if hasattr(ax, "setup_pp"):
        ax.setup_pp()
    if hasattr(ax, "configure_profile"):
        ax.configure_profile(velocity=slow_velocity)
    ax.enable()

    neg_pos_mm = pos_pos_mm = None

    # 1) 负限位(左)
    try:
        neg_ok, neg_pos_mm = _seek_limit(ax, -1, step_mm, max_mm, timeout, should_stop)
        neg_detail = (f"左限位触发@{neg_pos_mm:+.1f}mm" if neg_ok
                      else f"左限位未触发(走满{max_mm}mm)")
    except Exception as e:
        neg_ok, neg_detail = False, f"异常:{e}"

    # 2) 正限位(右)
    try:
        pos_ok, pos_pos_mm = _seek_limit(ax, +1, step_mm, max_mm * 2, timeout, should_stop)
        pos_detail = f"右限位触发@{pos_pos_mm:+.1f}mm" if pos_ok else "右限位未触发"
    except Exception as e:
        pos_ok, pos_detail = False, f"异常:{e}"

    # 3) 回零 (把轴带回原点，恢复干净状态)
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

    span_mm = None
    if neg_pos_mm is not None and pos_pos_mm is not None:
        span_mm = abs(pos_pos_mm - neg_pos_mm)

    detail = (f"左限位[{neg_detail}] 右限位[{pos_detail}] 回零[{home_detail}]")
    return AxisCheckResult(ax.name, home_ok, neg_ok, pos_ok, detail,
                           neg_pos_mm=neg_pos_mm, pos_pos_mm=pos_pos_mm,
                           span_mm=span_mm)
