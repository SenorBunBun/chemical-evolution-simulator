"""Headless simulation runner — no pygame display, outputs metrics to CSV."""
from __future__ import annotations

import csv
import os

from src.config import GfxConfig, SimConfig
from src.id_gen import IdGen
from src.metrics import METRIC_FUNCTIONS
from src.physics import SpatialHash
from src.simulation import create_initial_state, step


def run_headless(sim_config: SimConfig, gfx_config: GfxConfig, quiet: bool = False) -> None:
    """Run the simulation headless, collecting the configured metrics to CSV.

    Columns are `tick` plus each name in `sim_config.headless_metrics`, resolved
    via metrics.METRIC_FUNCTIONS. Set quiet=True to suppress progress prints
    (useful when many runs execute in parallel).
    """
    max_ticks = sim_config.headless_max_ticks
    gather_tick = sim_config.headless_gather_tick
    csv_path = sim_config.headless_csv_path

    metric_names = list(sim_config.headless_metrics)
    unknown = [m for m in metric_names if m not in METRIC_FUNCTIONS]
    if unknown:
        raise ValueError(f"Unknown headless_metrics: {unknown}. "
                         f"Available: {sorted(METRIC_FUNCTIONS)}")
    metric_fns = [(m, METRIC_FUNCTIONS[m]) for m in metric_names]

    # Ensure output directory exists
    csv_dir = os.path.dirname(csv_path)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)

    id_gen = IdGen()
    state = create_initial_state(sim_config, gfx_config, id_gen)
    spatial_hash = SpatialHash(gfx_config.bond_length)

    if not quiet:
        print(f"Headless simulation: {len(state.blocks)} blocks, {max_ticks} ticks")
        print(f"  Gathering every {gather_tick} ticks -> {csv_path}")

    def sample_row():
        return [state.tick] + [f"{fn(state):.6f}" for _, fn in metric_fns]

    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["tick"] + metric_names)

            # Write tick-0 baseline
            writer.writerow(sample_row())

            for _ in range(max_ticks):
                step(state, spatial_hash, id_gen)

                if state.tick % gather_tick == 0:
                    writer.writerow(sample_row())
                    f.flush()

                if not quiet and state.tick % 10_000 == 0:
                    print(f"  tick {state.tick}/{max_ticks} ({state.tick * 100 / max_ticks:.1f}%)")

    except KeyboardInterrupt:
        print(f"\nInterrupted at tick {state.tick}. Partial data saved to {csv_path}")
        return

    if not quiet:
        total_rows = (max_ticks // gather_tick) + 1  # +1 for tick-0 baseline
        print(f"Done. {total_rows} data points written to {csv_path}")
