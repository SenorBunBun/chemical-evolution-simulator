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
    assembly_enabled: bool = True
    base_assembly_chance: float = 0.3
    assembly_bond_resistance: float = 0.2
    assembly_mobility_penalty: float = 0.03
    assembly_growth_bonus: float = 0.1
    min_assembly_n: int = 5

    # Phase 3: Catalysis
    base_catalysis_chance: float = 0.1
    catalysis_range: float = 100.0
    catalysis_interval: int = 60
    base_generation_chance: float = 0.05
    base_reactivity_bonus: float = 0.02
    catalysis_m_bonus: float = 1.0

    # Headless mode
    headless: bool = False
    headless_max_ticks: int = 250_000
    headless_gather_tick: int = 100
    headless_csv_path: str = "output/headless_results.csv"

    # Scenario mode
    scenario_blocks: Optional[list[dict]] = None
    scenario_molecules: Optional[list[dict]] = None
    scenario_assemblies: Optional[list[dict]] = None


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
    h_bond_width: int = 1
    block_outline: bool = True  # outline on blocks in molecules

    # Soft glow drawn between H-bonded pieces instead of a hard line, since
    # the donor/acceptor shapes already show the connection.
    h_bond_glow_color: list[int] = field(default_factory=lambda: [50, 120, 255])  # blue
    h_bond_glow_radius: int = 4
    h_bond_glow_alpha: int = 55
    h_bond_glow_samples: int = 6

    # Optional illustrated background image, scaled to fill the window.
    # Falls back to bg_color if the path is None or the file is missing.
    background_image: Optional[str] = None

    # Animation played briefly at the spot a bond breaks. The image is
    # scaled up and faded out over break_anim_duration ticks.
    break_anim_image: Optional[str] = None
    break_anim_duration: int = 20
    break_anim_size: int = 24
    break_anim_max_scale: float = 3.0
    break_anim_max_alpha: int = 255  # cap peak opacity for a more subtle effect
    # Optional duotone recolor (dark strokes -> muted tint, light areas ->
    # bright tint) so a break reads as a distinct "warning" cue, separate
    # from the blue H-bond glow. Baked in once at load time.
    break_anim_tint: Optional[list[int]] = None

    # Animation played briefly at the spot a new bond forms (covalent or
    # H-bond), scaled up and faded out over form_anim_duration ticks.
    form_anim_image: Optional[str] = None
    form_anim_duration: int = 20
    form_anim_size: int = 24
    form_anim_max_scale: float = 3.0
    form_anim_max_alpha: int = 255
    form_anim_tint: Optional[list[int]] = None



    # Illustrated donor/acceptor blocks (used only when block_color_by == "h_bond_type").
    # Falls back to the procedural circle if disabled or a file is missing.
    use_illustrated_blocks: bool = False
    donor_image: Optional[str] = None
    acceptor_image: Optional[str] = None

    # Alternate donor/acceptor art used once a block belongs to an assembly.
    # Falls back to donor_image/acceptor_image if unset or missing.
    donor_assembly_image: Optional[str] = None
    acceptor_assembly_image: Optional[str] = None

    # Fixed rotation (degrees) applied to each sprite so its knobs/notches
    # line up with the vertical H-bond axis (assemblies only ever stack
    # vertically -- rigid bodies translate but never rotate).
    donor_rotation: float = 0.0
    acceptor_rotation: float = 90.0

    # How much larger to draw a block's sprite when it currently has an
    # H-bond, so its knob visually overlaps into its partner's notch.
    hbond_overlap_scale: float = 1.4

    # Same idea, but for blocks belonging to an assembly -- the assembly
    # art already has a built-in connection ring, so it needs less (or no)
    # extra enlargement to still read as overlapping.
    assembly_overlap_scale: float = 1.4

    # Visual-only enlargement of free (not H-bonded, not in an assembly)
    # donor/acceptor sprites, purely to reduce the size gap against the
    # (necessarily larger) assembly/overlap variants -- doesn't touch
    # block_radius, so physics/collision are unaffected.
    donor_acceptor_scale: float = 1.2

    # Phase 3: Catalysis rendering
    catalysis_range_color: list[int] = field(default_factory=lambda: [0, 200, 0])  # green
    catalysis_range_alpha: int = 30  # transparency for range circle fill
    # Visual-only scale on the drawn catalytic halo, independent of the
    # actual sim_config.catalysis_range that affects gameplay.
    catalysis_zone_visual_scale: float = 0.6


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
