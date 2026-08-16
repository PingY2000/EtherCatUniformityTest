"""命令行入口: 双轴滑台扫描 + 功率计采集。

用法:
  # 无硬件 dry-run (模拟轴 + 模拟高斯光斑功率计)
  python examples/run_scan.py --dry-run

  # 真实硬件 (需 pysoem + Npcap)
  python examples/run_scan.py --ifname "\\Device\\NPF_{GUID}" --x-alias 0 --y-alias 1
"""
from __future__ import annotations

import argparse
import os
import sys

# 允许从任意目录运行 (把项目根目录加入 import 路径)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ethercat_scan import (AxisConfig, ScanConfig, SimulatedAxis,
                           SimulatedPowerMeter, Scanner)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EtherCAT 双轴滑台扫描采集")
    # 硬件
    p.add_argument("--dry-run", action="store_true", help="无硬件，用模拟轴+模拟功率计跑通流程")
    p.add_argument("--ifname", default=None, help="EtherCAT 网卡名 (Npcap, 如 \\Device\\NPF_{GUID})")
    # 轴映射
    p.add_argument("--x-alias", type=int, default=0, help="X 轴驱动器站号(拨码)")
    p.add_argument("--y-alias", type=int, default=1, help="Y 轴驱动器站号(拨码)")
    p.add_argument("--x-ppmm", type=float, default=1000.0, help="X 轴脉冲/mm")
    p.add_argument("--y-ppmm", type=float, default=1000.0, help="Y 轴脉冲/mm")
    p.add_argument("--x-dir", type=int, default=1, choices=[1, -1])
    p.add_argument("--y-dir", type=int, default=1, choices=[1, -1])
    # 回零与软限位
    p.add_argument("--home-method", type=int, default=17, choices=[17, 18, 24, 29],
                   help="6098h 回零方式: 17=负限位, 18=正限位, 24/29=原点开关")
    p.add_argument("--home-offset", type=int, default=0, help="607Ch 回零偏移 (pulses)")
    p.add_argument("--x-min", type=float, default=None, help="X 软限位下限 (mm，相对回零原点)")
    p.add_argument("--x-max", type=float, default=None, help="X 软限位上限 (mm)")
    p.add_argument("--y-min", type=float, default=None, help="Y 软限位下限 (mm)")
    p.add_argument("--y-max", type=float, default=None, help="Y 软限位上限 (mm)")
    # 扫描范围 (START STOP STEP)
    p.add_argument("--x-range", nargs=3, type=float, default=[0, 10, 1], metavar=("START", "STOP", "STEP"))
    p.add_argument("--y-range", nargs=3, type=float, default=[0, 10, 1], metavar=("START", "STOP", "STEP"))
    p.add_argument("--dwell", type=float, default=0.1, help="每点停留/稳定时间(s)")
    p.add_argument("--samples", type=int, default=1, help="每点采样次数(取平均)")
    p.add_argument("--no-snake", action="store_true", help="关闭蛇形往返扫描")
    # 回零与输出
    p.add_argument("--home", action="store_true", help="扫描前先回零(需接限位开关)")
    p.add_argument("--out-csv", default="scan_result.csv")
    p.add_argument("--out-png", default="scan_result.png")
    p.add_argument("--no-plot", action="store_true")
    return p


def main():
    args = build_parser().parse_args()

    cfg = ScanConfig(
        x_start=args.x_range[0], x_stop=args.x_range[1], x_step=args.x_range[2],
        y_start=args.y_range[0], y_stop=args.y_range[1], y_step=args.y_range[2],
        dwell=args.dwell, n_samples_per_point=args.samples,
        snake=not args.no_snake,
        output_csv=args.out_csv,
        output_heatmap=None if args.no_plot else args.out_png,
    )

    # 功率计: 先用模拟光斑占位 (中心在扫描区中心)
    cx = (cfg.x_start + cfg.x_stop) / 2
    cy = (cfg.y_start + cfg.y_stop) / 2
    meter = SimulatedPowerMeter(center=(cx, cy))
    meter.open()

    master = None
    if args.dry_run:
        x_axis = SimulatedAxis("X", pulses_per_mm=args.x_ppmm, direction=args.x_dir,
                               soft_limits=(args.x_min, args.x_max))
        y_axis = SimulatedAxis("Y", pulses_per_mm=args.y_ppmm, direction=args.y_dir,
                               soft_limits=(args.y_min, args.y_max))
    else:
        from ethercat_scan.master import EtherCATMaster
        master = EtherCATMaster(args.ifname)
        master.open()
        master.find_drives()
        master.go_op()
        x_axis = master.make_drive(AxisConfig(name="X", alias=args.x_alias,
                                              pulses_per_mm=args.x_ppmm, direction=args.x_dir,
                                              home_method=args.home_method,
                                              home_offset=args.home_offset,
                                              soft_limit_min_mm=args.x_min,
                                              soft_limit_max_mm=args.x_max))
        y_axis = master.make_drive(AxisConfig(name="Y", alias=args.y_alias,
                                              pulses_per_mm=args.y_ppmm, direction=args.y_dir,
                                              home_method=args.home_method,
                                              home_offset=args.home_offset,
                                              soft_limit_min_mm=args.y_min,
                                              soft_limit_max_mm=args.y_max))

    try:
        sc = Scanner(x_axis, y_axis, meter, cfg)
        sc.prepare()
        if args.home:
            sc.home()
        sc.scan()
        sc.save_csv()
        if cfg.output_heatmap:
            sc.save_heatmap()
    finally:
        meter.close()
        if master is not None:
            master.close()


if __name__ == "__main__":
    main()
