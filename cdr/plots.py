"""Matplotlib visualizations for the CDR demo."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cdr.signal import NRZSignal


def plot_phase_error(fixed: pd.DataFrame, cdr: pd.DataFrame, path: Path) -> None:
    """Plot fixed-clock drift against recovered CDR phase error."""

    fig, ax = plt.subplots(figsize=(11, 4.8), constrained_layout=True)
    ax.plot(fixed["k"], fixed["phase_ui"], color="#c92a2a", lw=1.2, alpha=0.82, label="fixed clock")
    ax.plot(cdr["k"], cdr["phase_ui"], color="#2b8a3e", lw=1.2, label="Alexander CDR")
    ax.axhline(0.0, color="#343a40", lw=1.0)
    ax.axhline(0.5, color="#adb5bd", lw=0.8, ls="--")
    ax.axhline(-0.5, color="#adb5bd", lw=0.8, ls="--")
    ax.set_ylim(-0.75, 0.75)
    ax.set_xlabel("Bit index")
    ax.set_ylabel("Sampling phase error (UI)")
    ax.set_title("Sampling phase: free-running clock vs recovered CDR")
    ax.grid(True, color="#e9ecef", lw=0.8)
    ax.legend(loc="upper right")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _eye_trace(signal: NRZSignal, centers: np.ndarray, span_ui: float = 1.2, points: int = 96) -> tuple[np.ndarray, np.ndarray]:
    x_ui = np.linspace(-0.5 * span_ui, 0.5 * span_ui, points)
    traces = []
    sample_axis = np.arange(signal.samples.size)
    for center in centers:
        times = center + x_ui * signal.true_ui
        if times[0] >= 0 and times[-1] < signal.samples.size - 1:
            traces.append(np.interp(times, sample_axis, signal.samples))
    return x_ui, np.asarray(traces)


def plot_diagnostics(
    signal: NRZSignal,
    fixed: pd.DataFrame,
    cdr: pd.DataFrame,
    fixed_summary: dict[str, float],
    cdr_summary: dict[str, float],
    path: Path,
) -> None:
    """Create a compact engineering diagnostics dashboard."""

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    sample_axis = np.arange(signal.samples.size)

    # Received waveform around the first several symbols.
    ax = axes[0, 0]
    window = int(80 * signal.nominal_sps)
    ax.plot(sample_axis[:window] / signal.nominal_sps, signal.samples[:window], color="#1864ab", lw=1.0)
    ax.set_title("Received noisy NRZ waveform")
    ax.set_xlabel("Receiver time (nominal UI)")
    ax.set_ylabel("Amplitude")
    ax.grid(True, color="#e9ecef")

    # Phase convergence.
    ax = axes[0, 1]
    ax.plot(fixed["k"], np.clip(fixed["phase_ui"], -1.5, 1.5), color="#c92a2a", lw=1.0, label="fixed")
    ax.plot(cdr["k"], cdr["phase_ui"], color="#2b8a3e", lw=1.1, label="CDR")
    ax.axhline(0.0, color="#343a40", lw=0.9)
    ax.axhline(0.5, color="#adb5bd", lw=0.8, ls="--")
    ax.axhline(-0.5, color="#adb5bd", lw=0.8, ls="--")
    ax.set_title("Timing phase error")
    ax.set_xlabel("Bit index")
    ax.set_ylabel("UI")
    ax.legend()
    ax.grid(True, color="#e9ecef")

    # Recovered UI period.
    ax = axes[1, 0]
    ax.plot(cdr["k"], cdr["period"], color="#2f9e44", lw=1.1)
    ax.axhline(signal.true_ui, color="#d9480f", lw=1.2, ls="--", label=f"true UI = {signal.true_ui:.4f}")
    ax.set_title("Recovered UI estimate")
    ax.set_xlabel("Bit index")
    ax.set_ylabel("ADC samples / UI")
    ax.legend()
    ax.grid(True, color="#e9ecef")

    # Eye diagram sampled from the received waveform.
    ax = axes[1, 1]
    rng = np.random.default_rng(0)
    centers = signal.centers[50:-50]
    if centers.size > 260:
        centers = rng.choice(centers, size=260, replace=False)
    x_ui, traces = _eye_trace(signal, np.sort(centers))
    for trace in traces:
        ax.plot(x_ui, trace, color="#495057", alpha=0.06, lw=0.8)
    ax.axvline(0.0, color="#2b8a3e", lw=1.1, label="ideal data sample")
    ax.axvline(-0.5, color="#f08c00", lw=0.9, ls="--", label="edge")
    ax.axvline(0.5, color="#f08c00", lw=0.9, ls="--")
    ax.set_title("Eye diagram view")
    ax.set_xlabel("Time around bit center (UI)")
    ax.set_ylabel("Amplitude")
    ax.legend(loc="upper right")
    ax.grid(True, color="#e9ecef")

    fig.suptitle(
        "CDR diagnostics: "
        f"fixed BER={fixed_summary['ber']:.4f}, "
        f"CDR BER={cdr_summary['ber']:.4f}, "
        f"CDR phase RMS={cdr_summary['rms_phase_ui']:.4f} UI",
        fontsize=14,
    )
    fig.savefig(path, dpi=170)
    plt.close(fig)
