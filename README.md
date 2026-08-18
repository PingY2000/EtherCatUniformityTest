# EtherCAT 双轴滑台扫描采集框架

通过 EtherCAT 总线控制两台 **研控 YKD2205PE** 驱动器，驱动双轴滑台做二维扫描，
在每点停留并采集**功率计**读数，输出 CSV 数据与热力图。

- 语言: Python (pysoem，底层 SOEM)
- 运动: CiA 402 **Profile Position (PP)** 逐点停测 (step & measure)
- 功率计: 抽象接口 + 模拟占位实现 (设备尚未确定)

## 目录结构

```
SOEM/
├── YKD2205PE.pdf            # 驱动器手册
├── requirements.txt
├── README.md
├── docs/
│   └── ykd2205pe_ci402.md   # 对象字典/控制字速查
├── ethercat_scan/           # 框架包
│   ├── config.py            #   轴/扫描配置 (dataclass)
│   ├── motion.py            #   轴抽象接口 + 模拟轴
│   ├── drive.py             #   YKD2205PE 封装 (CiA 402 PP)
│   ├── master.py            #   EtherCAT 主站封装 (pysoem)
│   ├── power_meter.py       #   功率计接口 + 模拟/SCPI/串口
│   ├── scanner.py           #   逐点停测扫描主循环
│   ├── gui.py               #   Tkinter 图形界面 (零依赖)
│   ├── gui_pyside6.py       #   PySide6 图形界面 (需 pip install PySide6)
│   └── ui/                  #   Qt Designer 布局文件
│       ├── main_window.ui           #   界面布局 (Designer 可视化编辑)
│       └── main_window_ui.py        #   pyside6-uic 自动生成，勿手改
└── examples/
    ├── run_scan.py          # 命令行入口
    ├── run_gui.py           # Tkinter 图形界面入口
    └── run_gui_pyside6.py   # PySide6 图形界面入口
```

## 安装

```bash
pip install -r requirements.txt
```

Windows 下 pysoem 依赖 **Npcap** 抓包驱动:
1. 到 https://npcap.com 下载安装 Npcap (选 "WinPcap API-compatible Mode")。
2. 若 pip 装 pysoem 失败 (无预编译 wheel)，建议用 Python 3.10~3.12 环境。

功率计接入时再按需安装 (见下)。

## 快速开始

### 1) dry-run (无硬件跑通流程)

```bash
python examples/run_scan.py --dry-run --x-range 0 10 1 --y-range 0 10 1
```

用模拟轴 + 模拟高斯光斑功率计，验证整个扫描→采集→导出链路，生成
`scan_result.csv` 和 `scan_result.png`。

### 2) 真实硬件

```bash
python examples/run_scan.py \
  --ifname "\\Device\\NPF_{GUID}" \
  --x-alias 0 --y-alias 1 \
  --x-ppmm 1000 --y-ppmm 1000 \
  --x-range 0 10 0.5 --y-range 0 10 0.5 --dwell 0.1
```

- `--ifname`: EtherCAT 网卡名。用 Wireshark → 捕获 → 选项 里看到的
  `\Device\NPF_{...}`，或 Npcap 网卡名。
- `--x-alias` / `--y-alias`: 两台驱动器的**站号拨码** (0~63)。务必把两轴拨成
  不同站号，例如 X=0、Y=1。
- `--x-ppmm` / `--y-ppmm`: 每毫米脉冲数 (标定值，见下)。

## 图形界面

提供两套桌面界面，功能一致，二选一：

### Tkinter 版 (默认，零额外依赖)

```bash
python examples/run_gui.py
```

### PySide6 版 (Qt，需先安装)

```bash
pip install "PySide6==6.8.*"   # 见下方版本说明
python examples/run_gui_pyside6.py
```

> **为什么固定 6.8.x**：PySide6 6.9+ 的 `Qt6Core.dll` 会依赖 `icuuc.dll`，而它要求
> **不带版本号** 的导出符号 (`ucnv_open`)；Windows 自带的系统 ICU 和 Anaconda 带的
> ICU (75/78 等) 导出的都是带版本号的符号 (`ucnv_open_78`)，二者对不上，启动时会报
> `ImportError: DLL load failed while importing QtCore: 找不到指定的程序`。
> 6.8.x 的 QtCore 不依赖 ICU，可直接运行。

两套界面共用同一份配置文件 `~/.ethercat_scan_config.json`，设置互通。

界面功能（热力图预览需 numpy+matplotlib，缺失时自动降级为纯日志）：

- 面板填扫描范围/步长/停留时间，勾选「模拟运行」即可无硬件试跑
- 「连接 → 回零/开始扫描 → 停止」，实时显示当前坐标、功率、进度条与热力图
- 扫描在后台线程运行，界面不卡顿；完成后「保存CSV / 保存热力图」

### 用 Qt Designer 改界面

PySide6 版的静态布局都在 `ethercat_scan/ui/main_window.ui`，用 Qt Designer 可视化编辑：

```bash
pyside6-designer ethercat_scan/ui/main_window.ui
# 改完保存，然后重新编译：
pyside6-uic ethercat_scan/ui/main_window.ui -o ethercat_scan/ui/main_window_ui.py
python examples/run_gui_pyside6.py   # 看效果
```

几点注意：

- 控件的 **objectName 必须与代码里的名字一致**：配置项对应 `ScanAppQt.w` 字典的 key
  （`x_start`、`dwell`、`snake`…），读写在 `_g`/`_s` 里按类型分派——
  `QCheckBox`→勾选、`QComboBox`→下拉、其余→文本，所以数值框请用 `QLineEdit`，
  不要用 `QSpinBox/QDoubleSpinBox`（后者没有 `text()`，会报错）。
- 热力图画布（matplotlib）和左右标尺是代码动态生成的，Designer 里只是三个占位容器
  `canvas_holder` / `ruler_x_holder` / `ruler_y_holder`，别删。
- 运行时状态控件 `lbl_status`/`lbl_progress`/`btn_*` 等由代码绑定，改名字需同步改
  [gui_pyside6.py](ethercat_scan/gui_pyside6.py)。

## 关键参数标定

**脉冲/mm** 决定扫描坐标是否正确，由三样决定:

```
pulses_per_mm = 电机转一圈脉冲数 / 丝杠导程(mm)
电机转一圈脉冲数 = 编码器线数 × 4 × 电子齿轮(2408h/2409h)
```

例: 丝杠导程 5mm、编码器 1000 线、4 细分、电子齿轮 1:1 →
`1000*4/5 = 800 脉冲/mm`。先用 `--dry-run` 验证逻辑，再实测标定
(让轴走固定距离、量实际位移反推)。

## 接入真实功率计

框架已留好 `PowerMeter` 抽象接口 (`ethercat_scan/power_meter.py`):

- **USB/GPIB 仪器** (Thorlabs/Newport/Keysight): 用 `ScpiPowerMeter`，
  填 `measure_cmd` 即可，需 `pip install pyvisa` + NI-VISA。
- **串口仪器**: 用 `SerialPowerMeter`，需 `pip install pyserial`。

把 `examples/run_scan.py` 里的 `SimulatedPowerMeter(...)` 换成你的实现即可，
`Scanner` 只调用 `meter.measure()`。

## 扫描流程

1. `prepare()` — 两轴使能并切 PP 模式
2. `home()` (可选 `--home`) — 回零，需接限位开关
3. `scan()` — 逐点: 走到 (x,y) → 等待到位 → 停留 `dwell` → 采 `samples` 次功率取平均 → 记录
4. `save_csv()` / `save_heatmap()` — 导出

## 回零与软限位

框架把「回零原点 + 左右限位」结合成软限位保护：

- **回零方式** (6098h)：`AxisConfig.home_method`，GUI/CLI 可选 17/18/24/29
  （17=负限位, 18=正限位, 24/29=原点开关），按接线选择。
- **软限位**：`AxisConfig.soft_limit_min_mm / soft_limit_max_mm`，以回零原点为 0、
  单位 mm，扫描前校验范围、越界即报错；None 表示该方向不校验（默认）。
- **限位状态**：读取 60FDh（Bit0=负限位, Bit1=正限位, Bit2=原点），GUI 空闲时实时显示。

> 软限位只有在**回零之后**才与限位开关对齐，建议勾选「扫描前回零」。

### 自检 (找左右限位 → 回零)

GUI「自检」按钮对每轴依次执行：**左(负)限位 → 右(正)限位 → 回零复位**，
记录左右限位触发时的轴位置 (mm) 并弹窗显示，供参考填写软限位字段
(留安全余量)。自检结束后轴已回到原点。

> 位置以回零原点为参考；若自检前未回零，则以自检起点为参考，建议先「回零」再自检。

```bash
python examples/run_scan.py \
  --ifname "\\Device\\NPF_{GUID}" --x-alias 0 --y-alias 1 \
  --home-method 24 \
  --x-min 0 --x-max 100 --y-min 0 --y-max 100 \
  --x-range 5 95 1 --y-range 5 95 1
```

## 说明与注意

- 本框架用 **SDO 控制** (不依赖周期 PDO)，简单可靠，适合逐点停测；默认不进 OP
  (从站 TxPDO 默认为空)。若后续要**连续扫描/CSP 同步**，需映射 PDO 并跑周期
  数据，可在 `drive.py`/`master.py` 基础上扩展。
- 上电后若驱动器故障，`enable()` 会自动发 fault reset。
- 回零方式 (6098h) 与软限位见上「回零与软限位」；软限位默认 None 不校验。
