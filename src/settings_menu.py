"""Pre-game settings screen built with pygame_menu.

Lets a user tweak a curated set of simulation/graphics parameters before
the sim starts, instead of hand-editing JSON config files.
"""
from __future__ import annotations

from dataclasses import replace

import pygame
import pygame_menu

from src.config import GfxConfig, SimConfig


def show_settings_menu(sim_config: SimConfig, gfx_config: GfxConfig) -> tuple[SimConfig, GfxConfig]:
    """Blocking pre-game settings screen. Returns (updated_sim_config, updated_gfx_config).

    Closing the window here exits the whole program (pygame_menu's default
    QUIT handling), same as closing the main sim window would.
    """
    screen = pygame.display.set_mode((gfx_config.window_width, gfx_config.window_height))
    pygame.display.set_caption("Molecular Evolution Simulator - Settings")

    theme = pygame_menu.themes.THEME_DARK.copy()
    theme.title_font_size = 26
    theme.widget_font_size = 18

    menu = pygame_menu.Menu(
        "Simulation Settings",
        gfx_config.window_width, gfx_config.window_height,
        theme=theme,
    )

    values = {
        "num_blocks": sim_config.num_blocks,
        "speed_scale": sim_config.speed_scale,
        "formation_reactivity_mean": sim_config.formation_reactivity_mean,
        "breaking_reactivity_mean": sim_config.breaking_reactivity_mean,
        "block_radius": gfx_config.block_radius,
        "use_illustrated_blocks": gfx_config.use_illustrated_blocks,
        "donor_tint": tuple(gfx_config.donor_tint) if gfx_config.donor_tint else (14, 86, 242),
        "acceptor_tint": tuple(gfx_config.acceptor_tint) if gfx_config.acceptor_tint else (255, 20, 146),
        "bg_color": tuple(gfx_config.bg_color),
        "sprite_tint_opacity": gfx_config.sprite_tint_opacity,
        "animated_molecule_min_n": gfx_config.animated_molecule_min_n,
    }

    menu.add.label("Simulation", font_size=22)
    menu.add.range_slider(
        "Num Blocks", values["num_blocks"], (50, 2000), 10,
        onchange=lambda v: values.update(num_blocks=int(v)),
    )
    menu.add.range_slider(
        "Speed Scale", values["speed_scale"], (0.5, 5.0), 0.1,
        onchange=lambda v: values.update(speed_scale=round(v, 2)),
    )
    menu.add.range_slider(
        "Formation Reactivity", values["formation_reactivity_mean"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(formation_reactivity_mean=round(v, 2)),
    )
    menu.add.range_slider(
        "Breaking Reactivity", values["breaking_reactivity_mean"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(breaking_reactivity_mean=round(v, 2)),
    )

    menu.add.label("Graphics", font_size=22)
    menu.add.range_slider(
        "Block Radius", values["block_radius"], (4, 20), 1,
        onchange=lambda v: values.update(block_radius=float(v)),
    )
    menu.add.toggle_switch(
        "Illustrated Blocks", values["use_illustrated_blocks"],
        onchange=lambda v: values.update(use_illustrated_blocks=bool(v)),
    )
    menu.add.color_input(
        "Donor Color", color_type="rgb", default=values["donor_tint"],
        onchange=lambda v: values.update(donor_tint=v),
    )
    menu.add.color_input(
        "Acceptor Color", color_type="rgb", default=values["acceptor_tint"],
        onchange=lambda v: values.update(acceptor_tint=v),
    )
    menu.add.color_input(
        "Background Color", color_type="rgb", default=values["bg_color"],
        onchange=lambda v: values.update(bg_color=v),
    )
    menu.add.range_slider(
        "Tint Opacity", values["sprite_tint_opacity"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(sprite_tint_opacity=round(v, 2)),
    )
    menu.add.range_slider(
        "Min Animated Size (n)", values["animated_molecule_min_n"], (0, 30), 1,
        onchange=lambda v: values.update(animated_molecule_min_n=int(v)),
    )

    menu.add.button("Start Simulation", pygame_menu.events.CLOSE)

    menu.mainloop(screen)

    new_sim = replace(
        sim_config,
        num_blocks=values["num_blocks"],
        speed_scale=values["speed_scale"],
        formation_reactivity_mean=values["formation_reactivity_mean"],
        breaking_reactivity_mean=values["breaking_reactivity_mean"],
    )
    new_gfx = replace(
        gfx_config,
        block_radius=values["block_radius"],
        use_illustrated_blocks=values["use_illustrated_blocks"],
        donor_tint=list(values["donor_tint"]),
        acceptor_tint=list(values["acceptor_tint"]),
        bg_color=list(values["bg_color"]),
        sprite_tint_opacity=values["sprite_tint_opacity"],
        animated_molecule_min_n=values["animated_molecule_min_n"],
    )
    return new_sim, new_gfx
