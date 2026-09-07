#!/usr/bin/env python
"""03 使能·状态机练习 (通电，但不产生定位运动)。

前提: 00/01/02 已通过。
内容: 对目标轴做 CiA 402 状态机往返 (去使能→使能→去使能)，
读状态字确认 OperationEnabled 生效与取消，并核对"使能前后实际位置不变"
(证明仅通电保持，没有意外运动)。为第一次真正运动 (04) 做安全铺垫。

注意: 使能会让闭环驱动产生保持力矩，请确保滑台无障碍、人员已清场。

用法:
  python examples/bringup/03_state_machine.py --ifname "\\Device\\NPF_{GUID}" --alias 0
"""
from __future__ import annotations

import sys
import time

from _common import (STEP_TITLES, build_parser, check_prereqs, close,
                     confirm, load_state, make_axis, mark, open_master, report,
                     state_path)

KEY = "03"


def main() -> int:
    args = build_parser("03 使能·状态机练习").parse_args()
    if not check_prereqs(args, KEY, requires=["00", "01", "02"]):
        return 1

    if args.dry_run:
        report("使能(OperationEnabled)", True, "(dry-run) 演示状态机往返，不写进度")
        return 0

    master, err = open_master(args)
    if err:
        report("连接主站/驱动器", False, err)
        return 1

    try:
        axis = make_axis(args, master)
    except Exception as e:
        report("定位目标轴", False, str(e))
        close(master)
        return 1

    # ---- 确认闸门 ----
    if not confirm("即将使能驱动器(保持力矩, 不运动)。确认滑台无障碍、人员已清场?", args):
        report("使能练习", False, "未确认，退出")
        close(master)
        return 1

    pos_before = axis.read_actual_position()
    checks_ok = True

    # 第一次: 去使能→使能
    axis.setup_pp()
    axis.enable(timeout=args.timeout)
    time.sleep(0.1)
    enabled1 = axis.is_enabled
    checks_ok &= report("使能 (OperationEnabled)", enabled1,
                        f"状态字=0x{axis.status:04X}")
    pos_mid = axis.read_actual_position()

    # 第二次: 去使能→再使能
    axis.disable()
    time.sleep(0.1)
    checks_ok &= report("去使能 (撤销 OperationEnabled)", not axis.is_enabled,
                        f"状态字=0x{axis.status:04X}")
    axis.enable(timeout=args.timeout)
    checks_ok &= report("再次使能", axis.is_enabled, f"状态字=0x{axis.status:04X}")
    axis.disable()

    # 使能前后位置不变 (无意外运动)
    drift = pos_mid - pos_before
    checks_ok &= report("使能前后无位移", abs(drift) <= 3,
                        f"位置 {pos_before} → {pos_mid} (Δ{drift} pulses)")

    path = state_path(args)
    state = load_state(path)
    if checks_ok:
        mark(path, state, KEY, True,
             "状态机往返正常，无意外位移", {"pos_before": pos_before, "pos_mid": pos_mid})
        print(f"\n[OK] {STEP_TITLES[KEY]} 通过 → 已解锁 04 低速点动试转。")
    close(master, axis)
    return 0 if checks_ok else 1


if __name__ == "__main__":
    sys.exit(main())
