# 设备导入/首次上电 分步验证链 (bringup)

首次把 **驱动器 + 滑台** 接入 EtherCAT 时的**安全、分步**装机验证。
把"上电前 → 只读核实 → 通电不运动 → 第一次运动 → 限位/原点 → 软限位"拆成
**8 个独立编号脚本**（00~07），每个脚本做完把 PASS/FAIL + 关键数据写进
共享进度文件 `bringup_state.json`；后面的脚本会**校验前置环节已 PASS**，
否则拒绝运行（专家可用 `--ignore-order` 强制跳过）。

```
00_checklist.py        # 上电前检查清单 (纯人工, 安全闸门 0, 不连网)
01_scan_bus.py         # 总线枚举/从站识别   (只读)
02_read_params.py      # 参数读取·核对·存档  (只读)
03_state_machine.py    # 使能·状态机练习     (通电, 不产生定位运动)
04_jog.py              # 低速点动试转         (第一次真实运动)
05_limits.py           # 限位/原点开关触发确认 (人手触发, 无自动运动)
06_home.py             # 回零与原点标定       (首次自动回零)
07_soft_limits.py      # 行程标定与软限位建议  (链收尾)
```

## 用法 (从项目根目录运行)

```bash
# 00: 上电前人工检查 (全部答 y 才解锁 01)
python examples/bringup/00_checklist.py

# 之后每步一条，顺序执行 (省略即从当前步往后)
python examples/bringup/01_scan_bus.py   --ifname "\\Device\\NPF_{GUID}"
python examples/bringup/02_read_params.py --ifname "\\Device\\NPF_{GUID}" --alias 0
python examples/bringup/03_state_machine.py --ifname "\\Device\\NPF_{GUID}" --alias 0
python examples/bringup/04_jog.py         --ifname "\\Device\\NPF_{GUID}" --alias 0 --steps-mm 0.2 0.5 1
python examples/bringup/05_limits.py      --ifname "\\Device\\NPF_{GUID}" --alias 0 --switches neg pos home
python examples/bringup/06_home.py        --ifname "\\Device\\NPF_{GUID}" --alias 0 --home-method 24
python examples/bringup/07_soft_limits.py --ifname "\\Device\\NPF_{GUID}" --alias 0 --margin-mm 2.0
```

所有运动环节默认 `--slow-vel 2000` pulses/s；每步都可用 `-h` 看参数。
共享进度文件默认 `./bringup_state.json`，可用 `--state <路径>` 换位置
(例如换轴、换机台时各存一份)。

## 三个验证目标 ↔ 环节对照

| 验证目标 | 环节 | 判定依据 |
|---|---|---|
| 控制器通信 | 01 + 02 | 从站被枚举出、是 YKD2205PE (0x0994/0x2000)、站号对上；身份+状态字+位置能 SDO 读回 |
| 滑台控制 | 03 + 04 | CiA402 使能往返正常、无意外位移；低速点动递增幅度到位且实际位置反馈正确 |
| 限位和原点 | 05 + 06 (+07) | 各开关 0→1→0 触发正确；按 6098h 回零成功、原点≈0；07 爬两端得行程并给软限位建议 |

## 安全原则 (读一遍)

1. **顺序不可跳**：04 之前必须 03、06 之前必须 04、07 之前必须 05+06 ——
   进度文件强制，是为了"先证明会动、再让它去撞开关"。
2. **运动前有人工闸门**：03/04/06/07 会打印确认问题，回车 y 才继续；
   `--yes` 仅适合老手。
3. 每个运动脚本开始前：**确认行程无障碍、急停在手、人员清场**。
4. 首次建议 04 从 `--steps-mm 0.2 0.5 1` 起步；跑 06/07 前先想清楚
   方向对不对、`--home-method` 是否和接线一致 (17=负限位 18=正限位 24/29=原点)。
5. 07 沿**整个行程**爬行，务必已通过 05 确认开关接线再跑。
6. 任一环节 FAIL：先修再重跑该环节；进度里 FAIL 记录会阻止后续环节。

## 常见卡点

- **01 发现不了从站**：网卡名 `--ifname` 用 Wireshark 里的 `\Device\NPF_{...}`；
  查网线/供电/驱动是否上电。
- **01 报了站号不存在**：核对拨码，把 `--alias` 改成实际站号。
- **03 使能后报 fault**：`enable()` 会自动发一次 fault reset，若仍故障，
  查 24~50V 供电/动力线/急停是否被按下。
- **04 一动方向反了 / 位置不对**：用 `--dir -1` 翻转，或核对电子齿轮(2408h/2409h)
  与脉冲/mm 标定 (见项目 README「关键参数标定」)。
- **05 某开关触发不到**：可能没接/没配置端子功能 (2310h~2313h)；
  可先 `--switches` 只验接了的，剩下的在 06/07 中由运动触发后回来补跑。

## 进度文件

`bringup_state.json` 记录每步 `{ok, detail, data, at}`，07 结束会打印整条链汇总。
要重来/换轴，删掉或换 `--state` 即可；`02` 还会单独存档
`bringup_params_<轴>_a<站号>.json`、`07` 存 `bringup_softlimits_<轴>.json`。

链跑完后，可用 **examples/run_verify.py** 一键复验 (通信→滑台→限位原点)，
或直接进 examples/run_scan.py 做正式扫描。
