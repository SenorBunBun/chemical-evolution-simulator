"""Parallel multi-run orchestrator for headless simulation.

Spawns N independent headless processes, each writing to multirun/program{i}/.
Output from each process is printed as plain lines, prefixed with the run index.
Ctrl-C stops all processes cleanly.

Usage (via main.py):
    python main.py --headless --multirun --par 4
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


def run_parallel(n: int, base_args: list[str]) -> None:
    """Launch n headless processes in parallel, each in its own output folder.

    Args:
        n:         Number of parallel runs.
        base_args: Args to forward to each child process (already stripped of
                   --multirun / --par / --seq by the caller).
    """
    multirun_dir = Path("multirun")
    multirun_dir.mkdir(exist_ok=True)

    processes: list[subprocess.Popen] = []
    csv_paths: list[Path] = []

    for i in range(1, n + 1):
        run_dir = multirun_dir / f"program{i}"
        run_dir.mkdir(exist_ok=True)
        csv_path = run_dir / "headless_results.csv"
        csv_paths.append(csv_path)

        env = os.environ.copy()
        env["SIM_CSV_OVERRIDE"] = str(csv_path)
        env["SIM_RUN_INDEX"] = str(i)

        cmd = [sys.executable, "main.py", "--headless"] + base_args
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        processes.append(proc)

    print(f"Started {n} parallel run(s).")
    for i, csv_path in enumerate(csv_paths, 1):
        print(f"  run {i}: output -> {csv_path}")
    print("Press Ctrl-C to stop all runs.\n")

    # One thread per process: reads stdout lines and prints them with a prefix
    threads: list[threading.Thread] = []
    for i, proc in enumerate(processes, 1):
        t = threading.Thread(
            target=_stream_output,
            args=(proc, i),
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        # Block until all processes finish
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\nCtrl-C received — stopping all runs...")
        _terminate_all(processes)
        print("All processes stopped.")

    _print_final_summary(csv_paths)


def _stream_output(proc: subprocess.Popen, run_index: int) -> None:
    """Read lines from proc stdout and print them prefixed with [run N]."""
    prefix = f"[run {run_index}]"
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(f"{prefix} {line}", flush=True)
    except ValueError:
        # stdout closed early (e.g. process was killed)
        pass
    finally:
        proc.wait()
        print(f"{prefix} finished (exit code {proc.returncode})", flush=True)


def _terminate_all(processes: list[subprocess.Popen]) -> None:
    """Ask all running processes to terminate, then wait for them."""
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _print_final_summary(csv_paths: list[Path]) -> None:
    print("\nRun summary:")
    for i, csv_path in enumerate(csv_paths, 1):
        rows = _count_csv_rows(csv_path)
        exists = csv_path.exists()
        status = f"{rows} data rows" if exists else "no output file"
        print(f"  run {i}: {status} -> {csv_path}")


def _count_csv_rows(path: Path) -> int:
    """Count data rows in CSV (excluding header line)."""
    try:
        with open(path) as f:
            lines = sum(1 for line in f if line.strip())
        return max(0, lines - 1)  # subtract header
    except FileNotFoundError:
        return 0