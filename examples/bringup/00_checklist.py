#!/usr/bin/env python
"""00 上电前检查清单 (纯人工，不上电不连网)。

首次接入前逐条人工确认，全部 [y] 才写入进度 (PASS)。
它是整条链的"安全闸门 0": 未通过时后续环节拒绝运行。

用法:
  python examples/bringup/00_checklist.py            # 逐条回答
  python examples/bringup/00_checklist.py --yes      # 全部视为确认(仅专家!)
  python examples/bringup/00_checklist.py --dry-run  # 演示流程，不写进度
"""
from __future__ import annotations

import sys

from _common import (build_parser, check_prereqs, confirm, load_state, mark,
                     report, state_path)

KEY = "00"

# (代码, 检查内容) —— 可按你的机型增删
CHECKLIST = [
    ("机械安装", "滑台/丝杠安装牢固、无卡阻；行程两端均有富余空间，当前不在行程极端。"),
    ("接线核对", "按图纸核对: 电机动力线、反馈/编码器线、驱动器供电(24~50V 极性正确)、"
                 "EtherCAT 网线、限位/原点开关线。"),
    ("站号拨码", "本机要接入的驱动器站号拨码已设定并记录 (将用于 --alias)。"),
    ("供电电压", "上电前用万用表确认电源电压在驱动器允许范围且极性正确。"),
    ("急停可用", "硬线急停处于可随时按下的位置且接线有效；确认急停按下可切断动力。"),
    ("人员清场", "行程范围内无人员/手/异物；如有防护罩请关闭。"),
    ("断电路径", "明确主电源开关/断路器位置，知道如何立即断电。"),
]


def main() -> int:
    args = build_parser("00 上电前检查清单 (安全闸门 0)").parse_args()
    if not check_prereqs(args, KEY, requires=[]):
        return 1
    if args.dry_run:
        for code, question in CHECKLIST:
            report(f"[{code}]", True, "(dry-run)")
        report("上电前检查清单", True, "(dry-run) 不写进度")
        return 0
    print("以下为上电前必须逐条确认的检查项。全部回答 [y] 才允许进入 01 (上电/连网)。")
    print("任一项无法满足，请先处理；完成后重新运行本脚本。\n")

    results = {}
    all_ok = True
    for code, question in CHECKLIST:
        ok = confirm(f"  [{code}] {question}", args)
        results[code] = ok
        if not ok:
            all_ok = False

    if not all_ok:
        report("上电前检查清单", False, "存在未确认项，禁止上电，请处理后再运行")
        return 1

    if args.dry_run:
        report("上电前检查清单", True, "(dry-run) 不写进度")
        return 0

    path = state_path(args)
    state = load_state(path)
    mark(path, state, KEY, True, "全部人工确认通过", {"items": results})
    print("\n[OK] 检查清单全部通过 → 已解锁 01 总线枚举。可以上电/连网了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
