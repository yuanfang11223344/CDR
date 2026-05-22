"""Vectorized NRZ/PAM2 signal generation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal

from cdr.config import SimulationConfig


@dataclass(frozen=True)
class NRZSignal:
    """All data needed by the samplers and CDR loop."""

    bits: np.ndarray
    levels: np.ndarray
    boundaries: np.ndarray
    samples: np.ndarray
    true_ui: float
    nominal_sps: float

    @property
    def centers(self) -> np.ndarray:
        return 0.5 * (self.boundaries[:-1] + self.boundaries[1:])

    @property
    def ui(self) -> np.ndarray:
        return np.diff(self.boundaries)


def _monotonic_boundaries(boundaries: np.ndarray, min_spacing: float) -> np.ndarray:
    """Guarantee physically valid bit boundaries after jitter is applied."""

    fixed = boundaries.copy()
    for idx in range(1, fixed.size):
        fixed[idx] = max(fixed[idx], fixed[idx - 1] + min_spacing)
    return fixed


def generate_nrz_signal(cfg: SimulationConfig) -> NRZSignal:
    """Generate a noisy NRZ/PAM2 waveform as a receiver would see it.

    The model includes deterministic frequency offset, sinusoidal jitter,
    random Gaussian jitter, a one-pole bandwidth limit, and additive noise.
    """

    rng = np.random.default_rng(cfg.seed)
    bits = rng.integers(0, 2, size=cfg.n_bits, dtype=np.int8)
    levels = np.where(bits == 1, 1.0, -1.0).astype(float)

    k = np.arange(cfg.n_bits + 1, dtype=float)
    start = cfg.start_ui * cfg.nominal_sps
    sinusoidal_jitter = (
        cfg.sinusoidal_jitter_ui
        * cfg.nominal_sps
        * np.sin(2.0 * np.pi * k / cfg.jitter_period_bits)
    )
    random_jitter = rng.normal(
        loc=0.0,
        scale=cfg.random_jitter_ui * cfg.nominal_sps,
        size=cfg.n_bits + 1,
    )
    boundaries = start + k * cfg.true_ui + sinusoidal_jitter + random_jitter
    boundaries = _monotonic_boundaries(
        boundaries,
        min_spacing=cfg.min_boundary_spacing_ui * cfg.nominal_sps,
    )

    n_samples = int(np.ceil(boundaries[-1] + cfg.tail_ui * cfg.nominal_sps))
    sample_times = np.arange(n_samples, dtype=float)
    bit_index = np.searchsorted(boundaries, sample_times, side="right") - 1
    bit_index = np.clip(bit_index, 0, cfg.n_bits - 1)
    raw = levels[bit_index]

    # One-pole low-pass: y[n] = y[n-1] + alpha * (x[n] - y[n-1]).
    alpha = cfg.channel_alpha
    filtered, _ = scipy_signal.lfilter(
        [alpha],
        [1.0, -(1.0 - alpha)],
        raw,
        zi=[(1.0 - alpha) * raw[0]],
    )
    samples = filtered + rng.normal(0.0, cfg.noise_std, size=n_samples)

    return NRZSignal(
        bits=bits,
        levels=levels,
        boundaries=boundaries,
        samples=samples,
        true_ui=cfg.true_ui,
        nominal_sps=cfg.nominal_sps,
    )
