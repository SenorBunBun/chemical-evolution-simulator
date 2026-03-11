from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimConfig:
    """Simulation parameters - physics, chemistry, sampling."""

    num_blocks: int = 50
    speed_scale: float = 2.0
    hydrolysis_interval: int = 60
    molec_mobility_penalty: float = 0.02
    history_interval: int = 30

    # Property sampling (normal distribution, clamped to [0,1])
    mobility_mean: float = 0.5
    mobility_std: float = 0.15
    formation_reactivity_mean: float = 0.5
    formation_reactivity_std: float = 0.15
    breaking_reactivity_mean: float = 0.25
    breaking_reactivity_std: float = 0.10
    latent_catalytic_mean: float = 0.5
    latent_catalytic_std: float = 0.20

    # Phase 2: Assembly
    base_assembly_chance: float = 0.3
    assembly_bond_resistance: float = 0.2
    assembly_mobility_penalty: float = 0.03
    assembly_growth_bonus: float = 0.1
    min_assembly_n: int = 5

    # Phase 3: Catalysis
    catalysis_chance: float = 0.1
    catalysis_range: float = 100.0
    catalysis_interval: int = 60
    generation_factor: float = 0.05
    reactivity_bonus_factor: float = 0.02
    catalysis_m_bonus: float = 0.1

    # Scenario mode
    scenario_blocks: Optional[list[dict]] = None
    scenario_molecules: Optional[list[dict]] = None


@dataclass
class GfxConfig:
    """Graphics/display parameters."""

    window_width: int = 1200
    window_height: int = 800
    target_fps: int = 60
    bg_color: list[int] = field(default_factory=lambda: [255, 255, 255])
    block_radius: float = 8.0
    bond_length: float = 16.0

    # Which block property to color by:
    #   "formation_reactivity", "mobility", "breaking_reactivity",
    #   "latent_catalytic_potential", "h_bond_type"
    block_color_by: str = "formation_reactivity"

    # Configurable block color scale: low value -> high value
    block_color_low: list[int] = field(default_factory=lambda: [0, 0, 255])    # blue (inert)
    block_color_high: list[int] = field(default_factory=lambda: [255, 0, 0])   # red (active)

    # Configurable bond color scale: strong (low break prob) -> fragile (high break prob)
    bond_color_strong: list[int] = field(default_factory=lambda: [0, 0, 0])        # black
    bond_color_fragile: list[int] = field(default_factory=lambda: [180, 180, 180]) # gray

    bond_width: int = 3
    block_outline: bool = True  # outline on blocks in molecules


def _load_json_filtered(cls, path: str) -> dict:
    """Load JSON and filter to only valid fields for the dataclass."""
    with open(path) as f:
        data = json.load(f)
    valid = {f.name for f in cls.__dataclass_fields__.values()}
    return {k: v for k, v in data.items() if k in valid}


def load_sim_config(path: Optional[str] = None, base_path: Optional[str] = None) -> SimConfig:
    """Load sim config. If base_path given, load defaults from it first, then overlay path on top."""
    if base_path is not None and path is not None:
        base = _load_json_filtered(SimConfig, base_path)
        overlay = _load_json_filtered(SimConfig, path)
        base.update(overlay)
        return SimConfig(**base)
    if path is not None:
        return SimConfig(**_load_json_filtered(SimConfig, path))
    return SimConfig()


def load_gfx_config(path: Optional[str] = None) -> GfxConfig:
    if path is not None:
        return GfxConfig(**_load_json_filtered(GfxConfig, path))
    return GfxConfig()
