"""Command-line interface for the CDR demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cdr.config import CDRLoopConfig, OutputConfig, SimulationConfig
from cdr.plots import plot_diagnostics, plot_phase_error
from cdr.recovery import combine_results, run_alexander_cdr, run_fixed_sampler, summarize_result
from cdr.signal import generate_nrz_signal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Digital CDR simulation for NRZ/PAM2 data.")
    parser.add_argument("--bits", type=int, default=2500, help="number of simulated bits")
    parser.add_argument("--sps", type=float, default=16.0, help="nominal ADC samples per UI")
    parser.add_argument("--ppm", type=float, default=1800.0, help="transmitter UI frequency offset in ppm")
    parser.add_argument("--noise", type=float, default=0.09, help="Gaussian noise standard deviation")
    parser.add_argument("--seed", type=int, default=7, help="random seed")
    parser.add_argument("--prefix", default="cdr_demo", help="output file prefix")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="directory for generated files")
    parser.add_argument("--settle", type=int, default=300, help="symbols ignored before computing lock metrics")
    parser.add_argument("--phase-gain-ui", type=float, default=0.11, help="phase correction gain in UI")
    parser.add_argument("--freq-gain-ui", type=float, default=0.0007, help="frequency correction gain in UI")
    parser.add_argument("--no-plots", action="store_true", help="skip Matplotlib SVG/PNG outputs")
    return parser


def _summary_line(name: str, metrics: dict[str, float]) -> str:
    return (
        f"{name:>10s}: BER(after lock)={metrics['ber']:.6f}, "
        f"median(|phase|)={metrics['median_abs_phase_ui']:.4f} UI, "
        f"rms(phase)={metrics['rms_phase_ui']:.4f} UI, "
        f"mean_period={metrics['mean_period']:.4f}, "
        f"period_error={metrics['period_error_ppm']:.1f} ppm"
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    sim_cfg = SimulationConfig(
        n_bits=args.bits,
        nominal_sps=args.sps,
        ppm_offset=args.ppm,
        noise_std=args.noise,
        seed=args.seed,
    )
    loop_cfg = CDRLoopConfig(
        phase_gain_ui=args.phase_gain_ui,
        freq_gain_ui=args.freq_gain_ui,
        settle_bits=args.settle,
    )
    out_cfg = OutputConfig(prefix=args.prefix, output_dir=args.output_dir)
    out_cfg.output_dir.mkdir(parents=True, exist_ok=True)

    signal = generate_nrz_signal(sim_cfg)
    fixed = run_fixed_sampler(signal, sim_cfg, loop_cfg)
    cdr = run_alexander_cdr(signal, sim_cfg, loop_cfg)
    fixed_summary = summarize_result(fixed, loop_cfg.settle_bits, signal.true_ui)
    cdr_summary = summarize_result(cdr, loop_cfg.settle_bits, signal.true_ui)

    csv_path = out_cfg.path("output.csv")
    summary_path = out_cfg.path("summary.json")
    combine_results(fixed, cdr).to_csv(csv_path, index=False)
    summary = {
        "simulation": {
            "bits": sim_cfg.n_bits,
            "nominal_sps": sim_cfg.nominal_sps,
            "true_ui": signal.true_ui,
            "ppm_offset": sim_cfg.ppm_offset,
            "noise_std": sim_cfg.noise_std,
            "seed": sim_cfg.seed,
        },
        "fixed": fixed_summary,
        "cdr": cdr_summary,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    written = [csv_path, summary_path]
    if not args.no_plots:
        phase_path = out_cfg.path("phase.svg")
        diagnostics_path = out_cfg.path("diagnostics.png")
        plot_phase_error(fixed, cdr, phase_path)
        plot_diagnostics(signal, fixed, cdr, fixed_summary, cdr_summary, diagnostics_path)
        written.extend([phase_path, diagnostics_path])

    print("CDR simulation finished")
    print(f"true UI={signal.true_ui:.4f} ADC samples, nominal UI={sim_cfg.nominal_sps:.4f} ADC samples")
    print(_summary_line("fixed", fixed_summary))
    print(_summary_line("cdr", cdr_summary))
    print(f"CDR phase-detector updates after settle: {cdr_summary['phase_detector_updates']:.0f}")
    for path in written:
        print(f"wrote: {path}")


if __name__ == "__main__":
    main()
