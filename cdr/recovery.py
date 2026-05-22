"""Clock and data recovery algorithms."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cdr.config import CDRLoopConfig, SimulationConfig
from cdr.signal import NRZSignal


def _sample_at(samples: np.ndarray, t: float) -> float:
    if t < 0.0 or t >= samples.size - 1:
        return float("nan")
    i = int(np.floor(t))
    frac = t - i
    return float((1.0 - frac) * samples[i] + frac * samples[i + 1])


def phase_error_ui(signal: NRZSignal, symbol_index: int, t: float) -> float:
    center = signal.centers[symbol_index]
    ui = signal.ui[symbol_index]
    return float((t - center) / ui)


def run_fixed_sampler(
    signal: NRZSignal,
    sim_cfg: SimulationConfig,
    loop_cfg: CDRLoopConfig,
) -> pd.DataFrame:
    """Sample with a free-running local clock.

    This is the control experiment. It intentionally has the same initial
    frequency and phase error as the CDR loop, but it never uses edge feedback.
    """

    period = loop_cfg.initial_period(sim_cfg.nominal_sps)
    t0 = signal.boundaries[0] + (0.5 + sim_cfg.initial_phase_ui) * sim_cfg.nominal_sps
    k = np.arange(signal.levels.size - 1)
    times = t0 + k * period
    valid = times < signal.samples.size - 2
    k = k[valid]
    times = times[valid]

    samples = np.interp(times, np.arange(signal.samples.size), signal.samples)
    decisions = np.where(samples >= 0.0, 1.0, -1.0)
    actual = signal.levels[k]
    phase_ui = (times - signal.centers[k]) / signal.ui[k]

    return pd.DataFrame(
        {
            "k": k,
            "time": times,
            "sample": samples,
            "decision": decisions,
            "actual": actual,
            "phase_ui": phase_ui,
            "error": np.zeros_like(times),
            "period": np.full_like(times, period),
            "transition": np.zeros_like(times, dtype=bool),
        }
    )


def run_alexander_cdr(
    signal: NRZSignal,
    sim_cfg: SimulationConfig,
    loop_cfg: CDRLoopConfig,
) -> pd.DataFrame:
    """Run an Alexander bang-bang CDR loop.

    The loop is second-order in the practical digital-PLL sense:
    ``error`` directly nudges the next sampling phase and also integrates into
    the recovered UI estimate ``period``.
    """

    nominal_sps = sim_cfg.nominal_sps
    period = loop_cfg.initial_period(nominal_sps)
    period_min, period_max = loop_cfg.period_limits(nominal_sps)
    phase_gain = loop_cfg.phase_gain(nominal_sps)
    freq_gain = loop_cfg.freq_gain(nominal_sps)
    t = signal.boundaries[0] + (0.5 + sim_cfg.initial_phase_ui) * nominal_sps

    rows: list[dict[str, float | bool | int]] = []
    previous_decision: float | None = None

    for k in range(signal.levels.size - 1):
        if t + 0.5 * period >= signal.samples.size - 2:
            break

        y = _sample_at(signal.samples, t)
        decision = 1.0 if y >= 0.0 else -1.0
        error = 0.0
        transition = previous_decision is not None and decision != previous_decision

        if transition:
            edge_sample = _sample_at(signal.samples, t - 0.5 * period)
            error = float(np.sign((previous_decision - decision) * edge_sample))
            period = float(np.clip(period + freq_gain * error, period_min, period_max))

        rows.append(
            {
                "k": k,
                "time": t,
                "sample": y,
                "decision": decision,
                "actual": signal.levels[k],
                "phase_ui": phase_error_ui(signal, k, t),
                "error": error,
                "period": period,
                "transition": bool(transition),
            }
        )

        t += period + phase_gain * error
        previous_decision = decision

    return pd.DataFrame(rows)


def summarize_result(
    frame: pd.DataFrame,
    settle_bits: int,
    true_ui: float | None = None,
) -> dict[str, float]:
    """Compute lock-region quality metrics."""

    tail = frame.iloc[settle_bits:] if len(frame) > settle_bits else frame
    if tail.empty:
        return {
            "n_symbols": 0.0,
            "ber": 0.0,
            "median_abs_phase_ui": 0.0,
            "rms_phase_ui": 0.0,
            "mean_period": 0.0,
            "period_error_ppm": 0.0,
            "phase_detector_updates": 0.0,
        }

    wrong = tail["decision"].to_numpy() != tail["actual"].to_numpy()
    phase = tail["phase_ui"].to_numpy(dtype=float)
    period = tail["period"].to_numpy(dtype=float)
    mean_period = float(np.nanmean(period))
    period_error_ppm = 0.0
    if true_ui is not None and true_ui != 0:
        period_error_ppm = float((mean_period / true_ui - 1.0) * 1e6)

    return {
        "n_symbols": float(len(tail)),
        "ber": float(np.mean(wrong)),
        "median_abs_phase_ui": float(np.nanmedian(np.abs(phase))),
        "rms_phase_ui": float(np.sqrt(np.nanmean(phase * phase))),
        "mean_period": mean_period,
        "period_error_ppm": period_error_ppm,
        "phase_detector_updates": float(np.count_nonzero(tail["error"].to_numpy())),
    }


def combine_results(fixed: pd.DataFrame, cdr: pd.DataFrame) -> pd.DataFrame:
    """Create one aligned table for CSV export."""

    fixed_view = fixed.add_prefix("fixed_")
    cdr_view = cdr.add_prefix("cdr_")
    return pd.concat([fixed_view, cdr_view], axis=1)
