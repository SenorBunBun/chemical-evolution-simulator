"""Headless simulation runner — no pygame display, outputs metrics to CSV."""
from __future__ import annotations

import csv
import os

from src.config import GfxConfig, SimConfig
from src.id_gen import IdGen
from src.metrics import avg_hydrolytic_resistance, pct_blocks_in_assemblies
from src.physics import SpatialHash
from src.simulation import create_initial_state, step


def run_headless(sim_config: SimConfig, gfx_config: GfxConfig) -> None:
    """Run the simulation headless, collecting metrics to CSV."""
    max_ticks = sim_config.headless_max_ticks
    gather_tick = sim_config.headless_gather_tick
    csv_path = sim_config.headless_csv_path

    # Ensure output directory exists
    csv_dir = os.path.dirname(csv_path)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)

    id_gen = IdGen()
    state = create_initial_state(sim_config, gfx_config, id_gen)
    spatial_hash = SpatialHash(gfx_config.bond_length)

    print(f"Headless simulation: {len(state.blocks)} blocks, {max_ticks} ticks")
    print(f"  Gathering every {gather_tick} ticks -> {csv_path}")

    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["tick", "avg_hydrolytic_resistance", "pct_blocks_in_assemblies"])

            # Write tick-0 baseline
            hr = avg_hydrolytic_resistance(state)
            pct = pct_blocks_in_assemblies(state)
            writer.writerow([state.tick, f"{hr:.6f}", f"{pct:.2f}"])

            for _ in range(max_ticks):
                step(state, spatial_hash, id_gen)

                if state.tick % gather_tick == 0:
                    hr = avg_hydrolytic_resistance(state)
                    pct = pct_blocks_in_assemblies(state)
                    writer.writerow([state.tick, f"{hr:.6f}", f"{pct:.2f}"])
                    f.flush()

                if state.tick % 10_000 == 0:
                    print(f"  tick {state.tick}/{max_ticks} ({state.tick * 100 / max_ticks:.1f}%)")

    except KeyboardInterrupt:
        print(f"\nInterrupted at tick {state.tick}. Partial data saved to {csv_path}")
        return

    total_rows = (max_ticks // gather_tick) + 1  # +1 for tick-0 baseline
    print(f"Done. {total_rows} data points written to {csv_path}")
