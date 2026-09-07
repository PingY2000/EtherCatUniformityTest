#!/usr/bin/env python
"""05 限位/原点开关触发确认 (人手触发，程序读 60FDh，无自动运动)。

前提: 03 已通过。
内容: 逐个确认开关端子接线正确 —— 操作员用手/机构触发开关，程序实时轮询
60FDh 数字输入，看到对应位从 0→1 (触发) 再回到 0 (松开) 才算该项通过。

安全: 本环节不产生自动运动；若开关不在徒手可达处，可在 04 点动把它带到位、
      或先做 06 回零/07 行程测量间接触发，之后再回来补跑本环节。

开关类型 (见 docs: 2310h~2313h 配置): neg=负限位(左) pos=正限位(右) home=原点开关。
只接了一部分就用 --switches 指定，例如只接左右限位:
  python examples/bringup/05_limits.py --ifname "\\Device\\NPF_{GUID}" --alias 0 \
      --switches neg pos
"""
from __future__ import annotations

import sys
import time

from _common import (STEP_TITLES, build_parser, check_prereqs, close,
                     load_state, make_axis, mark, open_master, report,
                     state_path)

KEY = "05"

SW_LABEL = {"neg": "负限位(左)", "pos": "正限位(右)", "home": "原点开关"}
STATE_KEY = {"neg": "neg", "pos": "pos", "home": "home"}


def build_my_parser():
    p = build_parser("05 限位/原点开关触发确认")
    p.add_argument("--switches", nargs="+", default=["neg", "pos", "home"],
                   choices=["neg", "pos", "home"],
                   help="要确认的开关 (默认全三; 按接线取舍)")
    p.add_argument("--press-timeout", type=float, default=180.0,
                   help="等待人工触发的最长秒数")
    return p


def _wait_bit(axis, bit_key: str, want: bool, desc: str,
              timeout: float) -> bool:
    """轮询等待数字输入位变为 want (True=触发)。期间可 Ctrl-C。"""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = axis.read_limit_states() or {}
        if st.get(bit_key) is want:
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    args = build_my_parser().parse_args()
    if not check_prereqs(args, KEY, requires=["03"]):
        return 1

    if args.dry_run:
        for s in args.switches:
            report(f"触发确认 {SW_LABEL.get(s, s)}", True, "(dry-run) 演示，不写进度")
        return 0

    master, err = open_master(args)
    if err:
        report("连接主站/驱动器", False, err)
        return 1
    try:
        axis = make_axis(args, master)
        st0 = axis.read_limit_states() or {}
    except Exception as e:
        report("定位目标轴/读限位", False, str(e))
        close(master)
        return 1

    print("\n操作指引:")
    print("  对每个开关: 请触发它 → 程序看到位变 1 会打印[检测到] → 请松开 → 看到位回 0 记通过。")
    print("  若某项当前已是 1 (轴压在触发区)，程序会先等它松开再要求重新触发。")
    print("  开关不在手边时按 Ctrl-C 退出，之后用 06/07 的运动间接触发。\n")

    confirmed = {}
    all_ok = True
    for s in args.switches:
        key = STATE_KEY[s]
        label = SW_LABEL.get(s, s)
        # 1) 若当前已触发，先等松开
        if st0.get(key):
            print(f"  [{label}] 当前=1(触发区)。请先使其松开回 0…")
            if not _wait_bit(axis, key, False, label, args.press_timeout):
                report(f"触发确认 {label}", False, "等待松开超时")
                all_ok = False
                continue
        # 2) 等触发(按下)
        print(f"  [{label}] 请现在触发开关并保持…")
        if not _wait_bit(axis, key, True, label, args.press_timeout):
            report(f"触发确认 {label}", False, f"等待触发超时({args.press_timeout:.0f}s)，"
                                               "可能未接线/不在手边，可缩小 --switches")
            all_ok = False
            continue
        report(f"触发确认 {label}", True, "位已变 1")
        # 3) 等松开
        print(f"  [{label}] 检测到! 请松开开关…")
        if not _wait_bit(axis, key, False, label, 15.0):
            report(f"松开确认 {label}", False, "松开超时(15s)，可能开关常闭/卡住?")
            all_ok = False
            continue
        confirmed[s] = True
        print(f"  [{label}] 0→1→0 完整往返, 接线 OK\n")

    path = state_path(args)
    state = load_state(path)
    if confirmed:
        # 合并历史确认: 部分开关可分批补跑，进度取并集
        old = state.get("steps", {}).get(KEY, {}).get("data", {})
        old_conf = old.get("confirmed", {})
        merged = {"confirmed": {**old_conf, **{k: True for k in confirmed}}}
        mark(path, state, KEY, bool(all_ok),
             f"已确认开关: {', '.join(SW_LABEL[k] for k in merged['confirmed'])}",
             merged)
        print(f"\n[info] 累计已确认: {[SW_LABEL[k] for k in merged['confirmed']]}")
        print(f"[OK] {STEP_TITLES[KEY]} 本次{'全部通过' if all_ok else '部分通过(未全通过前 07 仍会拦截)'}")
    close(master)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
