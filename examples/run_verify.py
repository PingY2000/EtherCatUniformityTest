"""装机分步验证命令行: 控制器通信 → 滑台控制 → 限位与原点。

按顺序做三部分逐步验证，每部分输出 PASS/FAIL 汇总，便于装机调试留档:

  第 1 步  控制器通信    EtherCAT 网卡/从站发现、驱动器识别、进入运行态、
                        SDO 读 + 读写回环 (证明主站↔驱动器双向通信)
  第 2 步  滑台控制      使能 (CiA 402) + PP 模式，慢速点动前进/回程，
                        读实际位置确认"确实动了且位移正确"
  第 3 步  限位和原点    读限位/原点开关状态 (60FDh)，做自检
                        (找负限位 → 找正限位 → 回零)，报告限位触发位置

当前按"单轴"实现 (默认 X)，轴参数统一为 alias/ppmm/dir 一组；
后续扩双轴时把 AxisConfig 列表化即可 (见 main 里 build_axes 的注释)。

用法示例:
  # 三步全跑 (真实硬件, 需 pysoem + Npcap)
  python examples/run_verify.py --ifname "\\Device\\NPF_{GUID}" --alias 0

  # 只跑第 1 步控制器通信
  python examples/run_verify.py --ifname "\\Device\\NPF_{GUID}" --alias 0 --only 1

  # 只跑第 2 步滑台控制 (点动 3mm)
  python examples/run_verify.py --ifname ... --alias 0 --only 2 --jog-mm 3

  # 无硬件跑通流程 (第1步 NA、第2步 PASS、第3步 NA，仅验证脚本逻辑)
  python examples/run_verify.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from typing import List, Optional

# 允许从任意目录运行 (把项目根目录加入 import 路径)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 下统一 UTF-8 输出，避免中文在 cmd/重定向时乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ethercat_scan import AxisConfig, SimulatedAxis


class Check:
    """一条验证结果。ok: True=PASS, False=FAIL, None=NA/跳过。"""

    __slots__ = ("name", "ok", "detail")

    def __init__(self, name: str, ok: Optional[bool], detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail


def _flag(ok: Optional[bool]) -> str:
    return {True: "PASS", False: "FAIL", None: "NA  "}[ok]


def _print_checks(title: str, checks: List[Check]) -> bool:
    """打印一阶段检查列表，返回该阶段是否全部通过 (NA 不计)。"""
    print(f"\n===== {title} =====")
    passed = True
    for c in checks:
        print(f"[{_flag(c.ok)}] {c.name}" + (f"  --  {c.detail}" if c.detail else ""))
        if c.ok is False:
            passed = False
    print(f"----- 汇总: {_flag(passed)} ({title})")
    return passed


# ---------- SDO 读写回环小工具 (6081h: PP 速度, U32, 读写无副作用) ----------
_SDO_6081 = 0x6081


def _sdo_read_u32(slave, idx: int) -> int:
    data = slave.sdo_read(idx, 0x00)
    return struct.unpack("<I", data[:4])[0]


def _sdo_write_u32(slave, idx: int, value: int) -> None:
    slave.sdo_write(idx, 0x00, struct.pack("<I", value & 0xFFFFFFFF))


# ---------- 第 1 步: 控制器通信 ----------
def stage1_comm(master, axis, dry_run: bool, setup_fail: Optional[str],
                show_slaves: bool = True) -> List[Check]:
    if dry_run:
        return [Check("控制器通信 (EtherCAT)", None,
                      "dry-run 无网卡，本步跳过 (真实硬件才验证)")]
    if setup_fail:
        return [Check("控制器通信 (EtherCAT)", False, f"初始化失败: {setup_fail}")]

    checks: List[Check] = []
    slaves = master.master.slaves
    n = len(slaves)

    # 1.1 从站发现
    checks.append(Check("从站发现 (config_init)", n > 0, f"总线上共 {n} 个从站"))
    if n == 0:
        return checks

    # 1.2 驱动器识别
    drives = master.find_drives()
    names = ", ".join(f"站号={master._slave_alias(s)}" for s in drives) or "无"
    checks.append(Check("识别 YKD2205PE 驱动器", len(drives) > 0,
                        f"vendor=0x{0x0994:x} product=0x{0x2000:x}，发现 {len(drives)} 台 [{names}]"))
    if not drives:
        return checks

    # 1.3 主站运行状态 (go_op 在初始化时已执行)
    st = getattr(master, "op_state", "?")
    checks.append(Check("主站进入运行状态", True, f"当前 {st} (SDO 控制可用)"))

    # 1.4 目标轴 SDO 读 (状态字/实际位置)
    try:
        sw = axis.status
        pos = axis.read_actual_position()
        checks.append(Check("SDO 读 (状态字/实际位置)", True,
                            f"轴 {axis.name} status=0x{sw:04X} pos={pos} pulses"))
    except Exception as e:
        checks.append(Check("SDO 读 (状态字/实际位置)", False, f"异常: {e}"))

    # 1.5 SDO 读写回环 (6081h 写→读回→恢复)
    try:
        orig = _sdo_read_u32(axis.slave, _SDO_6081)
        trial = orig + 1 if orig < 0xFFFFFFFF else orig - 1
        try:
            _sdo_write_u32(axis.slave, _SDO_6081, trial)
            got = _sdo_read_u32(axis.slave, _SDO_6081)
            checks.append(Check("SDO 读写回环 (6081h)", got == trial,
                                f"写 {trial} → 读回 {got}"))
        finally:
            _sdo_write_u32(axis.slave, _SDO_6081, orig)
    except Exception as e:
        checks.append(Check("SDO 读写回环 (6081h)", False, f"异常: {e}"))

    if show_slaves:
        for i, s in enumerate(slaves):
            print(f"  从站[{i}] 站号={master._slave_alias(s)} "
                  f"vendor=0x{getattr(s, 'man', 0):x} product=0x{getattr(s, 'id', 0):x} "
                  f"name={getattr(s, 'name', '')}")
    return checks


# ---------- 第 2 步: 滑台控制 ----------
def stage2_motion(axis, args, dry_run: bool, setup_fail: Optional[str]) -> List[Check]:
    if dry_run:
        # 无硬件时用模拟轴验证流程 (使能/移动/回位逻辑)
        axis = SimulatedAxis(args.name, pulses_per_mm=args.ppmm, direction=args.dir,
                             soft_limits=(args.soft_min, args.soft_max))
    if axis is None:
        return [Check("滑台控制", False, f"初始化失败: {setup_fail}")]

    checks: List[Check] = []
    jog_mm = float(args.jog_mm)
    ppmm = args.ppmm * args.dir          # 脉冲/mm (含方向)
    tol_pul = max(5, abs(round(jog_mm * args.ppmm)) // 100 + 1)

    # 2.1 使能 + PP 模式 (低速)
    try:
        if hasattr(axis, "setup_pp"):
            axis.setup_pp()
        if hasattr(axis, "configure_profile"):
            axis.configure_profile(velocity=int(args.slow_vel))
        axis.enable()
        enabled = (not hasattr(axis, "is_enabled")) or axis.is_enabled
        checks.append(Check("使能 (CiA 402) + PP 低速模式", bool(enabled),
                            f"profile 速度 {args.slow_vel} pulses/s"))
    except Exception as e:
        checks.append(Check("使能 (CiA 402) + PP 低速模式", False, f"异常: {e}"))
        return checks

    # 2.2 出发前安全: 若轴上已压住限位开关则拒绝动作
    try:
        st = axis.read_limit_states()
        if st is not None and (st.get("neg") or st.get("pos")):
            checks.append(Check("点动方向安全 (未压限位)", False,
                                "轴当前停在限位开关上，请先手动移开或回零再验证"))
            return checks
    except Exception as e:
        checks.append(Check("点动方向安全 (未压限位)", False, f"读取限位失败: {e}"))
        return checks

    # 2.3 慢速点动前进 jog_mm → 读实际位置 → 回程到起点
    try:
        start_pul = axis.read_actual_position()
        delta_pul = round(jog_mm * ppmm)
        fwd_pul = start_pul + delta_pul

        axis.move_abs(fwd_pul)
        axis.wait_target_reached(args.timeout)
        mid_pul = axis.read_actual_position()

        axis.move_abs(start_pul)
        axis.wait_target_reached(args.timeout)
        end_pul = axis.read_actual_position()

        moved_mm = (mid_pul - start_pul) / (ppmm or 1)
        fwd_ok = abs(mid_pul - fwd_pul) <= tol_pul and abs(moved_mm - jog_mm) <= max(0.2, 0.1 * jog_mm)
        back_ok = abs(end_pul - start_pul) <= tol_pul

        checks.append(Check(
            f"点动 +{jog_mm:g}mm 并回程", fwd_ok and back_ok,
            f"起点 {start_pul} → {mid_pul} (实测 {moved_mm:+.2f}mm) → 回 {end_pul} pulses"))
    except Exception as e:
        checks.append(Check(f"点动 +{jog_mm:g}mm 并回程", False, f"异常: {e}"))
    return checks


# ---------- 第 3 步: 限位和原点功能 ----------
def stage3_limits(axis, args, dry_run: bool, setup_fail: Optional[str]) -> List[Check]:
    if dry_run:
        return [Check("限位和原点功能", None,
                      "dry-run 无硬件开关，本步跳过 (真实硬件才验证)")]
    if axis is None:
        return [Check("限位和原点功能", False, f"初始化失败: {setup_fail}")]

    from ethercat_scan.selftest import can_selftest, run_axis_selftest

    checks: List[Check] = []
    if not can_selftest(axis):
        return [Check("限位和原点功能", False,
                      "该轴无 move_rel/read_limit_states (模拟轴?)，无法自检")]

    # 3.1 读限位/原点开关状态 (60FDh)
    try:
        st = axis.read_limit_states()
        txt = "  ".join(f"{k}={'●触发' if v else '○'}" for k, v in st.items())
        checks.append(Check("限位/原点开关读取 (60FDh)", True, txt))
    except Exception as e:
        checks.append(Check("限位/原点开关读取 (60FDh)", False, f"异常: {e}"))

    # 3.2 自检: 找负限位(左) → 找正限位(右) → 回零
    try:
        res = run_axis_selftest(axis, step_mm=args.step_mm, max_mm=args.max_mm,
                                timeout=args.timeout,
                                slow_velocity=int(args.slow_vel))
        detail = res.detail
        if res.ok and res.neg_pos_mm is not None and res.pos_pos_mm is not None:
            detail += f" | 左限位@{res.neg_pos_mm:+.1f}mm 右限位@{res.pos_pos_mm:+.1f}mm " \
                      f"行程≈{res.span_mm:.1f}mm"
        checks.append(Check("自检 (负限位→正限位→回零)", res.ok, detail))
    except Exception as e:
        checks.append(Check("自检 (负限位→正限位→回零)", False, f"异常: {e}"))
    return checks


# ---------- 参数与主流程 ----------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="装机分步验证: 1控制器通信 2滑台控制 3限位和原点")
    # 运行方式
    p.add_argument("--dry-run", action="store_true",
                   help="无硬件用模拟轴验证脚本流程 (第1/3步 NA)")
    p.add_argument("--ifname", default=None,
                   help="EtherCAT 网卡名 (Npcap, 如 \\Device\\NPF_{GUID})")
    p.add_argument("--only", nargs="+", type=int, choices=[1, 2, 3],
                   default=[1, 2, 3], help="只运行指定步骤，如 --only 1 或 --only 2 3")
    # 轴 (单轴: X。扩双轴时在此加一组 y- 参数)
    p.add_argument("--name", default="X", help="轴名 (仅用于显示)")
    p.add_argument("--alias", type=int, default=0, help="驱动器站号(拨码, 0~63)")
    p.add_argument("--ppmm", type=float, default=1000.0, help="脉冲/mm (标定值)")
    p.add_argument("--dir", type=int, default=1, choices=[1, -1], help="方向 ±1")
    p.add_argument("--home-method", type=int, default=17, choices=[17, 18, 24, 29],
                   help="6098h 回零方式 (见 docs)")
    p.add_argument("--home-offset", type=int, default=0, help="607Ch 回零偏移 (pulses)")
    p.add_argument("--soft-min", type=float, default=None,
                   help="软限位下限 mm (相对回零原点, 可选)")
    p.add_argument("--soft-max", type=float, default=None,
                   help="软限位上限 mm (相对回零原点, 可选)")
    # 运动/自检参数
    p.add_argument("--jog-mm", type=float, default=2.0,
                   help="第2步点动距离 (mm, 前进再回程)")
    p.add_argument("--slow-vel", type=int, default=2000,
                   help="第2/3步低速 (pulses/s)")
    p.add_argument("--step-mm", type=float, default=1.0,
                   help="第3步自检找限位的步长 (mm)")
    p.add_argument("--max-mm", type=float, default=500.0,
                   help="第3步自检单方向最大搜索行程 (mm)")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="单次移动/回零到位超时 (s)")
    return p


def main() -> int:
    args = build_parser().parse_args()

    # 硬件初始化: 打开网卡 → 进入运行态 → 定位轴。
    # 失败时不崩溃，记入 setup_fail，各阶段输出 FAIL 说明原因。
    master = None
    axis = None
    setup_fail = None
    if not args.dry_run:
        try:
            if not args.ifname:
                raise RuntimeError("缺少 --ifname (网卡名)。dry-run 请加 --dry-run")
            from ethercat_scan.master import EtherCATMaster
            master = EtherCATMaster(args.ifname)
            n = master.open()
            master.find_drives()
            master.op_state = master.go_op()
            axis = master.make_drive(AxisConfig(
                name=args.name, alias=args.alias,
                pulses_per_mm=args.ppmm, direction=args.dir,
                home_method=args.home_method, home_offset=args.home_offset,
                soft_limit_min_mm=args.soft_min, soft_limit_max_mm=args.soft_max))
            print(f"[init] 网卡就绪, {n} 从站, 目标轴 {args.name} (站号={args.alias})")
        except Exception as e:  # 任一步失败 → 后续阶段统一报 FAIL
            master = None
            axis = None
            setup_fail = str(e)
            print(f"[init] 初始化失败: {setup_fail}")

    try:
        stages = {
            1: lambda: stage1_comm(master, axis, args.dry_run, setup_fail),
            2: lambda: stage2_motion(axis, args, args.dry_run, setup_fail),
            3: lambda: stage3_limits(axis, args, args.dry_run, setup_fail),
        }
        titles = {1: "第1步 控制器通信", 2: "第2步 滑台控制", 3: "第3步 限位和原点"}

        all_ok = True
        stage_ok = {}
        for s in sorted(set(args.only)):
            ok = _print_checks(titles[s], stages[s]())
            stage_ok[s] = ok
            all_ok &= ok

        # 最终汇总
        print("\n============== 分步验证汇总 ==============")
        for s in sorted(set(args.only)):
            print(f"  [{_flag(stage_ok[s])}] {titles[s]}")
        print(f"  总体: {_flag(all_ok)}")
        return 0 if all_ok else 1
    finally:
        # 结束后断电 (安全) 并关闭主站
        if axis is not None and hasattr(axis, "disable"):
            try:
                axis.disable()
            except Exception:
                pass
        if master is not None:
            try:
                master.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
