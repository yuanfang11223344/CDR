# CDR Demo 基础版说明

本文说明当前基础版 `cdr_demo.py`。这个版本不再使用复杂工程结构，只保留一个主程序文件，并且只使用 `numpy` 一个第三方库。

## 1. 这个程序做什么

程序模拟一个接收端如何从数据流中恢复采样时钟。

它会做三件事：

1. 生成一段带频偏、抖动、噪声和有限带宽的 NRZ/PAM2 信号。
2. 用固定时钟采样，作为失败对照组。
3. 用 Alexander bang-bang CDR 恢复采样点，并和固定采样结果对比。

## 2. 文件构成规则

```text
cdr_demo.py                  # 主程序，所有核心逻辑都在这里
requirements.txt             # 只保留 numpy
README.md                    # 快速运行说明
UPDATE_LOG.md                # 每次提交前都要更新
docs/CDR_DEMO_EXPLAINED.md   # 当前说明文档
docs/images/cdr_loop.svg     # CDR 环路图
docs/images/alexander_pd.svg # Alexander 相位检测器图
outputs/                     # 运行生成物，不提交
```

规则很简单：

- 初学阶段只看 `cdr_demo.py`。
- 修改程序后同步更新 `UPDATE_LOG.md`。
- 运行生成的 CSV、JSON、SVG 都放在 `outputs/`。
- `outputs/` 已经写入 `.gitignore`，不需要提交。

## 3. 运行

```bash
python3 cdr_demo.py
```

常用参数：

```bash
python3 cdr_demo.py --bits 5000 --ppm 3000 --noise 0.12
```

输出文件：

| 文件 | 作用 |
|---|---|
| `outputs/cdr_demo_output.csv` | 保存每个 bit 的采样时间、判决、相位误差 |
| `outputs/cdr_demo_summary.json` | 保存 BER、相位误差、周期误差等摘要 |
| `outputs/cdr_demo_phase.svg` | 保存相位误差曲线图 |

## 4. CDR 原理

CDR 是 Clock and Data Recovery，也就是时钟数据恢复。

在很多高速数字通信里，发送端只发送数据，不单独发送时钟。接收端必须从数据跳变中推断“什么时候采样最安全”。

最安全的位置通常是眼图中心，也就是每个 bit 的中间。

![数字 CDR 环路](images/cdr_loop.svg)

## 5. UI 和相位误差

UI 是 Unit Interval，一个 UI 就是一个 bit 周期。

程序里每个 bit 有两个真实边界：

```text
left  = boundaries[k]
right = boundaries[k + 1]
```

bit 中心：

```text
center = 0.5 * (left + right)
```

当前采样时刻是 `t`，相位误差定义为：

```text
phase_ui = (t - center) / (right - left)
```

含义：

| `phase_ui` | 含义 |
|---:|---|
| `0` | 正好采在 bit 中心 |
| `+0.5` | 接近右边界 |
| `-0.5` | 接近左边界 |
| 绝对值越小 | 采样越安全 |

## 6. 信号如何生成

程序函数 `generate_signal()` 生成接收波形。

### 6.1 bit 到电平

```text
bit = 1  -> level = +1
bit = 0  -> level = -1
```

代码：

```python
bits = rng.integers(0, 2, size=n_bits)
levels = np.where(bits == 1, 1.0, -1.0)
```

### 6.2 真实 UI

真实 UI 由名义采样率和频偏决定：

```text
true_ui = nominal_sps * (1 + ppm_offset * 1e-6)
```

默认：

```text
true_ui = 16 * (1 + 1800 * 1e-6)
        = 16.0288 samples
```

### 6.3 抖动和噪声

程序加入两种抖动：

```text
sinusoidal_jitter  # 低频正弦抖动
random_jitter      # 随机高斯抖动
```

然后用一阶低通模拟有限带宽：

```text
y = y + alpha * (raw[i] - y)
```

最后加入高斯噪声：

```text
samples = samples + random_noise
```

## 7. 固定采样为什么会失败

固定采样器使用一个不变的本地周期：

```text
period = nominal_sps * 0.993
```

它不看数据边沿，也不修正自己。

如果真实 UI 是 `16.0288`，固定周期是 `15.888`，每个 bit 都会差一点。差值会一直累积，最后采样点会从眼图中心漂到边沿附近，误码率变高。

## 8. Alexander Bang-Bang CDR

![Alexander 相位检测器](images/alexander_pd.svg)

CDR 的核心函数是 `run_cdr()`。

它每个 bit 做以下步骤：

1. 在当前时刻 `t` 采样。
2. 根据采样值正负判成 `+1` 或 `-1`。
3. 如果当前判决和上一个判决不同，说明中间有数据跳变。
4. 在半 UI 位置读取边沿采样值。
5. 判断本地时钟早了还是晚了。
6. 更新下一次采样时刻和本地周期估计。

代码核心：

```python
if previous_decision is not None and decision != previous_decision:
    edge_sample = linear_interp(samples, t - 0.5 * period)
    error = np.sign((previous_decision - decision) * edge_sample)
    period = period + freq_gain * error
```

早晚判断：

| `error` | 含义 | 动作 |
|---:|---|---|
| `+1` | 本地时钟偏早 | 下一次采样往后推 |
| `-1` | 本地时钟偏晚 | 下一次采样往前拉 |
| `0` | 没有有效边沿信息 | 不修正 |

下一次采样时刻：

```text
t = t + period + phase_gain * error
```

其中：

| 变量 | 作用 |
|---|---|
| `period` | 当前估计的 UI 长度 |
| `freq_gain` | 控制周期更新速度 |
| `phase_gain` | 控制相位修正速度 |
| `error` | 相位检测器输出 |

## 9. 输出怎么看

运行后终端会打印类似结果：

```text
fixed: BER=..., period_error=...
cdr:   BER=..., period_error=...
```

看重点：

| 指标 | 含义 |
|---|---|
| `BER` | 误码率，越小越好 |
| `median(|phase|)` | 相位误差中位数，越接近 0 越好 |
| `rms(phase)` | 相位误差 RMS，越小越好 |
| `mean_period` | 平均恢复 UI |
| `period_error` | 周期估计误差，单位 ppm |

如果 CDR 成功，通常会看到：

- 固定采样器 BER 接近 `0.5`
- CDR BER 接近 `0`
- CDR 的 `phase_ui` 围绕 `0` 波动
- CDR 的 `mean_period` 接近真实 UI

## 10. 维护规则

项目维护规则保持不变：

1. 每次提交前更新 `UPDATE_LOG.md`。
2. 提交信息要说明具体改动点。
3. 运行输出不提交。
4. 依赖变化同步更新 `requirements.txt`。
5. 代码结构变化同步更新 README 和本文档。
