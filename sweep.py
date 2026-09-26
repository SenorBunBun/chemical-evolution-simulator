"""Parallel parameter sweep over formation/breaking reactivity and hydrolysis interval.

Each combo is one headless run (common seed) writing its own time-series CSV. A
master index links to every run; `annotate_master` then computes a complexity
score per combo from the last-N-ticks average.

Usage:
    python sweep.py smoke              # tiny 8-combo grid @ 5k ticks (pipeline test)
    python sweep.py full               # full 343-combo grid @ TICKS
    python sweep.py annotate <dir>     # (re)compute annotated_master.csv for a dir
    python sweep.py full --out output/my_sweep --ticks 150000
"""
from __future__ import annotations

import os

# Must be set before pygame is imported (survives macOS 'spawn' re-import).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import argparse
import csv
import multiprocessing as mp
import random
import time

# --- Editable configuration ---------------------------------------------------
RUN_OUTPUT_DIR = "output/param_sweep_1"   # output folder for a full run
NUM_WORKERS = 7
SEED = 12345                            # common seed => identical initialization per combo
TICKS = 150_000
GATHER_TICK = 100
AVG_WINDOW_TICKS = 30_000               # complexity score averages the last this-many ticks
WEIGHT_FLOOR = 1.0                      # the "+1" in the score formula (tunable)
ASSEMBLY_WEIGHT = 0.7                   # new_score down-weights assembly% so catalysis% matters more
MAX_ATTEMPTS = 2                        # a failed run is retried up to this many times

FORMATION = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
BREAKING = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
HYDROLYSIS = [30, 60, 90, 120, 150, 200, 250]

SWEEP_METRICS = [
    "pct_blocks_in_assemblies",
    "pct_blocks_in_catalytic_assemblies",
    "avg_molecule_size_formed",
    "avg_hydrolytic_resistance",
]

# Fixed (unchanging) overrides applied on top of configs/simulation_default.json
FIXED = {
    "base_assembly_chance": 1.0,
    "assembly_bond_resistance": 0.4,
    "mobility_mean": 0.6,
    "mobility_std": 0.25,
    "h_bond_type_weights": [1.0, 1.0, 1.0],
    "formation_reactivity_std": 0.25,
    "breaking_reactivity_std": 0.25,
    "num_blocks": 500,
    # catalysis params left at simulation_default.json values
}

DEFAULT_SIM = "configs/simulation_default.json"
DEFAULT_GFX = "configs/graphics_default.json"

MASTER_COLUMNS = [
    "formation_reactivity_mean", "breaking_reactivity_mean", "hydrolysis_interval",
    "seed", "ticks", "status", "csv_path", "error",
]


def _run_csv_path(runs_dir: str, f: float, b: float, h: int) -> str:
    return os.path.join(runs_dir, f"f{f:.2f}_b{b:.2f}_h{h}.csv")


def _run_complete(csv_path: str, expected_final_tick: int) -> bool:
    """True if a per-run CSV already exists and reached the expected final tick."""
    if not os.path.exists(csv_path):
        return False
    try:
        with open(csv_path) as fh:
            last = None
            for last in csv.reader(fh):
                pass
        return last is not None and int(last[0]) >= expected_final_tick
    except (ValueError, IndexError, OSError):
        return False


def run_one(task: dict) -> dict:
    """Worker: run a single combo to completion, writing its own CSV. Never raises."""
    f, b, h = task["formation"], task["breaking"], task["hydrolysis"]
    csv_path = task["csv_path"]
    result = {
        "formation_reactivity_mean": f, "breaking_reactivity_mean": b,
        "hydrolysis_interval": h, "seed": task["seed"], "ticks": task["ticks"],
        "csv_path": csv_path, "status": "OK", "error": "",
    }
    if task["resume"] and _run_complete(csv_path, task["ticks"]):
        result["status"] = "SKIPPED"
        return result
    try:
        # Import inside the worker so spawn picks up the dummy SDL driver cleanly.
        from src.config import load_sim_config, load_gfx_config
        from src.headless import run_headless

        random.seed(task["seed"])
        sim = load_sim_config(DEFAULT_SIM)
        gfx = load_gfx_config(DEFAULT_GFX)
        for k, v in FIXED.items():
            setattr(sim, k, v)
        sim.formation_reactivity_mean = f
        sim.breaking_reactivity_mean = b
        sim.hydrolysis_interval = h
        sim.headless_metrics = list(SWEEP_METRICS)
        sim.headless_max_ticks = task["ticks"]
        sim.headless_gather_tick = task["gather"]
        sim.headless_csv_path = csv_path
        run_headless(sim, gfx, quiet=True)
    except Exception as exc:  # noqa: BLE001 - one bad run must not doom the sweep
        result["status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _build_tasks(formation, breaking, hydrolysis, runs_dir, ticks, gather, resume):
    tasks = []
    for f in formation:
        for b in breaking:
            for h in hydrolysis:
                tasks.append({
                    "formation": f, "breaking": b, "hydrolysis": h,
                    "seed": SEED, "ticks": ticks, "gather": gather,
                    "csv_path": _run_csv_path(runs_dir, f, b, h), "resume": resume,
                })
    return tasks


def _append_master(master_path: str, row: dict, write_header: bool):
    mode = "w" if write_header else "a"
    with open(master_path, mode, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MASTER_COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in MASTER_COLUMNS})


def run_sweep(out_dir, formation, breaking, hydrolysis, ticks, gather, resume):
    runs_dir = os.path.join(out_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    master_path = os.path.join(out_dir, "master_sweep.csv")

    tasks = _build_tasks(formation, breaking, hydrolysis, runs_dir, ticks, gather, resume)
    total = len(tasks)
    print(f"Sweep: {total} combos, {ticks} ticks each, {NUM_WORKERS} workers -> {out_dir}")

    with open(master_path, "w", newline="") as fh:  # fresh master with header only
        csv.DictWriter(fh, fieldnames=MASTER_COLUMNS).writeheader()

    done = 0
    failed = []
    t0 = time.perf_counter()
    with mp.Pool(NUM_WORKERS) as pool:
        for res in pool.imap_unordered(run_one, tasks, chunksize=1):
            done += 1
            _append_master(master_path, res, write_header=False)
            if res["status"] == "FAILED":
                failed.append(res)
            elapsed = time.perf_counter() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"[{done}/{total}] {res['status']:7s} "
                  f"f={res['formation_reactivity_mean']} b={res['breaking_reactivity_mean']} "
                  f"h={res['hydrolysis_interval']}  elapsed={elapsed/60:.1f}m eta={eta/60:.1f}m")

    # Retry failed combos (fresh attempts), overwriting their master rows on success.
    attempt = 1
    while failed and attempt < MAX_ATTEMPTS:
        attempt += 1
        retry = [t for t in tasks if any(
            t["csv_path"] == r["csv_path"] for r in failed)]
        for t in retry:
            t["resume"] = False
        print(f"Retry attempt {attempt}: {len(retry)} failed combo(s)")
        failed = []
        with mp.Pool(NUM_WORKERS) as pool:
            for res in pool.imap_unordered(run_one, retry, chunksize=1):
                _append_master(master_path, res, write_header=False)
                if res["status"] == "FAILED":
                    failed.append(res)
                print(f"  retry {res['status']:7s} f={res['formation_reactivity_mean']} "
                      f"b={res['breaking_reactivity_mean']} h={res['hydrolysis_interval']}")

    print(f"Sweep done in {(time.perf_counter()-t0)/60:.1f} min. "
          f"{len(failed)} still failed.")
    if failed:
        print("  STILL FAILED:", [(r['formation_reactivity_mean'],
                                    r['breaking_reactivity_mean'],
                                    r['hydrolysis_interval']) for r in failed])
    return master_path


def _window_mean(rows, col_idx, header, window_ticks):
    """Mean of a column over rows whose tick >= max_tick - window_ticks."""
    if not rows:
        return 0.0
    max_tick = int(rows[-1][0])
    lo = max_tick - window_ticks
    vals = [float(r[col_idx]) for r in rows if int(r[0]) >= lo]
    return sum(vals) / len(vals) if vals else 0.0


def annotate_master(out_dir, window_ticks=AVG_WINDOW_TICKS, floor=WEIGHT_FLOOR):
    """Compute the complexity score per combo into annotated_master.csv."""
    master_path = os.path.join(out_dir, "master_sweep.csv")
    annotated_path = os.path.join(out_dir, "annotated_master.csv")

    with open(master_path) as fh:
        master_rows = list(csv.DictReader(fh))

    out_rows = []
    for m in master_rows:
        if m["status"] not in ("OK", "SKIPPED"):
            continue
        path = m["csv_path"]
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            reader = csv.reader(fh)
            header = next(reader)
            rows = [r for r in reader if r]
        idx = {name: i for i, name in enumerate(header)}
        mean_asm = _window_mean(rows, idx["pct_blocks_in_assemblies"], header, window_ticks)
        mean_cat = _window_mean(rows, idx["pct_blocks_in_catalytic_assemblies"], header, window_ticks)
        mean_n = _window_mean(rows, idx["avg_molecule_size_formed"], header, window_ticks)
        score = (mean_asm + mean_cat + floor) * mean_n
        new_score = (ASSEMBLY_WEIGHT * mean_asm + mean_cat + floor) * mean_n
        out_rows.append({
            "formation_reactivity_mean": float(m["formation_reactivity_mean"]),
            "breaking_reactivity_mean": float(m["breaking_reactivity_mean"]),
            "hydrolysis_interval": int(m["hydrolysis_interval"]),
            "mean_pct_in_assemblies": round(mean_asm, 4),
            "mean_pct_in_catalysts": round(mean_cat, 4),
            "mean_avg_n": round(mean_n, 4),
            "complexity_score": round(score, 4),
            "new_score": round(new_score, 4),
            "csv_path": path,
        })

    out_rows.sort(key=lambda r: r["complexity_score"], reverse=True)
    cols = ["formation_reactivity_mean", "breaking_reactivity_mean", "hydrolysis_interval",
            "mean_pct_in_assemblies", "mean_pct_in_catalysts", "mean_avg_n",
            "complexity_score", "new_score", "csv_path"]
    with open(annotated_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Annotated {len(out_rows)} combos -> {annotated_path}")
    if out_rows:
        print("Top 5 by complexity_score:")
        for r in out_rows[:5]:
            print(f"  score={r['complexity_score']:.2f}  f={r['formation_reactivity_mean']} "
                  f"b={r['breaking_reactivity_mean']} h={r['hydrolysis_interval']}  "
                  f"asm%={r['mean_pct_in_assemblies']:.2f} cat%={r['mean_pct_in_catalysts']:.2f} "
                  f"n={r['mean_avg_n']:.2f}")
    return annotated_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "full", "annotate"])
    ap.add_argument("dir", nargs="?", default=None, help="dir for annotate mode")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ticks", type=int, default=None)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    if args.mode == "annotate":
        annotate_master(args.dir or args.out or RUN_OUTPUT_DIR)
        return

    if args.mode == "smoke":
        out = args.out or "output/sweep_smoke"
        ticks = args.ticks or 5_000
        formation, breaking, hydrolysis = [0.2, 0.8], [0.2, 0.8], [30, 250]
    else:  # full
        out = args.out or RUN_OUTPUT_DIR
        ticks = args.ticks or TICKS
        formation, breaking, hydrolysis = FORMATION, BREAKING, HYDROLYSIS

    run_sweep(out, formation, breaking, hydrolysis, ticks, GATHER_TICK,
              resume=not args.no_resume)
    annotate_master(out, window_ticks=min(AVG_WINDOW_TICKS, ticks))


if __name__ == "__main__":
    main()
