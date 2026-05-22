# CDR

这是一个纯基础版 CDR（Clock and Data Recovery，时钟数据恢复）仿真 demo。

当前版本刻意保持简单：

- 只有一个主程序文件：`cdr_demo.py`
- 不使用 `numpy`
- 不使用任何第三方库
- 只使用 Python 标准库
- 用中文注释解释每一步
- 运行输出放在 `outputs/`，该目录不提交到 git

## 文件结构

```text
cdr_demo.py                  # 主程序，包含信号生成、固定采样、CDR、输出
README.md                    # 项目快速说明
UPDATE_LOG.md                # 每次提交前都要更新，并记录更新时间
docs/CDR_DEMO_EXPLAINED.md   # CDR 原理和代码说明
docs/images/                 # 原理图
outputs/                     # 运行输出，git 忽略
```

## 依赖

不需要安装任何第三方依赖。系统自带 Python 3 即可运行。

## 运行

```bash
python3 cdr_demo.py
```

可选参数：

```bash
python3 cdr_demo.py --bits 5000 --sps 16 --ppm 3000 --noise 0.12 --seed 9
```

默认生成：

- `outputs/cdr_demo_output.csv`：逐 bit 采样结果
- `outputs/cdr_demo_summary.json`：BER、相位误差、周期误差摘要
- `outputs/cdr_demo_phase.svg`：固定采样和 CDR 相位误差图

## 维护约定

每次提交都需要同步更新 `UPDATE_LOG.md`，并写明更新时间。提交信息要说明具体改动点，不要只写 `update` 或 `initial commit`。
