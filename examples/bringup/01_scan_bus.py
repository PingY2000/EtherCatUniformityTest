#!/usr/bin/env python
"""01 总线枚举 / 从站识别 (只读，无运动)。

前提: 00 已通过 (已人工确认，可上电/连网)。
内容: 打开网卡 → config_init 枚举从站 → 逐个打印 索引/站号/厂商/产品/名称，
并识别 YKD2205PE (vendor 0x0994, product 0x2000)。用于确认:
  - 网卡/网线/供电正常 (能发现从站)
  - 从站就是 YKD 驱动器 (产品码对上)
  - 站号拨码与预期一致

用法:
  python examples/bringup/01_scan_bus.py --ifname "\\Device\\NPF_{GUID}"
"""
from __future__ import annotations

import sys

from _common import (STEP_TITLES, build_parser, check_prereqs, load_state,
                     mark, report, state_path)
from ethercat_scan.master import EtherCATMaster, YKD_PRODUCT_CODE, YKD_VENDOR_ID

KEY = "01"


def main() -> int:
    args = build_parser("01 总线枚举 / 从站识别").parse_args()
    if not check_prereqs(args, KEY, requires=["00"]):
        return 1

    if args.dry_run:
        report("从站发现", True, "(dry-run) 演示: 总线[0] 站号=0 YKD2205PE")
        report("识别 YKD 驱动器", True, "(dry-run) 不写进度")
        return 0

    try:
        master = EtherCATMaster(args.ifname)
        n = master.open()          # open + config_init
    except Exception as e:
        report("打开网卡/枚举从站", False, str(e))
        return 1

    slaves = master.master.slaves
    print(f"\n总线上共 {n} 个从站:")
    found_ykd = 0
    for i, s in enumerate(slaves):
        alias = master._slave_alias(s)
        is_ykd = (getattr(s, "man", None) == YKD_VENDOR_ID
                  and getattr(s, "id", None) == YKD_PRODUCT_CODE)
        if is_ykd:
            found_ykd += 1
        tag = "  <-- YKD2205PE" if is_ykd else ""
        print(f"  从站[{i}] 站号={alias} vendor=0x{getattr(s, 'man', 0):X} "
              f"product=0x{getattr(s, 'id', 0):X} rev=0x{getattr(s, 'rev', 0):X} "
              f"name={getattr(s, 'name', '')}{tag}")

    try:
        master.close()
    except Exception:
        pass

    ok_slaves = n > 0
    ok_ykd = found_ykd > 0
    detail = f"{n} 个从站, YKD×{found_ykd}"
    if not ok_ykd:
        detail += "  <-- 未发现 YKD2205PE，检查接线/供电/是否混入其它从站!"
    if not ok_slaves:
        detail = "总线无从站，检查网卡/网线/供电"

    all_ok = ok_slaves and ok_ykd
    report("从站发现/识别", all_ok, detail)

    # 目标站号拨码是否在总线上 (与本脚本要接入的轴对应)
    alias_ok = any(master._slave_alias(s) == args.alias for s in slaves)
    if alias_ok:
        report("目标站号 --alias", True, f"站号 {args.alias} 已在总线上")
    else:
        report("目标站号 --alias", False,
               f"站号 {args.alias} 未在总线上找到，请核对拨码或用 --alias 指定实际站号")
        all_ok = False

    path = state_path(args)
    state = load_state(path)
    if all_ok:
        mark(path, state, KEY, True, detail,
             {"slaves": n, "ykd": found_ykd, "alias": args.alias})
        print(f"\n[OK] {STEP_TITLES[KEY]} 通过 → 已解锁 02 参数读取。")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
