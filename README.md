# CDR

数字信号处理中的 CDR（Clock and Data Recovery，时钟数据恢复）仿真 demo。

本项目使用 `numpy`、`scipy`、`pandas`、`matplotlib` 生成一段带频偏、抖动、噪声和有限上升时间的 NRZ/PAM2 信号，并对比：

- 固定采样时钟：不做相位或频率恢复，作为失败对照组。
- 数字 CDR 环路：使用 Alexander bang-bang 相位检测器恢复采样时钟。

## 项目结构

```text
cdr_demo.py               # 兼容入口，调用 cdr.cli.main()
cdr/
  config.py               # 仿真、环路、输出配置
  signal.py               # NumPy/SciPy 信号生成与信道模型
  recovery.py             # 固定采样器与 Alexander CDR
  plots.py                # Matplotlib 相位图、诊断图、眼图视图
  cli.py                  # 命令行编排与输出
docs/                     # 原理与工程说明
outputs/                  # 运行生成物，git 忽略
UPDATE_LOG.md             # 每次提交前必须更新
```

## 运行

```bash
python3 cdr_demo.py
```

也可以安装成命令行工具：

```bash
python3 -m pip install --user --break-system-packages -e .
cdr-demo
```

如果使用虚拟环境，则不需要 `--user --break-system-packages`：

```bash
source .venv/bin/activate
python -m pip install -e .
cdr-demo
```

## 依赖环境

项目依赖：

- `numpy`
- `matplotlib`
- `scipy`
- `pandas`

重新安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

可选参数：

```bash
python3 cdr_demo.py --bits 5000 --sps 16 --ppm 3000 --noise 0.12 --seed 9
```

默认运行会生成：

- `outputs/cdr_demo_output.csv`：逐 bit 采样、判决、相位误差和 CDR 周期估计数据。
- `outputs/cdr_demo_summary.json`：可机器读取的 BER、相位误差和周期恢复摘要。
- `outputs/cdr_demo_phase.svg`：固定采样和 CDR 的相位误差对比图。
- `outputs/cdr_demo_diagnostics.png`：接收波形、相位误差、周期收敛、眼图视图。

## 文档

- [详细说明文档](docs/CDR_DEMO_EXPLAINED.md)
- [更新记录](UPDATE_LOG.md)

## 维护约定

每次提交都需要同步更新 `UPDATE_LOG.md`，说明本次更新内容。提交信息应简明扼要地说明具体改动点，避免只写 `initial commit`、`update` 这类过于笼统的备注。
