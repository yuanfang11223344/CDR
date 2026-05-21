# CDR

数字信号处理中的 CDR（Clock and Data Recovery，时钟数据恢复）仿真 demo。

本项目使用纯 Python 标准库生成一段带频偏、抖动、噪声和有限上升时间的 NRZ/PAM2 信号，并对比：

- 固定采样时钟：不做相位或频率恢复，作为失败对照组。
- 数字 CDR 环路：使用 Alexander bang-bang 相位检测器恢复采样时钟。

## 运行

```bash
python3 cdr_demo.py
```

## 依赖环境

当前基础脚本只依赖 Python 标准库；为了后续扩展 NumPy 版本、绘制更丰富的曲线和做数据分析，项目虚拟环境已安装：

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

- `cdr_demo_output.csv`：逐 bit 采样、判决、相位误差和 CDR 周期估计数据。
- `cdr_demo_phase.svg`：固定采样和 CDR 的相位误差对比图。

## 文档

- [详细说明文档](docs/CDR_DEMO_EXPLAINED.md)
- [更新记录](UPDATE_LOG.md)

## 维护约定

每次提交都需要同步更新 `UPDATE_LOG.md`，说明本次更新内容。提交信息应简明扼要地说明具体改动点，避免只写 `initial commit`、`update` 这类过于笼统的备注。
