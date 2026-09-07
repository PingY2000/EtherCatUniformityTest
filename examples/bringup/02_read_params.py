#!/usr/bin/env python
"""02 参数读取·核对·存档 (只读，无运动)。

前提: 01 已通过。
内容: 读取目标轴 (按 --alias) 驱动器的身份信息与 CiA 402 / 限位参数，
打印成核对表供与名牌、拨码、电机丝杠规格逐项比对，并把完整原始值
存档为 JSON (留档/追溯)。这一环不写任何参数、不产生运动。

读不到的可选对象会显示 "未提供" (不判失败)；判定"通过"只需身份 +
状态字 + 实际位置能正常读回 (证明 SDO 双向可用)。

用法:
  python examples/bringup/02_read_params.py --ifname "\\Device\\NPF_{GUID}" --alias 0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (PROJECT_ROOT, STEP_TITLES, build_parser, check_prereqs,
                     load_state, make_axis, mark, open_master, report,
                     sdo_i32, sdo_str, sdo_u16, sdo_u32, state_path)
from ethercat_scan.master import YKD_PRODUCT_CODE, YKD_VENDOR_ID

KEY = "02"

TERMINAL_FUNC = {  # 端子功能 (2310h~2313h 值) 见 docs/ykd2205pe_ci402.md
    1: "原点", 2: "正限位", 3: "负限位", 4: "停止", 5: "急停", 6: "MF",
    7: "探针1", 8: "探针2", 9: "用户自定义", 10: "用户自定义", 11: "用户自定义", 12: "用户自定义",
}


def _try(fn, default="未提供"):
    try:
        return fn()
    except Exception:
        return default


def build_my_parser():
    p = build_parser("02 参数读取·核对·存档")
    p.add_argument("--out", default=None,
                   help=f"存档 JSON 路径 (默认 {PROJECT_ROOT / 'bringup_params_<name>_a<alias>.json'})")
    return p


def _term(slave, sub):
    v = _try(lambda: sdo_u32(slave, 0x2310, sub), None)
    if not isinstance(v, int):
        return v
    return f"{v} ({TERMINAL_FUNC.get(v, '?')})"


def main() -> int:
    args = build_my_parser().parse_args()
    if not check_prereqs(args, KEY, requires=["01"]):
        return 1

    params = {}
    if args.dry_run:
        report("读取身份/参数", True, "(dry-run) 演示，不写进度")
        return 0

    master, err = open_master(args)
    if err:
        report("连接主站/驱动器", False, err)
        return 1
    try:
        axis = make_axis(args, master)
        slave = axis.slave
    except Exception as e:
        report("定位目标轴 (站号)", False, str(e))
        try:
            master.close()
        except Exception:
            pass
        return 1

    # ---- 身份 (1018h / 1008h) ----
    identity = {
        "vendor_expected": hex(YKD_VENDOR_ID),
        "product_expected": hex(YKD_PRODUCT_CODE),
        "vendor(1018:01)": _try(lambda: hex(sdo_u32(slave, 0x1018, 1))),
        "product(1018:02)": _try(lambda: hex(sdo_u32(slave, 0x1018, 2))),
        "revision(1018:03)": _try(lambda: hex(sdo_u32(slave, 0x1018, 3))),
        "serial(1018:04)": _try(lambda: sdo_u32(slave, 0x1018, 4)),
        "device_name(1008h)": _try(lambda: sdo_str(slave, 0x1008)),
    }
    params["identity"] = identity

    # ---- CiA 402 / 运动 ----
    motion = {
        "status_word(6041h)": _try(lambda: hex(sdo_u16(slave, 0x6041))),
        "mode_of_op(6060h)": _try(lambda: sdo_u16(slave, 0x6060)),
        "actual_pos(6064h)_pulses": _try(lambda: sdo_i32(slave, 0x6064)),
        "profile_vel(6081h)": _try(lambda: sdo_u32(slave, 0x6081)),
        "profile_acc(6083h)": _try(lambda: sdo_u32(slave, 0x6083)),
        "profile_dec(6084h)": _try(lambda: sdo_u32(slave, 0x6084)),
        "home_offset(607Ch)": _try(lambda: sdo_i32(slave, 0x607C)),
        "home_method(6098h)": _try(lambda: sdo_u16(slave, 0x6098)),
        "home_speed_fast(6099h:01)": _try(lambda: sdo_u32(slave, 0x6099, 1)),
        "home_speed_slow(6099h:02)": _try(lambda: sdo_u32(slave, 0x6099, 2)),
        "home_acc(609Ah)": _try(lambda: sdo_u32(slave, 0x609A)),
    }
    params["motion"] = motion

    # ---- IO/限位 ----
    io = {
        "digital_input(60FDh)": _try(lambda: hex(sdo_u32(slave, 0x60FD))),
        "X0_func(2310h)": _term(slave, 1),
        "X1_func(2311h)": _term(slave, 2),
        "X2_func(2312h)": _term(slave, 3),
        "X3_func(2313h)": _term(slave, 4),
    }
    params["io"] = io

    # ---- 打印核对表 ----
    print(f"\n===== {args.name} 轴驱动器参数核对表 (站号 {args.alias}) =====")
    for group, d in (("身份信息", identity), ("运动参数", motion), ("IO/限位", io)):
        print(f"\n-- {group} --")
        for k, v in d.items():
            print(f"  {k:<30} {v}")

    # ---- 判定: 核心对象能读回即可 ----
    core_ok = (identity["device_name(1008h)"] != "未提供"
               and motion["status_word(6041h)"] != "未提供"
               and motion["actual_pos(6064h)_pulses"] != "未提供")
    n_motion = sum(1 for v in motion.values() if v != "未提供")
    detail = (f"身份/状态字/位置已读回; 运动参数读到 {n_motion}/{len(motion)} 项; "
              f"60FDh={io['digital_input(60FDh)']}")
    report("参数读取 (核心对象)", core_ok, detail)

    path = state_path(args)
    state = load_state(path)
    if core_ok:
        out = Path(args.out or PROJECT_ROOT / f"bringup_params_{args.name}_a{args.alias}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[存档] 完整参数 → {out}")
        mark(path, state, KEY, True, detail, params)
        print(f"[OK] {STEP_TITLES[KEY]} 通过 → 已解锁 03 使能练习。")
    return 0 if core_ok else 1


if __name__ == "__main__":
    sys.exit(main())
