"""Generate publication-ready plots from headless simulation CSV output.

Usage:
    python plot_results.py                          # Default: output/headless_results.csv
    python plot_results.py path/to/results.csv      # Custom CSV path
"""
from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Style constants ──────────────────────────────────────────────────────────
COLOR_RESISTANCE = "#2c7bb6"      # steel blue
COLOR_ASSEMBLY = "#d7191c"        # muted red
COLOR_SMOOTH = "#fdae61"          # warm amber for smoothed line
COLOR_SMOOTH_2 = "#abd9e9"        # light cyan for smoothed line
SMOOTH_WINDOW = 50                # rolling average window (in data points)

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})


def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["tick_k"] = df["tick"] / 1000  # thousands for x-axis scaling
    return df


def plot_hydrolytic_resistance(df: pd.DataFrame, out_dir: str):
    fig, ax = plt.subplots(figsize=(8, 4.5))

    ax.plot(df["tick"], df["avg_hydrolytic_resistance"],
            color=COLOR_RESISTANCE, linewidth=1.2)

    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Avg Hydrolytic Resistance")
    ax.set_title("Average Hydrolytic Resistance in Formed Molecules")
    ax.set_xlim(df["tick"].iloc[0], df["tick"].iloc[-1])

    path = os.path.join(out_dir, "hydrolytic_resistance.png")
    fig.savefig(path)
    path_pdf = os.path.join(out_dir, "hydrolytic_resistance.pdf")
    fig.savefig(path_pdf)
    plt.close(fig)
    print(f"  Saved: {path}  |  {path_pdf}")


def plot_assembly_percentage(df: pd.DataFrame, out_dir: str):
    fig, ax = plt.subplots(figsize=(8, 4.5))

    ax.plot(df["tick"], df["pct_blocks_in_assemblies"],
            color=COLOR_ASSEMBLY, linewidth=1.2)

    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Blocks in Assemblies (%)")
    ax.set_title("Percentage of Molecular Building Blocks in Assemblies")
    ax.set_xlim(df["tick"].iloc[0], df["tick"].iloc[-1])
    ax.set_ylim(bottom=0)

    path = os.path.join(out_dir, "assembly_percentage.png")
    fig.savefig(path)
    path_pdf = os.path.join(out_dir, "assembly_percentage.pdf")
    fig.savefig(path_pdf)
    plt.close(fig)
    print(f"  Saved: {path}  |  {path_pdf}")


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "output/headless_results.csv"
    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at {csv_path}")
        sys.exit(1)

    # Optional tick range: --range MIN MAX (in ticks)
    tick_min = None
    tick_max = None
    args = sys.argv[1:]
    for j, arg in enumerate(args):
        if arg == "--range" and j + 2 < len(args):
            tick_min = int(args[j + 1])
            tick_max = int(args[j + 2])

    df = load_data(csv_path)

    if tick_min is not None and tick_max is not None:
        df = df[(df["tick"] >= tick_min) & (df["tick"] <= tick_max)]
        print(f"Filtered to tick range {tick_min} - {tick_max}")

    out_dir = os.path.dirname(csv_path) or "output"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Plotting {len(df)} data points from {csv_path}")
    plot_hydrolytic_resistance(df, out_dir)
    plot_assembly_percentage(df, out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
