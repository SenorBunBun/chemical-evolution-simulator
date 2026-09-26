"""Plot parameter-sweep results as a grid of heatmaps.

Reads a sweep output directory's annotated_master.csv and draws one heatmap per
hydrolysis interval, with formation_reactivity_mean on the x-axis and
breaking_reactivity_mean on the y-axis, colored by complexity_score. All panels
share a common color scale so they are directly comparable.

Usage:
    python plot_sweep.py                         # default: output/param_sweep_1
    python plot_sweep.py output/param_sweep_1    # explicit sweep dir
    python plot_sweep.py path/to/annotated_master.csv
    python plot_sweep.py output/param_sweep_1 --metric mean_pct_in_assemblies
"""
from __future__ import annotations

import argparse
import csv
import math
import os

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
})


PRETTY_LABELS = {
    "complexity_score": "Complexity Score",
    "new_score": "New Score",
    "mean_pct_in_assemblies": "Mean % in Assemblies",
    "mean_pct_in_catalysts": "Mean % in Catalysts",
    "mean_avg_n": "Mean Molecule Size",
    "formation_reactivity_mean": "Formation Reactivity (mean)",
    "breaking_reactivity_mean": "Breaking Reactivity (mean)",
    "hydrolysis_interval": "Hydrolysis Interval",
}


def _pretty(name: str) -> str:
    """Human-readable label for a metric/column name."""
    return PRETTY_LABELS.get(name, name.replace("_", " ").title())


def _resolve_csv(target: str) -> str:
    """Accept either a sweep dir or a direct CSV path."""
    if os.path.isdir(target):
        return os.path.join(target, "annotated_master.csv")
    return target


def load_rows(csv_path: str) -> list[dict]:
    with open(csv_path) as fh:
        return list(csv.DictReader(fh))


def build_grid(rows, metric, hydro, x_vals, y_vals):
    """2D array [len(y_vals) x len(x_vals)] of `metric` for one hydrolysis interval."""
    xi = {v: i for i, v in enumerate(x_vals)}
    yi = {v: i for i, v in enumerate(y_vals)}
    grid = np.full((len(y_vals), len(x_vals)), np.nan)
    for r in rows:
        if int(r["hydrolysis_interval"]) != hydro:
            continue
        f = float(r["formation_reactivity_mean"])
        b = float(r["breaking_reactivity_mean"])
        if f in xi and b in yi:
            grid[yi[b], xi[f]] = float(r[metric])
    return grid


def plot_heatmaps(csv_path: str, metric: str = "complexity_score"):
    rows = load_rows(csv_path)
    if not rows:
        print(f"No rows in {csv_path}")
        return

    x_vals = sorted({float(r["formation_reactivity_mean"]) for r in rows})
    y_vals = sorted({float(r["breaking_reactivity_mean"]) for r in rows})
    hydros = sorted({int(r["hydrolysis_interval"]) for r in rows})

    # Shared color scale across all panels for comparability.
    all_vals = [float(r[metric]) for r in rows if r.get(metric) not in (None, "")]
    vmin, vmax = (min(all_vals), max(all_vals)) if all_vals else (0.0, 1.0)

    n = len(hydros)
    ncols = min(n, math.ceil(math.sqrt(n)))
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.8 * nrows),
                             squeeze=False)

    im = None
    for k, hydro in enumerate(hydros):
        ax = axes[k // ncols][k % ncols]
        grid = build_grid(rows, metric, hydro, x_vals, y_vals)
        im = ax.imshow(grid, origin="lower", aspect="auto", cmap="viridis",
                       vmin=vmin, vmax=vmax)
        ax.set_title(f"hydrolysis = {hydro}")
        ax.set_xticks(range(len(x_vals)), [f"{v:g}" for v in x_vals])
        ax.set_yticks(range(len(y_vals)), [f"{v:g}" for v in y_vals])
        ax.set_xlabel("formation_reactivity_mean")
        ax.set_ylabel("breaking_reactivity_mean")
        # annotate each cell with its value
        for iy in range(len(y_vals)):
            for ix in range(len(x_vals)):
                val = grid[iy, ix]
                if not np.isnan(val):
                    # white text on dark cells, black on light
                    frac = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.5
                    ax.text(ix, iy, f"{val:.1f}", ha="center", va="center",
                            fontsize=7, color="white" if frac < 0.6 else "black")

    # hide any unused panels
    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")

    if im is not None:
        cbar = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
        cbar.set_label(metric)

    fig.suptitle(f"{metric} by formation × breaking, per hydrolysis interval",
                 fontsize=14, fontweight="bold")

    out_dir = os.path.dirname(csv_path) or "output"
    stem = os.path.join(out_dir, f"heatmap_{metric}")
    fig.savefig(f"{stem}.png", bbox_inches="tight")
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {stem}.png  |  {stem}.pdf")


def plot_heatmap_avg(csv_path: str, metric: str = "complexity_score"):
    """Single heatmap: each (formation, breaking) cell averaged over all hydrolysis intervals."""
    rows = load_rows(csv_path)
    if not rows:
        print(f"No rows in {csv_path}")
        return

    x_vals = sorted({float(r["formation_reactivity_mean"]) for r in rows})
    y_vals = sorted({float(r["breaking_reactivity_mean"]) for r in rows})
    xi = {v: i for i, v in enumerate(x_vals)}
    yi = {v: i for i, v in enumerate(y_vals)}

    # accumulate mean per (formation, breaking) across all hydrolysis intervals
    sums = np.zeros((len(y_vals), len(x_vals)))
    counts = np.zeros((len(y_vals), len(x_vals)))
    for r in rows:
        if r.get(metric) in (None, ""):
            continue
        f = float(r["formation_reactivity_mean"])
        b = float(r["breaking_reactivity_mean"])
        if f in xi and b in yi:
            sums[yi[b], xi[f]] += float(r[metric])
            counts[yi[b], xi[f]] += 1
    grid = np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts > 0)

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    finite = grid[~np.isnan(grid)]
    vmin, vmax = (finite.min(), finite.max()) if finite.size else (0.0, 1.0)
    im = ax.imshow(grid, origin="lower", aspect="auto", cmap="viridis",
                   vmin=vmin, vmax=vmax)
    ax.set_title(f"{_pretty(metric)} Averaged Across Hydrolysis Intervals",
                 fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(x_vals)), [f"{v:g}" for v in x_vals])
    ax.set_yticks(range(len(y_vals)), [f"{v:g}" for v in y_vals])
    ax.set_xlabel(_pretty("formation_reactivity_mean"))
    ax.set_ylabel(_pretty("breaking_reactivity_mean"))
    for iy in range(len(y_vals)):
        for ix in range(len(x_vals)):
            val = grid[iy, ix]
            if not np.isnan(val):
                frac = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.5
                ax.text(ix, iy, f"{val:.1f}", ha="center", va="center",
                        fontsize=8, color="white" if frac < 0.6 else "black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(f"Mean {_pretty(metric)}")

    out_dir = os.path.dirname(csv_path) or "output"
    stem = os.path.join(out_dir, f"heatmap_avg_{metric}")
    fig.savefig(f"{stem}.png", bbox_inches="tight")
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {stem}.png  |  {stem}.pdf")


def plot_scatter3d(csv_path: str, metric: str = "complexity_score", show: bool = False):
    """3D scatter: formation (x), breaking (y), hydrolysis (z), colored by metric."""
    rows = load_rows(csv_path)
    vals = [(float(r["formation_reactivity_mean"]),
             float(r["breaking_reactivity_mean"]),
             float(r["hydrolysis_interval"]),
             float(r[metric])) for r in rows if r.get(metric) not in (None, "")]
    if not vals:
        print(f"No rows in {csv_path}")
        return

    xs, ys, zs, cs = (np.array(v) for v in zip(*vals))

    fig = plt.figure(figsize=(9, 7.5))
    ax = fig.add_subplot(111, projection="3d")
    p = ax.scatter(xs, ys, zs, c=cs, cmap="viridis", s=60,
                   depthshade=False, edgecolors="k", linewidths=0.3)
    ax.set_xlabel("formation_reactivity_mean", labelpad=10)
    ax.set_ylabel("breaking_reactivity_mean", labelpad=10)
    ax.set_zlabel("hydrolysis_interval", labelpad=10)
    ax.set_title(f"{metric} across the parameter space", fontsize=14, fontweight="bold")
    cbar = fig.colorbar(p, ax=ax, fraction=0.03, pad=0.1)
    cbar.set_label(metric)

    out_dir = os.path.dirname(csv_path) or "output"
    stem = os.path.join(out_dir, f"scatter3d_{metric}")
    fig.savefig(f"{stem}.png", bbox_inches="tight")
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    print(f"Saved: {stem}.png  |  {stem}.pdf")
    if show:
        print("Opening interactive 3D window (rotate/zoom with the mouse; close it to exit)...")
        plt.show()
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default="output/param_sweep_1",
                    help="sweep dir or annotated_master.csv path")
    ap.add_argument("--metric", default="complexity_score",
                    help="column to color by (e.g. complexity_score, "
                         "mean_pct_in_assemblies, mean_avg_n)")
    ap.add_argument("--show", action="store_true",
                    help="open the 3D scatter in an interactive window (still saves files)")
    args = ap.parse_args()

    csv_path = _resolve_csv(args.target)
    if not os.path.exists(csv_path):
        print(f"Error: annotated CSV not found at {csv_path}\n"
              f"Run the sweep first, or point me at the right dir.")
        raise SystemExit(1)

    plot_heatmaps(csv_path, args.metric)
    plot_heatmap_avg(csv_path, args.metric)
    plot_scatter3d(csv_path, args.metric, show=args.show)


if __name__ == "__main__":
    main()
