#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CDR（Clock and Data Recovery，时钟数据恢复）基础版 demo。

这个版本故意写得“朴素”一些：
- 只使用一个第三方库：numpy。
- 不拆复杂包结构，核心逻辑都放在本文件里。
- 多用普通函数、列表、字典和清晰注释，便于逐行理解。

运行：
    python3 cdr_demo.py

输出：
    outputs/cdr_demo_output.csv      每个 bit 的采样结果
    outputs/cdr_demo_summary.json    误码率和相位误差摘要
    outputs/cdr_demo_phase.svg       采样相位误差图
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def parse_args():
    """读取命令行参数。没有传参数时使用默认值。"""

    parser = argparse.ArgumentParser(description="Simple NumPy CDR demo.")
    parser.add_argument("--bits", type=int, default=2500, help="仿真的 bit 数")
    parser.add_argument("--sps", type=float, default=16.0, help="名义每 UI 的 ADC 采样点数")
    parser.add_argument("--ppm", type=float, default=1800.0, help="发送端相对频偏，单位 ppm")
    parser.add_argument("--noise", type=float, default=0.09, help="高斯噪声标准差")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    parser.add_argument("--prefix", default="cdr_demo", help="输出文件名前缀")
    parser.add_argument("--output-dir", default="outputs", help="输出目录")
    return parser.parse_args()


def linear_interp(samples, t):
    """
    在小数采样点 t 处读取波形。

    ADC 波形 samples 只在整数下标处有值，但 CDR 的采样时刻 t 会不断微调，
    所以 t 往往不是整数。这里用最简单的线性插值：

        y(t) = (1 - frac) * samples[i] + frac * samples[i + 1]

    其中 i 是 t 左边的整数点，frac 是小数部分。
    """

    if t < 0 or t >= len(samples) - 1:
        return float("nan")

    i = int(np.floor(t))
    frac = t - i
    return (1.0 - frac) * samples[i] + frac * samples[i + 1]


def phase_error_ui(boundaries, bit_index, t):
    """
    计算采样时刻 t 离真实 bit 中心有多远，单位是 UI。

    phase = 0     表示采在眼图中心
    phase = +0.5  表示采到右边界附近
    phase = -0.5  表示采到左边界附近
    """

    left = boundaries[bit_index]
    right = boundaries[bit_index + 1]
    center = 0.5 * (left + right)
    ui = right - left
    return (t - center) / ui


def generate_signal(n_bits, nominal_sps, ppm_offset, noise_std, seed):
    """
    生成一段带频偏、抖动、噪声和有限带宽的 NRZ/PAM2 信号。

    返回一个字典，里面放后续函数需要的数据：
    - bits: 原始 0/1 数据
    - levels: 映射后的 -1/+1 电平
    - boundaries: 每个 bit 的真实边界
    - samples: 接收端 ADC 看到的波形
    - true_ui: 真实 UI 长度，单位 ADC samples
    """

    rng = np.random.default_rng(seed)

    # 1. 生成随机 bit，并映射为 NRZ/PAM2 电平。
    bits = rng.integers(0, 2, size=n_bits)
    levels = np.where(bits == 1, 1.0, -1.0)

    # 2. 设置发送端真实 UI。
    # ppm_offset 表示发送端和接收端名义时钟之间的频偏。
    true_ui = nominal_sps * (1.0 + ppm_offset * 1e-6)
    start = 10.0 * nominal_sps

    # 3. 生成每个 bit 的真实边界。
    # 这里同时加入低频正弦抖动和随机抖动，让信号更接近真实链路。
    k = np.arange(n_bits + 1)
    sinusoidal_jitter = 0.055 * nominal_sps * np.sin(2.0 * np.pi * k / 310.0)
    random_jitter = rng.normal(0.0, 0.018 * nominal_sps, size=n_bits + 1)
    boundaries = start + k * true_ui + sinusoidal_jitter + random_jitter

    # 防止极端随机抖动让边界倒序。
    for i in range(1, len(boundaries)):
        min_next = boundaries[i - 1] + 0.72 * nominal_sps
        if boundaries[i] < min_next:
            boundaries[i] = min_next

    # 4. 在整数 ADC 采样点上生成理想 NRZ 波形。
    n_samples = int(np.ceil(boundaries[-1] + 20.0 * nominal_sps))
    sample_times = np.arange(n_samples)
    bit_index = np.searchsorted(boundaries, sample_times, side="right") - 1
    bit_index = np.clip(bit_index, 0, n_bits - 1)
    raw = levels[bit_index]

    # 5. 用一阶低通模拟有限带宽。
    # alpha 越小，边沿越慢；alpha 越大，越接近理想方波。
    alpha = 0.38
    samples = np.empty(n_samples)
    y = raw[0]
    for i in range(n_samples):
        y = y + alpha * (raw[i] - y)
        samples[i] = y

    # 6. 加入高斯噪声。
    samples = samples + rng.normal(0.0, noise_std, size=n_samples)

    return {
        "bits": bits,
        "levels": levels,
        "boundaries": boundaries,
        "samples": samples,
        "true_ui": true_ui,
        "nominal_sps": nominal_sps,
    }


def run_fixed_sampler(signal, initial_phase_ui):
    """
    固定采样器：不做 CDR，只用一个固定周期往前采样。

    这个函数用作对照组。因为本地周期和真实 UI 不一样，采样点会一直漂移。
    """

    levels = signal["levels"]
    boundaries = signal["boundaries"]
    samples = signal["samples"]
    nominal_sps = signal["nominal_sps"]

    period = nominal_sps * 0.993
    t = boundaries[0] + (0.5 + initial_phase_ui) * nominal_sps

    rows = []
    for k in range(len(levels) - 1):
        if t >= len(samples) - 2:
            break

        sample_value = linear_interp(samples, t)
        decision = 1.0 if sample_value >= 0.0 else -1.0

        rows.append(
            {
                "k": k,
                "time": t,
                "sample": sample_value,
                "decision": decision,
                "actual": levels[k],
                "phase_ui": phase_error_ui(boundaries, k, t),
                "error": 0.0,
                "period": period,
            }
        )

        t = t + period

    return rows


def run_cdr(signal, initial_phase_ui):
    """
    运行 Alexander bang-bang CDR。

    CDR 的核心想法：
    1. 在当前估计的 bit 中心采样并判决。
    2. 如果当前 bit 和上一个 bit 不同，说明中间发生了跳变。
    3. 在半 UI 位置读取边沿采样值，判断本地时钟早了还是晚了。
    4. 根据早/晚结果修正下一次采样时刻，并慢慢修正本地 UI 长度。
    """

    levels = signal["levels"]
    boundaries = signal["boundaries"]
    samples = signal["samples"]
    nominal_sps = signal["nominal_sps"]

    # 初始周期故意设错一点，这样能看到 CDR 拉回锁定的过程。
    period = nominal_sps * 0.993
    t = boundaries[0] + (0.5 + initial_phase_ui) * nominal_sps

    # phase_gain 负责快速调整“下一次采样相位”。
    # freq_gain 负责慢慢调整“本地 UI 周期估计”。
    phase_gain = 0.11 * nominal_sps
    freq_gain = 0.0007 * nominal_sps

    # 给周期估计加上下限，避免噪声让环路跑飞。
    min_period = 0.96 * nominal_sps
    max_period = 1.04 * nominal_sps

    rows = []
    previous_decision = None

    for k in range(len(levels) - 1):
        if t + 0.5 * period >= len(samples) - 2:
            break

        sample_value = linear_interp(samples, t)
        decision = 1.0 if sample_value >= 0.0 else -1.0
        error = 0.0

        # 只有数据翻转时，中间边沿才提供“早/晚”信息。
        if previous_decision is not None and decision != previous_decision:
            edge_sample = linear_interp(samples, t - 0.5 * period)

            # Alexander 相位检测器：
            # error > 0：本地时钟偏早，下一次采样往后推
            # error < 0：本地时钟偏晚，下一次采样往前拉
            error = np.sign((previous_decision - decision) * edge_sample)

            # 用 error 慢慢修正本地周期估计。
            period = period + freq_gain * error
            period = min(max(period, min_period), max_period)

        rows.append(
            {
                "k": k,
                "time": t,
                "sample": sample_value,
                "decision": decision,
                "actual": levels[k],
                "phase_ui": phase_error_ui(boundaries, k, t),
                "error": error,
                "period": period,
            }
        )

        # 更新下一次采样时刻。
        t = t + period + phase_gain * error
        previous_decision = decision

    return rows


def summarize(rows, true_ui, settle_bits=300):
    """统计锁定后的误码率、相位误差和周期误差。"""

    if len(rows) > settle_bits:
        rows = rows[settle_bits:]

    if not rows:
        return {
            "ber": 0.0,
            "median_abs_phase_ui": 0.0,
            "rms_phase_ui": 0.0,
            "mean_period": 0.0,
            "period_error_ppm": 0.0,
            "updates": 0,
        }

    decisions = np.array([row["decision"] for row in rows])
    actual = np.array([row["actual"] for row in rows])
    phase = np.array([row["phase_ui"] for row in rows])
    period = np.array([row["period"] for row in rows])
    errors = np.array([row["error"] for row in rows])

    mean_period = float(np.mean(period))

    return {
        "ber": float(np.mean(decisions != actual)),
        "median_abs_phase_ui": float(np.median(np.abs(phase))),
        "rms_phase_ui": float(np.sqrt(np.mean(phase * phase))),
        "mean_period": mean_period,
        "period_error_ppm": float((mean_period / true_ui - 1.0) * 1e6),
        "updates": int(np.count_nonzero(errors)),
    }


def write_csv(path, fixed_rows, cdr_rows):
    """把固定采样器和 CDR 的逐 bit 数据写入 CSV。"""

    path.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "k",
        "fixed_time",
        "fixed_decision",
        "fixed_phase_ui",
        "cdr_time",
        "cdr_decision",
        "cdr_phase_ui",
        "cdr_error",
        "cdr_period",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        n = max(len(fixed_rows), len(cdr_rows))
        for i in range(n):
            fixed = fixed_rows[i] if i < len(fixed_rows) else {}
            cdr = cdr_rows[i] if i < len(cdr_rows) else {}

            writer.writerow(
                {
                    "k": i,
                    "fixed_time": fixed.get("time", ""),
                    "fixed_decision": fixed.get("decision", ""),
                    "fixed_phase_ui": fixed.get("phase_ui", ""),
                    "cdr_time": cdr.get("time", ""),
                    "cdr_decision": cdr.get("decision", ""),
                    "cdr_phase_ui": cdr.get("phase_ui", ""),
                    "cdr_error": cdr.get("error", ""),
                    "cdr_period": cdr.get("period", ""),
                }
            )


def make_polyline(rows, width, height, color):
    """把 phase_ui 数据转换为 SVG 折线。"""

    left = 60
    right = 20
    top = 30
    bottom = 40
    plot_w = width - left - right
    plot_h = height - top - bottom

    y_min = -0.6
    y_max = 0.6
    n = max(1, len(rows) - 1)

    points = []
    step = max(1, len(rows) // 1000)

    for i in range(0, len(rows), step):
        phase = rows[i]["phase_ui"]
        phase = min(max(phase, y_min), y_max)

        x = left + plot_w * i / n
        y = top + plot_h * (y_max - phase) / (y_max - y_min)
        points.append(f"{x:.1f},{y:.1f}")

    return f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{" ".join(points)}" />'


def write_svg(path, fixed_rows, cdr_rows):
    """不用绘图库，直接生成一个简单 SVG 相位误差图。"""

    path.parent.mkdir(parents=True, exist_ok=True)

    width = 1000
    height = 420
    left = 60
    right = 20
    top = 30
    bottom = 40
    plot_h = height - top - bottom

    def y_from_phase(phase):
        return top + plot_h * (0.6 - phase) / 1.2

    grid = []
    for phase, label in [(0.5, "+0.5 UI"), (0.0, "0"), (-0.5, "-0.5 UI")]:
        y = y_from_phase(phase)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#d8dee9" />')
        grid.append(f'<text x="8" y="{y + 4:.1f}" font-size="13" fill="#4c566a">{label}</text>')

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="{left}" y="22" font-size="16" fill="#2e3440">CDR phase error</text>
  {"".join(grid)}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#4c566a" />
  <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#4c566a" />
  {make_polyline(fixed_rows, width, height, "#c92a2a")}
  {make_polyline(cdr_rows, width, height, "#2b8a3e")}
  <text x="{left}" y="{height - 12}" font-size="13" fill="#4c566a">bit index</text>
  <rect x="760" y="18" width="12" height="12" fill="#c92a2a" />
  <text x="778" y="29" font-size="13" fill="#2e3440">fixed clock</text>
  <rect x="870" y="18" width="12" height="12" fill="#2b8a3e" />
  <text x="888" y="29" font-size="13" fill="#2e3440">CDR</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def print_summary(name, summary):
    """打印一行统计结果。"""

    print(
        f"{name:>10s}: "
        f"BER={summary['ber']:.6f}, "
        f"median(|phase|)={summary['median_abs_phase_ui']:.4f} UI, "
        f"rms(phase)={summary['rms_phase_ui']:.4f} UI, "
        f"mean_period={summary['mean_period']:.4f}, "
        f"period_error={summary['period_error_ppm']:.1f} ppm"
    )


def main():
    args = parse_args()

    # 这两个参数单独写在这里，方便初学者直接修改。
    initial_phase_ui = 0.28
    settle_bits = 300

    signal = generate_signal(
        n_bits=args.bits,
        nominal_sps=args.sps,
        ppm_offset=args.ppm,
        noise_std=args.noise,
        seed=args.seed,
    )

    fixed_rows = run_fixed_sampler(signal, initial_phase_ui)
    cdr_rows = run_cdr(signal, initial_phase_ui)

    fixed_summary = summarize(fixed_rows, signal["true_ui"], settle_bits)
    cdr_summary = summarize(cdr_rows, signal["true_ui"], settle_bits)

    output_dir = Path(args.output_dir)
    csv_path = output_dir / f"{args.prefix}_output.csv"
    json_path = output_dir / f"{args.prefix}_summary.json"
    svg_path = output_dir / f"{args.prefix}_phase.svg"

    write_csv(csv_path, fixed_rows, cdr_rows)
    write_svg(svg_path, fixed_rows, cdr_rows)

    summary = {
        "true_ui": signal["true_ui"],
        "nominal_sps": signal["nominal_sps"],
        "fixed": fixed_summary,
        "cdr": cdr_summary,
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("CDR simulation finished")
    print(f"true UI={signal['true_ui']:.4f} samples, nominal UI={signal['nominal_sps']:.4f} samples")
    print_summary("fixed", fixed_summary)
    print_summary("cdr", cdr_summary)
    print(f"CDR phase-detector updates after settle: {cdr_summary['updates']}")
    print(f"wrote: {csv_path}")
    print(f"wrote: {json_path}")
    print(f"wrote: {svg_path}")


if __name__ == "__main__":
    main()
