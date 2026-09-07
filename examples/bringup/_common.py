"""装机导入链 共享库。

八个独立编号脚本 00~07 组成一条"设备导入/首次上电"验证链，每个脚本：
  1. 校验前置环节已在共享进度文件 (bringup_state.json) 中 PASS，否则拒绝运行；
  2. 做完自己的检查后把 PASS/FAIL + 关键数据写回进度文件，供下一环节引用。

目录 (examples/bringup/):
  00 上电前检查清单        (纯人工，不上电不连网)
  01 总线枚举 / 从站识别    (只读: 发现从站、识别 YKD、核对站号)
  02 参数读取·核对·存档     (只读: 读身份+运动+限位参数并存 JSON)
  03 使能·状态机练习        (通电，不产生定位运动)
  04 低速小距点动试转        (第一次真实运动: 慢速递增往返)
  05 限位/原点开关触发确认   (人手触发开关，程序读 60FDh 确认接线)
  06 回零与原点标定          (按 6098h 方式回零，确认原点≈0)
  07 软限位建议与扫描参数档   (依据实测行程给出软限位建议并落盘)

用法: 从项目根目录运行，例如
  python examples/bringup/00_checklist.py
  python examples/bringup/01_scan_bus.py --ifname "\\Device\\NPF_{GUID}"
每个脚本都用 -h 查看参数；--dry-run 只演示流程不写进度；--yes 跳过人工确认(专家)。
"""
from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

# ---- 把项目根目录加入 import 路径 (本文件位于 <root>/examples/bringup/) ----
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---- Windows 下统一 UTF-8 输出 ----
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_STATE = PROJECT_ROOT / "bringup_state.json"

# 进度文件里步骤与说明 (展示用)
STEP_TITLES = {
    "00": "00 上电前检查清单",
    "01": "01 总线枚举 / 从站识别",
    "02": "02 参数读取·核对·存档",
    "03": "03 使能·状态机练习",
    "04": "04 低速点动试转",
    "05": "05 限位/原点开关触发确认",
    "06": "06 回零与原点标定",
    "07": "07 软限位建议",
}


# ================= 打印 =================
def banner(title: str):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def flag(ok):
    return "PASS" if ok is True else ("FAIL" if ok is False else "NA  ")


def report(title: str, ok, detail: str = "") -> bool:
    print(f"[{flag(ok)}] {title}" + (f"  --  {detail}" if detail else ""))
    return ok is True


# ================= 进度文件 =================
def state_path(args) -> Path:
    return Path(getattr(args, "state", None) or DEFAULT_STATE)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"steps": {}}


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def step_passed(state: dict, key: str) -> bool:
    st = state.get("steps", {}).get(key)
    return bool(st and st.get("ok") is True)


def mark(path: Path, state: dict, key: str, ok: bool, detail: str = "", data=None):
    state.setdefault("steps", {})[key] = {
        "ok": bool(ok),
        "detail": detail,
        "data": data or {},
        "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    save_state(path, state)


def missing_prereqs(state: dict, keys, args) -> list:
    """返回未通过的前置步骤 key；--ignore-order 时仅告警并返回空。"""
    miss = [k for k in keys if not step_passed(state, k)]
    if miss and getattr(args, "ignore_order", False):
        print(f"[warn] --ignore-order: 跳过前置校验 {miss}，请自行确认安全!")
        return []
    return miss


def check_prereqs(args, key: str, requires) -> bool:
    """打印当前环节并校验前置；不满足返回 False (脚本据此退出)。"""
    banner(f"第 {key} 环: {STEP_TITLES.get(key, key)}")
    state = load_state(state_path(args))
    miss = missing_prereqs(state, requires, args)
    if miss:
        for k in miss:
            print(f"[FAIL] 前置环节 {STEP_TITLES.get(k, k)} 未通过，请先运行 examples/bringup/{k}_*.py")
        print("      (确认已手动完成时可用 --ignore-order 强制继续)")
        return False
    return True


# ================= 人工确认 / SDO 小工具 =================
def confirm(question: str, args) -> bool:
    """人工安全闸门。--yes 时自动通过。"""
    if getattr(args, "yes", False):
        print(f"[confirm-自动] {question}")
        return True
    try:
        ans = input(f"{question} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def sdo_u32(slave, idx: int, sub: int = 0) -> int:
    data = slave.sdo_read(idx, sub)
    return struct.unpack("<I", data[:4])[0]


def sdo_i32(slave, idx: int, sub: int = 0) -> int:
    data = slave.sdo_read(idx, sub)
    return struct.unpack("<i", data[:4])[0]


def sdo_u16(slave, idx: int, sub: int = 0) -> int:
    data = slave.sdo_read(idx, sub)
    return struct.unpack("<H", data[:2])[0]


def sdo_str(slave, idx: int, sub: int = 0) -> str:
    data = slave.sdo_read(idx, sub) or b""
    return data.split(b"\0")[0].decode("ascii", "replace")


# ================= 硬件/模拟 连接 =================
def build_parser(desc: str):
    """创建解析器并附加所有环节共享的参数。"""
    import argparse
    p = argparse.ArgumentParser(description=desc, formatter_class=argparse.RawTextHelpFormatter)
    # 进度/模式
    p.add_argument("--state", default=None,
                   help=f"进度文件路径 (默认 {DEFAULT_STATE})")
    p.add_argument("--dry-run", action="store_true", help="无硬件演示流程，不写进度")
    p.add_argument("--ignore-order", action="store_true", help="忽略前置环节校验(专家)")
    p.add_argument("--yes", action="store_true", help="跳过人工安全确认(专家)")
    # EtherCAT 网卡
    p.add_argument("--ifname", default=None,
                   help="EtherCAT 网卡名 (Npcap, 如 \\Device\\NPF_{GUID})")
    # 轴参数 (单轴: X。扩双轴时加一组 y- 前缀参数即可)
    p.add_argument("--name", default="X", help="轴名 (仅用于显示)")
    p.add_argument("--alias", type=int, default=0, help="驱动器站号(拨码, 0~63)")
    p.add_argument("--ppmm", type=float, default=1000.0, help="脉冲/mm (标定值)")
    p.add_argument("--dir", type=int, default=1, choices=[1, -1], help="方向 ±1")
    p.add_argument("--home-method", type=int, default=17, choices=[17, 18, 24, 29],
                   help="6098h 回零方式: 17=负限位 18=正限位 24/29=原点开关")
    p.add_argument("--home-offset", type=int, default=0, help="607Ch 回零偏移 (pulses)")
    p.add_argument("--soft-min", type=float, default=None, help="软限位下限 mm (相对原点)")
    p.add_argument("--soft-max", type=float, default=None, help="软限位上限 mm (相对原点)")
    p.add_argument("--slow-vel", type=int, default=2000, help="低速 (pulses/s)")
    p.add_argument("--timeout", type=float, default=10.0, help="单次到位/回零超时(s)")
    return p


def make_sim_axis(args):
    from ethercat_scan import SimulatedAxis
    return SimulatedAxis(args.name, pulses_per_mm=args.ppmm, direction=args.dir,
                         soft_limits=(args.soft_min, args.soft_max))


def open_master(args):
    """打开 EtherCAT 主站并进入运行态。返回 (master, error)。dry-run 返回 (None, None)。"""
    if args.dry_run:
        return None, None
    if not args.ifname:
        return None, "缺少 --ifname (网卡名)。演示流程请加 --dry-run"
    try:
        from ethercat_scan.master import EtherCATMaster
        master = EtherCATMaster(args.ifname)
        n = master.open()
        master.find_drives()
        master.op_state = master.go_op()
        print(f"[init] 网卡就绪, {n} 从站, 运行态={master.op_state}")
        return master, None
    except Exception as e:
        return None, str(e)


def make_axis(args, master=None):
    """构建目标轴。dry-run 给模拟轴；否则从 master 定位 YKD 驱动器。"""
    if args.dry_run:
        return make_sim_axis(args)
    from ethercat_scan import AxisConfig
    return master.make_drive(AxisConfig(
        name=args.name, alias=args.alias, pulses_per_mm=args.ppmm, direction=args.dir,
        home_method=args.home_method, home_offset=args.home_offset,
        soft_limit_min_mm=args.soft_min, soft_limit_max_mm=args.soft_max))


def close(master, axis=None):
    """安全收尾: 去使能 + 关主站。"""
    if axis is not None and hasattr(axis, "disable") and not axis.__class__.__module__.startswith("ethercat_scan.motion"):
        try:
            axis.disable()
            print("[done] 轴已去使能")
        except Exception as e:
            print(f"[warn] 去使能失败: {e}")
    if master is not None:
        try:
            master.close()
        except Exception:
            pass


def axis_pos_mm(axis) -> float:
    """读实际位置换算 mm (与 GUI/扫描同一参考)。"""
    return axis.read_actual_position() / (axis.pulses_per_mm * axis.direction)
