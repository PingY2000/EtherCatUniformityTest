#!/usr/bin/env python
"""07 行程标定与软限位建议 (链收尾)。

前提: 05 (开关接线已确认) + 06 (原点已建立) 已通过。
内容: 以低速自动爬向负限位→正限位(找行程两端)→再回零 (复用 selftest)，
记录两端触发位置 (相对 06 原点, mm) 与总行程，按安全余量 (--margin-mm)
给出软限位建议，存档供填写 GUI/run_scan/run_verify 的 soft limit 字段。

安全: 会沿整个行程慢速爬行，请确认已通过 05 开关确认、急停在手。

用法:
  python examples/bringup/07_soft_limits.py --ifname "\\Device\\NPF_{GUID}" --alias 0 \
      --margin-mm 2.0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (PROJECT_ROOT, STEP_TITLES, build_parser, check_prereqs,
                     close, confirm, load_state, make_axis, mark, open_master,
                     report, state_path)

KEY = "07"


def build_my_parser():
    p = build_parser("07 行程标定与软限位建议")
    p.add_argument("--margin-mm", type=float, default=2.0,
                   help="软限位距硬限位开关的安全余量 mm")
    p.add_argument("--out", default=None, help="建议结果 JSON 路径")
    return p


def main() -> int:
    args = build_my_parser().parse_args()
    if not check_prereqs(args, KEY, requires=["05", "06"]):
        return 1

    if args.dry_run:
        report("行程两端触发", True, "(dry-run) 模拟: 左=0mm 右=100mm 行程=100mm")
        return 0

    from ethercat_scan.selftest import can_selftest, run_axis_selftest

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

    if not can_selftest(axis):
        report("行程标定", False, "该轴不支持自检所需的限位读取/相对运动")
        close(master)
        return 1

    if not confirm("即将沿全行程慢速爬行找两端限位并回零。确认已通过 05 接线确认、急停在手?", args):
        report("行程标定", False, "未确认，退出")
        close(master)
        return 1

    try:
        res = run_axis_selftest(axis, slow_velocity=int(args.slow_vel))
    except Exception as e:
        report("行程标定执行", False, f"异常: {e}")
        close(master, axis)
        return 1

    # 结果 (位置为相对 06 原点的 mm)
    lo_raw, hi_raw = min(res.neg_pos_mm, res.pos_pos_mm), max(res.neg_pos_mm, res.pos_pos_mm)
    travel = res.span_mm or abs(hi_raw - lo_raw)
    detail = (f"负限位@{res.neg_pos_mm:+.2f}mm 正限位@{res.pos_pos_mm:+.2f}mm "
              f"行程≈{travel:.2f}mm")
    report("左右限位触发 (自检)", res.neg_ok and res.pos_ok, detail)
    report("回零复位", res.home_ok, "")

    if not res.ok or travel <= 0:
        report("行程标定", False, "未得到有效行程，请检查开关接线/方向后再跑")
        close(master, axis)
        return 1

    # 建议软限位: 物理边界向内让出 margin (允许稍越界报警由上层校验, 这里只给建议)
    lo_sugg = lo_raw + args.margin_mm
    hi_sugg = hi_raw - args.margin_mm
    if args.margin_mm > 0 and args.margin_mm >= travel / 3:
        print(f"[warn] 余量 {args.margin_mm:g}mm 相对行程 {travel:.2f}mm 偏大, 建议减小 --margin-mm")

    print(f"\n===== {args.name} 轴软限位建议 (相对原点) =====")
    print(f"  实测硬限位: 负(左) {lo_raw:+.2f}mm   正(右) {hi_raw:+.2f}mm   行程 {travel:.2f}mm")
    print(f"  建议软限位: 下限 {lo_sugg:+.2f}mm  上限 {hi_sugg:+.2f}mm   (余量 {args.margin_mm:g}mm)")
    print(f"  可用于 run_scan/run_verify/GUI:  --soft-min {lo_sugg:.2f} --soft-max {hi_sugg:.2f}")

    data = {
        "neg_mm": res.neg_pos_mm, "pos_mm": res.pos_pos_mm, "travel_mm": travel,
        "margin_mm": args.margin_mm,
        "soft_min_sugg_mm": lo_sugg, "soft_max_sugg_mm": hi_sugg,
        "home_method": args.home_method, "home_offset": args.home_offset,
    }
    path = state_path(args)
    state = load_state(path)
    mark(path, state, KEY, True, detail, data)

    out = Path(args.out or PROJECT_ROOT / f"bringup_softlimits_{args.name}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[存档] 建议 → {out}")

    # ---- 链总结 ----
    print("\n============== 装机导入链进度 ==============")
    for k in sorted(state["steps"], key=int):
        st = state["steps"][k]
        flag = "PASS" if st["ok"] is True else "FAIL"
        print(f"  [{flag}] {STEP_TITLES.get(k, k)}  --  {st.get('detail', '')}")
    print(f"\n设备导入链已完成! 可再用 examples/run_verify.py 做一键复验。")
    close(master, axis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
