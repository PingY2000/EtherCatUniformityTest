#!/usr/bin/env python
"""06 回零与原点标定 (首次自动回零，会运动到开关)。

前提: 04 已通过 (方向/运动已验证)。
内容: 按 --home-method (6098h: 17负限位 18正限位 24/29原点开关) 执行回零，
确认到位且回零后实际位置≈目标原点 (默认 0; 若设了 --home-offset 则以其为准)。
通过后本轴就有了"原点"，后续 07 测得的限位位置都以它为参考。

安全: 回零会朝开关方向自动移动，请确认行程内无障碍、急停在手。
      首次若方向不对，会在较远处触发另一个开关/到行程端——随时可按急停。

用法:
  python examples/bringup/06_home.py --ifname "\\Device\\NPF_{GUID}" --alias 0 \
      --home-method 24
"""
from __future__ import annotations

import sys

from _common import (STEP_TITLES, axis_pos_mm, build_parser, check_prereqs,
                     close, confirm, load_state, make_axis, mark, open_master,
                     report, state_path)

KEY = "06"

METHOD_DESC = {17: "负限位回零", 18: "正限位回零", 24: "原点开关(双向)", 29: "原点开关(单向)"}


def main() -> int:
    args = build_parser("06 回零与原点标定").parse_args()
    if not check_prereqs(args, KEY, requires=["04"]):
        return 1

    if args.dry_run:
        report("回零", True, "(dry-run) 模拟回零成功，位置=0mm")
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

    if not confirm(f"即将回零 (方式 {args.home_method} = {METHOD_DESC.get(args.home_method, '?')})，"
                   f"轴会自动移动去找开关。确认无障碍、急停在手?", args):
        report("回零", False, "未确认，退出")
        close(master)
        return 1

    axis.setup_pp()
    axis.enable(timeout=args.timeout)
    try:
        axis.home(timeout=args.timeout * 3)
    except Exception as e:
        report("回零执行", False, f"异常: {e}")
        close(master, axis)
        return 1

    pos_pul = axis.read_actual_position()
    pos_mm = axis_pos_mm(axis)
    expected_mm = args.home_offset / (args.ppmm * args.dir) if (args.ppmm * args.dir) else 0.0
    ok = abs(pos_mm - expected_mm) <= 0.2
    report("回零到位/原点校验", ok,
           f"实际位置 {pos_mm:+.3f}mm ({pos_pul} pulses), 期望 {expected_mm:+.3f}mm")

    path = state_path(args)
    state = load_state(path)
    if ok:
        mark(path, state, KEY, True,
             f"回零完成({METHOD_DESC.get(args.home_method)})，原点 {pos_mm:+.3f}mm",
             {"pos_mm": pos_mm, "pos_pul": pos_pul, "home_method": args.home_method,
              "home_offset": args.home_offset})
        print(f"\n[OK] {STEP_TITLES[KEY]} 通过 → 原点已建立，可进入 07 标定行程/软限位。")
    close(master, axis)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
