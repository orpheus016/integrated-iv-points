"""Offline evaluation tool: run multiple backbones over CSV testbench data.

Produces per-file PNG overlays and a CSV summary of simple metrics (RMSE, MAE, MaxAbs)
for snapshot voltages when available. The decided snapshot is highlighted with a star
and written into the metrics CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..config.config import build_arg_parser, build_simulation_config
from ..utils.evaluate_helpers import (
	build_source_iterator_eval as build_source_iterator,
	evaluate_file,
	evaluate_samples,
	plot_results,
	write_summary,
)


def _resolve_source(args) -> str:
	input_path = Path(args.input)
	if args.source == "dummy" and input_path.exists():
		return "csv"
	return args.source


def _collect_input_files(input_path: Path) -> List[Path]:
	if input_path.is_dir():
		return sorted(input_path.glob("*.csv"))
	return [input_path]


def main(argv: Optional[List[str]] = None) -> None:
	parser = build_arg_parser()
	args = parser.parse_args(argv)

	sim_config = build_simulation_config(args)
	out_dir = Path(args.out)
	out_dir.mkdir(parents=True, exist_ok=True)
	source = _resolve_source(args)

	files: List[Path] = []
	if source == "csv":
		files = _collect_input_files(Path(args.input))

	backbones = [b.strip() for b in args.backbones.split(",") if b.strip()]

	if source == "csv":
		for f in files:
			data = evaluate_file(str(f), backbones, sim_config, args)
			plot_results(
				out_dir,
				str(f),
				data,
				show=args.show,
				plot_mode=args.evaluation_plot_mode,
				animate=args.evaluation_animate,
				animation_output=args.evaluation_animation_output,
				animation_fps=args.evaluation_animation_fps,
			)
			write_summary(out_dir, str(f), data)
	else:
		samples = build_source_iterator(source, sim_config, args)
		data = evaluate_samples(samples, backbones, sim_config, args)
		output_name = f"{source}-{Path(args.input).stem if args.input else source}"
		plot_results(
			out_dir,
			output_name,
			data,
			show=args.show,
			plot_mode=args.evaluation_plot_mode,
			animate=args.evaluation_animate,
			animation_output=args.evaluation_animation_output,
			animation_fps=args.evaluation_animation_fps,
		)
		write_summary(out_dir, output_name, data)


if __name__ == "__main__":
	main()