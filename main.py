"""Molecular Evolution Simulator - Entry Point.

Usage:
    python main.py                                          # Uses default configs
    python main.py configs/scenarios/two_molecules.json     # Scenario (overrides sim config)
    python main.py --gfx configs/graphics_default.json      # Custom graphics
    python main.py configs/simulation_default.json --verbose
"""
from __future__ import annotations

import logging
import os
import sys

import pygame

from src.config import load_gfx_config, load_sim_config
from src.id_gen import IdGen
from src.physics import SpatialHash
from src.renderer import Renderer
from src.simulation import create_initial_state, step

DEFAULT_SIM = "configs/simulation_default.json"
DEFAULT_GFX = "configs/graphics_default.json"


def main():
    # Parse CLI args
    sim_path = None
    gfx_path = None
    verbose = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--verbose":
            verbose = True
        elif args[i] == "--gfx" and i + 1 < len(args):
            i += 1
            gfx_path = args[i]
        elif not args[i].startswith("-"):
            sim_path = args[i]
        i += 1

    if gfx_path is None and os.path.exists(DEFAULT_GFX):
        gfx_path = DEFAULT_GFX

    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    # Load configs: scenarios overlay on top of defaults
    default_sim = DEFAULT_SIM if os.path.exists(DEFAULT_SIM) else None
    if sim_path is None:
        sim_config = load_sim_config(default_sim)
    elif default_sim and sim_path != default_sim:
        sim_config = load_sim_config(sim_path, base_path=default_sim)
    else:
        sim_config = load_sim_config(sim_path)
    gfx_config = load_gfx_config(gfx_path)

    id_gen = IdGen()
    state = create_initial_state(sim_config, gfx_config, id_gen)
    renderer = Renderer(sim_config, gfx_config)
    spatial_hash = SpatialHash(gfx_config.bond_length)
    clock = pygame.time.Clock()

    print(f"Simulation started: {len(state.blocks)} blocks")
    if sim_path:
        print(f"Sim config: {sim_path}")
    if gfx_path:
        print(f"Gfx config: {gfx_path}")
    print("Press SPACE to pause, D for debug, UP/DOWN for speed, ESC to quit")

    running = True
    while running:
        running = renderer.handle_events(state)

        if getattr(state, "_reset_requested", False):
            id_gen = IdGen()
            state = create_initial_state(sim_config, gfx_config, id_gen)
            spatial_hash = SpatialHash(gfx_config.bond_length)
            print("Simulation reset")
            continue

        if not state.paused or renderer.should_step:
            for _ in range(state.speed_multiplier):
                step(state, spatial_hash, id_gen)

        renderer.draw(state)
        clock.tick(gfx_config.target_fps)

    pygame.quit()


if __name__ == "__main__":
    main()
