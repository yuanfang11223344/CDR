#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CDR（Clock and Data Recovery，时钟数据恢复）数字仿真示例。

本脚本做三件事：
1. 生成一段带频偏、抖动、噪声和有限上升时间的 NRZ/PAM2 信号。
2. 用“固定采样时钟”和“数字 CDR 环路”分别采样判决。
3. 输出误码率、采样相位误差，并生成 CSV 与 SVG 图用于观察锁定过程。

无需第三方库，直接运行：
    python3 cdr_demo.py
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Config:
    """仿真参数。UI 表示一个比特周期（Unit Interval）。"""

    n_bits: int = 2500
    nominal_sps: float = 16.0  # 接收端名义上每 UI 的 ADC 采样点数
    ppm_offset: float = 1800.0  # 发送端 UI 相对接收端的频偏，单位 ppm
    initial_phase_ui: float = 0.28  # 初始采样点偏离眼图中心的 UI 数
    noise_std: float = 0.09
    seed: int = 7
    output_prefix: str = "cdr_demo"


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def sgn(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def linear_interp(samples: list[float], t: float) -> float:
    """对 ADC 离散采样做线性插值，使 CDR 可以在小数采样点处取值。"""

    if t < 0.0 or t >= len(samples) - 1:
        return float("nan")
    i = int(math.floor(t))
    frac = t - i
    return samples[i] * (1.0 - frac) + samples[i + 1] * frac


def generate_nrz_signal(cfg: Config) -> tuple[list[int], list[float], list[float], list[float], float]:
    """
    生成接收端 ADC 看到的 NRZ 波形。

    bits/levels 是发送的数据；boundaries 是每个真实比特边界在 ADC 采样坐标里的位置。
    samples 是经过一阶低通、加噪声后的 ADC 采样序列。
    """

    rng = random.Random(cfg.seed)
    bits = [rng.randrange(2) for _ in range(cfg.n_bits)]
    levels = [1.0 if bit else -1.0 for bit in bits]

    # true_ui 是发送端真实 UI，在接收端 ADC 采样坐标中略有偏差。
    true_ui = cfg.nominal_sps * (1.0 + cfg.ppm_offset * 1e-6)
    start = 10.0 * cfg.nominal_sps

    # 给比特边界加入随机抖动和低频正弦抖动，模拟真实链路中的时基不稳定。
    boundaries: list[float] = []
    for k in range(cfg.n_bits + 1):
        sinusoidal_jitter = 0.055 * cfg.nominal_sps * math.sin(2.0 * math.pi * k / 310.0)
        random_jitter = rng.gauss(0.0, 0.018 * cfg.nominal_sps)
        boundary = start + k * true_ui + sinusoidal_jitter + random_jitter
        if boundaries and boundary <= boundaries[-1] + 0.72 * cfg.nominal_sps:
            boundary = boundaries[-1] + 0.72 * cfg.nominal_sps
        boundaries.append(boundary)

    # 按 ADC 的均匀采样时刻生成矩形 NRZ，再用一阶低通模拟有限带宽/上升时间。
    n_samples = math.ceil(boundaries[-1] + 20.0 * cfg.nominal_sps)
    samples: list[float] = []
    bit_index = 0
    channel_alpha = 0.38
    y = levels[0]

    for n in range(n_samples):
        while bit_index + 1 < cfg.n_bits and n >= boundaries[bit_index + 1]:
            bit_index += 1
        raw = levels[bit_index]
        y += channel_alpha * (raw - y)
        samples.append(y + rng.gauss(0.0, cfg.noise_std))

    return bits, levels, boundaries, samples, true_ui


def phase_error_for_symbol(boundaries: list[float], symbol_index: int, t: float) -> float:
    """返回采样点相对该 bit 真实中心的误差，单位为 UI。0 表示正好在眼图中心。"""

    center = 0.5 * (boundaries[symbol_index] + boundaries[symbol_index + 1])
    ui = boundaries[symbol_index + 1] - boundaries[symbol_index]
    return (t - center) / ui


def run_fixed_sampler(
    cfg: Config,
    levels: list[float],
    boundaries: list[float],
    samples: list[float],
) -> list[dict[str, float]]:
    """固定采样时钟：不根据数据边沿修正相位或频率，用作 CDR 的对照组。"""

    period = cfg.nominal_sps * 0.993
    t = boundaries[0] + (0.5 + cfg.initial_phase_ui) * cfg.nominal_sps
    rows: list[dict[str, float]] = []

    for k in range(len(levels) - 1):
        if t >= len(samples) - 2:
            break
        y = linear_interp(samples, t)
        decision = 1.0 if y >= 0.0 else -1.0
        rows.append(
            {
                "k": float(k),
                "time": t,
                "sample": y,
                "decision": decision,
                "actual": levels[k],
                "phase_ui": phase_error_for_symbol(boundaries, k, t),
            }
        )
        t += period

    return rows


def run_cdr(
    cfg: Config,
    levels: list[float],
    boundaries: list[float],
    samples: list[float],
) -> list[dict[str, float]]:
    """
    数字 CDR：Alexander bang-bang 相位检测器 + 简单二阶环路。

    对每个 bit，CDR 在预计的眼图中心采样判决；如果前后两个判决不同，
    说明中间存在数据翻转，于是读取“半 UI 处”的边沿采样 edge_sample。

    error = sign((previous_decision - current_decision) * edge_sample)
      error > 0：本地时钟偏早，下一次采样点向后推一点
      error < 0：本地时钟偏晚，下一次采样点向前拉一点

    phase_gain 改相位，freq_gain 改估计 UI 长度；这就是一个数字 PLL。
    """

    period = cfg.nominal_sps * 0.993
    t = boundaries[0] + (0.5 + cfg.initial_phase_ui) * cfg.nominal_sps

    phase_gain = 0.11 * cfg.nominal_sps
    freq_gain = 0.0007 * cfg.nominal_sps
    min_period = 0.96 * cfg.nominal_sps
    max_period = 1.04 * cfg.nominal_sps

    previous_decision: float | None = None
    rows: list[dict[str, float]] = []

    for k in range(len(levels) - 1):
        if t + 0.5 * period >= len(samples) - 2:
            break

        y = linear_interp(samples, t)
        decision = 1.0 if y >= 0.0 else -1.0
        error = 0.0

        # 只有数据发生 0/1 翻转时，边沿位置才提供有效的相位信息。
        if previous_decision is not None and decision != previous_decision:
            edge_sample = linear_interp(samples, t - 0.5 * period)
            error = sgn((previous_decision - decision) * edge_sample)
            period = clamp(period + freq_gain * error, min_period, max_period)

        rows.append(
            {
                "k": float(k),
                "time": t,
                "sample": y,
                "decision": decision,
                "actual": levels[k],
                "phase_ui": phase_error_for_symbol(boundaries, k, t),
                "error": error,
                "period": period,
            }
        )

        t += period + phase_gain * error
        previous_decision = decision

    return rows


def summarize(rows: list[dict[str, float]], settle: int = 300) -> tuple[float, float, float]:
    """忽略前 settle 个 bit 的捕获过程，统计锁定后的 BER 和相位误差。"""

    tail = rows[settle:] if len(rows) > settle else rows
    if not tail:
        return 0.0, 0.0, 0.0

    errors = sum(1 for row in tail if row["decision"] != row["actual"])
    ber = errors / len(tail)
    phase_values = [row["phase_ui"] for row in tail if math.isfinite(row["phase_ui"])]
    median_abs_phase = statistics.median(abs(v) for v in phase_values) if phase_values else 0.0
    rms_phase = math.sqrt(sum(v * v for v in phase_values) / len(phase_values)) if phase_values else 0.0
    return ber, median_abs_phase, rms_phase


def format_summary(name: str, rows: list[dict[str, float]]) -> str:
    ber, median_abs_phase, rms_phase = summarize(rows)
    return (
        f"{name:>10s}: BER(after lock)={ber:.6f}, "
        f"median(|phase|)={median_abs_phase:.4f} UI, "
        f"rms(phase)={rms_phase:.4f} UI"
    )


def write_csv(path: Path, fixed: list[dict[str, float]], cdr: list[dict[str, float]]) -> None:
    """把两种采样方式的关键数据写入 CSV，便于后续用 Excel/Python 画图。"""

    fieldnames = [
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
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i in range(max(len(fixed), len(cdr))):
            fixed_row = fixed[i] if i < len(fixed) else {}
            cdr_row = cdr[i] if i < len(cdr) else {}
            writer.writerow(
                {
                    "k": i,
                    "fixed_time": fixed_row.get("time", ""),
                    "fixed_decision": fixed_row.get("decision", ""),
                    "fixed_phase_ui": fixed_row.get("phase_ui", ""),
                    "cdr_time": cdr_row.get("time", ""),
                    "cdr_decision": cdr_row.get("decision", ""),
                    "cdr_phase_ui": cdr_row.get("phase_ui", ""),
                    "cdr_error": cdr_row.get("error", ""),
                    "cdr_period": cdr_row.get("period", ""),
                }
            )


def decimated_points(rows: list[dict[str, float]], max_points: int = 1000) -> Iterable[tuple[int, float]]:
    step = max(1, len(rows) // max_points)
    for i in range(0, len(rows), step):
        yield i, rows[i]["phase_ui"]


def svg_polyline(rows: list[dict[str, float]], width: int, height: int, color: str) -> str:
    """生成相位误差折线。为了突出眼图中心，显示范围裁剪在 +/-0.6 UI。"""

    margin_left = 64
    margin_right = 24
    margin_top = 28
    margin_bottom = 42
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    y_min = -0.6
    y_max = 0.6
    n = max(1, len(rows) - 1)

    points: list[str] = []
    for i, phase in decimated_points(rows):
        phase = clamp(phase, y_min, y_max)
        x = margin_left + plot_w * i / n
        y = margin_top + plot_h * (y_max - phase) / (y_max - y_min)
        points.append(f"{x:.1f},{y:.1f}")
    return f'<polyline fill="none" stroke="{color}" stroke-width="1.8" points="{" ".join(points)}" />'


def write_svg(path: Path, fixed: list[dict[str, float]], cdr: list[dict[str, float]]) -> None:
    """写一个轻量 SVG，相当于不用 matplotlib 的相位误差图。"""

    width = 1000
    height = 420
    margin_left = 64
    margin_right = 24
    margin_top = 28
    margin_bottom = 42
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    def y_for_phase(phase: float) -> float:
        return margin_top + plot_h * (0.6 - phase) / 1.2

    grid_lines = []
    for phase, label in [(0.5, "+0.5 UI"), (0.0, "0"), (-0.5, "-0.5 UI")]:
        y = y_for_phase(phase)
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" '
            f'stroke="#d8dee9" stroke-width="1" />'
        )
        grid_lines.append(
            f'<text x="12" y="{y + 4:.1f}" font-size="13" fill="#4c566a">{label}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="{margin_left}" y="20" font-size="16" fill="#2e3440">CDR phase error demo</text>
  {"".join(grid_lines)}
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#4c566a" />
  <line x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" stroke="#4c566a" />
  {svg_polyline(fixed, width, height, "#bf616a")}
  {svg_polyline(cdr, width, height, "#2b8a3e")}
  <text x="{margin_left}" y="{height - 14}" font-size="13" fill="#4c566a">bit index</text>
  <rect x="{width - 210}" y="18" width="12" height="12" fill="#bf616a" />
  <text x="{width - 190}" y="29" font-size="13" fill="#2e3440">fixed clock</text>
  <rect x="{width - 110}" y="18" width="12" height="12" fill="#2b8a3e" />
  <text x="{width - 90}" y="29" font-size="13" fill="#2e3440">CDR</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Digital CDR simulation for NRZ/PAM2 data.")
    parser.add_argument("--bits", type=int, default=2500, help="number of simulated bits")
    parser.add_argument("--sps", type=float, default=16.0, help="nominal ADC samples per UI")
    parser.add_argument("--ppm", type=float, default=1800.0, help="transmitter UI frequency offset in ppm")
    parser.add_argument("--noise", type=float, default=0.09, help="Gaussian noise standard deviation")
    parser.add_argument("--seed", type=int, default=7, help="random seed")
    parser.add_argument("--prefix", default="cdr_demo", help="output file prefix")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        n_bits=args.bits,
        nominal_sps=args.sps,
        ppm_offset=args.ppm,
        noise_std=args.noise,
        seed=args.seed,
        output_prefix=args.prefix,
    )

    bits, levels, boundaries, samples, true_ui = generate_nrz_signal(cfg)
    fixed = run_fixed_sampler(cfg, levels, boundaries, samples)
    cdr = run_cdr(cfg, levels, boundaries, samples)

    csv_path = Path(f"{cfg.output_prefix}_output.csv")
    svg_path = Path(f"{cfg.output_prefix}_phase.svg")
    write_csv(csv_path, fixed, cdr)
    write_svg(svg_path, fixed, cdr)

    avg_cdr_period = statistics.mean(row["period"] for row in cdr[-100:]) if cdr else 0.0
    transition_updates = sum(1 for row in cdr if row["error"] != 0.0)

    print("CDR simulation finished")
    print(f"true UI={true_ui:.4f} ADC samples, nominal UI={cfg.nominal_sps:.4f} ADC samples")
    print(format_summary("fixed", fixed))
    print(format_summary("cdr", cdr))
    print(f"CDR average recovered UI over last 100 bits: {avg_cdr_period:.4f} ADC samples")
    print(f"CDR phase-detector updates: {transition_updates}")
    print(f"wrote: {csv_path}")
    print(f"wrote: {svg_path}")

    # 避免变量 bits 被优化工具误判为未使用；这里也提示数据长度。
    print(f"simulated bits: {len(bits)}")


if __name__ == "__main__":
    main()
