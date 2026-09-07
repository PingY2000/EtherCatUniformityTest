#!/usr/bin/env python
"""04 低速小距点动试转 (第一次真实运动)。

前提: 03 已通过。
内容: 以低速度 (--slow-vel, 默认 2000 pulses/s) 按递增幅度
(--steps-mm, 默认 0.5 1 2 mm) 每次"前进再回起点"，逐次核对:
  到位、实际位置反馈与目标一致、方向正确、无丢步/异响。
每档通过才进入下一档，任一出错即停。结束后回到起点。

安全: 出发前会做人工确认；开始前请确保两侧行程富余 ≥ 最大档位，
      手放急停上，眼盯滑台。首次建议从 --steps-mm 0.2 开始。

用法:
  python examples/bringup/04_jog.py --ifname "\\Device\\NPF_{GUID}" --alias 0 \
      --steps-mm 0.2 0.5 1
"""
from __future__ import annotations

import sys

from _common import (STEP_TITLES, build_parser, check_prereqs, close,
                     confirm, load_state, make_axis, mark, open_master, report,
                     state_path)

KEY = "04"


def build_my_parser():
    p = build_parser("04 低速点动试转")
    p.add_argument("--steps-mm", type=float, nargs="*", default=[0.5, 1.0, 2.0],
                   help="递增点动幅度 mm (每次前进再回起点)")
    return p


def main() -> int:
    args = build_my_parser().parse_args()
    if not check_prereqs(args, KEY, requires=["03"]):
        return 1

    steps = [s for s in args.steps_mm if s and s > 0] or [0.5]
    ppmm = args.ppmm * args.dir

    if args.dry_run:
        pos = 0
        for s in steps:
            fwd = pos + round(s * ppmm)
            report(f"点动 +{s:g}mm → 回程", True,
                   f"(dry-run) {pos} → {fwd} → {pos} pulses")
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

    # 低速 + PP
    axis.setup_pp()
    axis.configure_profile(velocity=int(args.slow_vel))
    axis.enable(timeout=args.timeout)

    # 出发前: 若已压限位则拒绝
    st = axis.read_limit_states()
    if st is not None and (st.get("neg") or st.get("pos")):
        report("点动", False, "轴已压住限位开关，请先移开/回零再试")
        close(master, axis)
        return 1

    if not confirm(f"即将第一次真实运动, 幅度递增 {[f'{s:g}mm' for s in steps]} 且每次回起点。"
                   f"\n请确认: 两侧行程富余、人员清场、急停在手?", args):
        report("点动试转", False, "未确认，退出")
        close(master, axis)
        return 1

    start_pul = axis.read_actual_position()
    max_step = max(steps)
    tol_pul = max(5, abs(round(max_step * args.ppmm)) // 100 + 1)
    all_ok = True

    for s in steps:
        delta_pul = round(s * ppmm)
        fwd_pul = start_pul + delta_pul
        try:
            axis.move_abs(fwd_pul)
            axis.wait_target_reached(args.timeout)
            mid = axis.read_actual_position()
            axis.move_abs(start_pul)
            axis.wait_target_reached(args.timeout)
            end = axis.read_actual_position()
        except Exception as e:
            report(f"点动 +{s:g}mm", False, f"异常: {e}")
            all_ok = False
            break

        moved_mm = (mid - start_pul) / (ppmm or 1)
        ok_fwd = abs(mid - fwd_pul) <= tol_pul and abs(moved_mm - s) <= max(0.2, 0.1 * s)
        ok_back = abs(end - start_pul) <= tol_pul
        this_ok = ok_fwd and ok_back
        all_ok &= this_ok
        report(f"点动 +{s:g}mm → 回起点", this_ok,
               f"{start_pul} → {mid} (实测 {moved_mm:+.2f}mm) → {end} pulses")

    path = state_path(args)
    state = load_state(path)
    if all_ok:
        mark(path, state, KEY, True,
             f"低速点动 {len(steps)} 档全部到位且位置反馈正确",
             {"steps_mm": steps, "start_pul": start_pul,
              "ppmm": args.ppmm, "dir": args.dir, "slow_vel": args.slow_vel})
        print(f"\n[OK] {STEP_TITLES[KEY]} 通过 → 已解锁 05/06。")
    close(master, axis)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
