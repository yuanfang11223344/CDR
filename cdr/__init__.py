"""CDR timing-recovery simulation package."""

from cdr.config import CDRLoopConfig, SimulationConfig
from cdr.recovery import run_alexander_cdr, run_fixed_sampler, summarize_result
from cdr.signal import NRZSignal, generate_nrz_signal

__all__ = [
    "CDRLoopConfig",
    "NRZSignal",
    "SimulationConfig",
    "generate_nrz_signal",
    "run_alexander_cdr",
    "run_fixed_sampler",
    "summarize_result",
]
