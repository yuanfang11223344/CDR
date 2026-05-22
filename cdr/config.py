"""Configuration objects for the CDR simulation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimulationConfig:
    """Signal and channel parameters.

    UI means Unit Interval, the duration of one transmitted bit.
    Values ending in ``_ui`` are normalized to UI; values ending in ``_sps``
    are measured in ADC samples per UI.
    """

    n_bits: int = 2500
    nominal_sps: float = 16.0
    ppm_offset: float = 1800.0
    initial_phase_ui: float = 0.28
    noise_std: float = 0.09
    seed: int = 7
    channel_alpha: float = 0.38
    sinusoidal_jitter_ui: float = 0.055
    random_jitter_ui: float = 0.018
    jitter_period_bits: float = 310.0
    start_ui: float = 10.0
    tail_ui: float = 20.0
    min_boundary_spacing_ui: float = 0.72

    @property
    def true_ui(self) -> float:
        """Transmitter UI measured in receiver ADC samples."""

        return self.nominal_sps * (1.0 + self.ppm_offset * 1e-6)


@dataclass(frozen=True)
class CDRLoopConfig:
    """Digital loop parameters for the Alexander CDR."""

    initial_period_scale: float = 0.993
    phase_gain_ui: float = 0.11
    freq_gain_ui: float = 0.0007
    min_period_scale: float = 0.96
    max_period_scale: float = 1.04
    settle_bits: int = 300

    def initial_period(self, nominal_sps: float) -> float:
        return nominal_sps * self.initial_period_scale

    def phase_gain(self, nominal_sps: float) -> float:
        return nominal_sps * self.phase_gain_ui

    def freq_gain(self, nominal_sps: float) -> float:
        return nominal_sps * self.freq_gain_ui

    def period_limits(self, nominal_sps: float) -> tuple[float, float]:
        return nominal_sps * self.min_period_scale, nominal_sps * self.max_period_scale


@dataclass(frozen=True)
class OutputConfig:
    """Output file naming policy."""

    prefix: str = "cdr_demo"
    output_dir: Path = Path("outputs")

    def path(self, suffix: str) -> Path:
        return self.output_dir / f"{self.prefix}_{suffix}"
