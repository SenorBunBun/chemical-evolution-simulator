"""Generate plots and summary CSV from a multirun output directory.

Expects the structure produced by --multirun --par N:
    multirun/
        program1/headless_results.csv
        program2/headless_results.csv
        ...

Produces:
    multirun/program{i}/hydrolytic_resistance.png  (.pdf)
    multirun/program{i}/assembly_percentage.png    (.pdf)
    multirun/summary/summary.csv
    multirun/summary/hydrolytic_resistance.png     (.pdf)
    multirun/summary/assembly_percentage.png       (.pdf)

Usage:
    python plot_multirun_results.py                     # default: multirun/
    python plot_multirun_results.py path/to/multirun/   # custom multirun dir
"""
from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

# ── Style (mirrors plot_results.py) ─────────────────────────────────────────
COLOR_RESISTANCE = "#2c7bb6"
COLOR_ASSEMBLY   = "#d7191c"
COLOR_MEAN       = "#1a1a1a"       # near-black for mean line on summary plots
COLOR_BAND       = "#aec6e8"       # light blue shading for std-dev band

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

CSV_FILENAME = "headless_results.csv"
SUMMARY_DIR  = "summary"
SUMMARY_CSV  = "summary.csv"


# ── Data loading ─────────────────────────────────────────────────────────────

def find_program_dirs(multirun_dir: str) -> list[str]:
    """Return sorted list of program{i} subdirectory paths that contain a CSV."""
    dirs = []
    for name in sorted(os.listdir(multirun_dir)):
        if not name.startswith("program"):
            continue
        full = os.path.join(multirun_dir, name)
        csv  = os.path.join(full, CSV_FILENAME)
        if os.path.isdir(full) and os.path.isfile(csv):
            dirs.append(full)
    return dirs


def load_csv(directory: str) -> pd.DataFrame:
    path = os.path.join(directory, CSV_FILENAME)
    df = pd.read_csv(path)
    return df


# ── Per-program plots (same style as plot_results.py) ────────────────────────

def plot_hydrolytic_resistance(df: pd.DataFrame, out_dir: str, title_suffix: str = ""):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(df["tick"], df["avg_hydrolytic_resistance"],
            color=COLOR_RESISTANCE, linewidth=1.2)
    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Avg Hydrolytic Resistance")
    ax.set_title(f"Average Hydrolytic Resistance in Formed Molecules{title_suffix}")
    ax.set_xlim(df["tick"].iloc[0], df["tick"].iloc[-1])

    _save(fig, out_dir, "hydrolytic_resistance")


def plot_assembly_percentage(df: pd.DataFrame, out_dir: str, title_suffix: str = ""):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(df["tick"], df["pct_blocks_in_assemblies"],
            color=COLOR_ASSEMBLY, linewidth=1.2)
    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Blocks in Assemblies (%)")
    ax.set_title(f"Percentage of Molecular Building Blocks in Assemblies{title_suffix}")
    ax.set_xlim(df["tick"].iloc[0], df["tick"].iloc[-1])
    ax.set_ylim(bottom=0)

    _save(fig, out_dir, "assembly_percentage")


# ── Summary CSV ───────────────────────────────────────────────────────────────

def build_summary(dataframes: list[pd.DataFrame]) -> pd.DataFrame:
    """Average all run DataFrames tick-by-tick.

    Uses the intersection of tick values present in ALL runs so the
    average is only computed where every run has data.
    """
    # Find common tick values across all runs
    common_ticks = set(dataframes[0]["tick"].tolist())
    for df in dataframes[1:]:
        common_ticks &= set(df["tick"].tolist())
    common_ticks = sorted(common_ticks)

    if not common_ticks:
        raise ValueError(
            "No common tick values found across runs. "
            "Ensure all runs used the same headless_gather_tick setting."
        )

    # Filter each df to common ticks only
    filtered = [
        df[df["tick"].isin(common_ticks)].set_index("tick")
        for df in dataframes
    ]

    numeric_cols = [
        c for c in filtered[0].columns
        if c != "tick" and pd.api.types.is_numeric_dtype(filtered[0][c])
    ]

    rows = []
    for tick in common_ticks:
        row = {"tick": tick}
        for col in numeric_cols:
            values = [f.loc[tick, col] for f in filtered if tick in f.index]
            row[f"avg_{col}"] = sum(values) / len(values)
            row[f"std_{col}"] = pd.Series(values).std(ddof=1) if len(values) > 1 else 0.0
            row[f"min_{col}"] = min(values)
            row[f"max_{col}"] = max(values)
        rows.append(row)

    return pd.DataFrame(rows)


# ── Summary plots (mean ± std shading) ───────────────────────────────────────

def plot_summary_resistance(summary: pd.DataFrame, out_dir: str, n_runs: int):
    col = "avg_hydrolytic_resistance"
    std = "std_avg_hydrolytic_resistance"

    # Gracefully handle CSVs that may have or lack the std column
    mean_col = f"avg_{col}" if f"avg_{col}" in summary.columns else col
    std_col  = std if std in summary.columns else None

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if std_col is not None:
        ax.fill_between(
            summary["tick"],
            summary[mean_col] - summary[std_col],
            summary[mean_col] + summary[std_col],
            color=COLOR_BAND, alpha=0.5, label="±1 std dev",
        )

    ax.plot(summary["tick"], summary[mean_col],
            color=COLOR_MEAN, linewidth=1.5, label=f"Mean (n={n_runs})")

    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Avg Hydrolytic Resistance")
    ax.set_title(f"Hydrolytic Resistance — Summary across {n_runs} runs")
    ax.set_xlim(summary["tick"].iloc[0], summary["tick"].iloc[-1])
    ax.legend(frameon=False)

    _save(fig, out_dir, "hydrolytic_resistance")


def plot_summary_assembly(summary: pd.DataFrame, out_dir: str, n_runs: int):
    col = "pct_blocks_in_assemblies"
    std = "std_pct_blocks_in_assemblies"

    mean_col = f"avg_{col}" if f"avg_{col}" in summary.columns else col
    std_col  = std if std in summary.columns else None

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if std_col is not None:
        lower = (summary[mean_col] - summary[std_col]).clip(lower=0)
        upper = summary[mean_col] + summary[std_col]
        ax.fill_between(
            summary["tick"], lower, upper,
            color=COLOR_BAND, alpha=0.5, label="±1 std dev",
        )

    ax.plot(summary["tick"], summary[mean_col],
            color=COLOR_MEAN, linewidth=1.5, label=f"Mean (n={n_runs})")

    ax.set_xlabel("Simulation Time (ticks)")
    ax.set_ylabel("Blocks in Assemblies (%)")
    ax.set_title(f"Assembly Percentage — Summary across {n_runs} runs")
    ax.set_xlim(summary["tick"].iloc[0], summary["tick"].iloc[-1])
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)

    _save(fig, out_dir, "assembly_percentage")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save(fig, out_dir: str, stem: str):
    os.makedirs(out_dir, exist_ok=True)
    for ext in ("png", "pdf"):
        path = os.path.join(out_dir, f"{stem}.{ext}")
        fig.savefig(path)
        print(f"  Saved: {path}")
    plt.close(fig)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    multirun_dir = sys.argv[1] if len(sys.argv) > 1 else "multirun"

    if not os.path.isdir(multirun_dir):
        print(f"Error: directory not found: {multirun_dir}")
        sys.exit(1)

    program_dirs = find_program_dirs(multirun_dir)
    if not program_dirs:
        print(f"Error: no program{{N}}/headless_results.csv files found in {multirun_dir}")
        sys.exit(1)

    print(f"Found {len(program_dirs)} run(s) in {multirun_dir}\n")

    # ── Per-program plots ────────────────────────────────────────────────────
    dataframes: list[pd.DataFrame] = []
    for prog_dir in program_dirs:
        name = os.path.basename(prog_dir)
        print(f"Plotting {name}...")
        df = load_csv(prog_dir)
        dataframes.append(df)
        suffix = f" — {name}"
        plot_hydrolytic_resistance(df, prog_dir, title_suffix=suffix)
        plot_assembly_percentage(df, prog_dir, title_suffix=suffix)

    # ── Summary CSV ──────────────────────────────────────────────────────────
    print(f"\nBuilding summary from {len(dataframes)} run(s)...")
    summary_dir = os.path.join(multirun_dir, SUMMARY_DIR)
    os.makedirs(summary_dir, exist_ok=True)

    try:
        summary = build_summary(dataframes)
    except ValueError as e:
        print(f"Error building summary: {e}")
        sys.exit(1)

    summary_csv_path = os.path.join(summary_dir, SUMMARY_CSV)
    summary.to_csv(summary_csv_path, index=False)
    print(f"  Saved: {summary_csv_path}  ({len(summary)} rows, {len(dataframes)} runs averaged)")

    # ── Summary plots ────────────────────────────────────────────────────────
    print(f"\nPlotting summary...")
    plot_summary_resistance(summary, summary_dir, n_runs=len(dataframes))
    plot_summary_assembly(summary, summary_dir, n_runs=len(dataframes))

    print("\nDone.")


if __name__ == "__main__":
    main()