"""Pre-game / mid-game settings screen built with pygame_menu.

Lets a user tweak a curated set of simulation/graphics parameters,
styled to match the main app (water background, legend's font, rounded
"bubble" widgets) instead of looking like a separate generic menu.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pygame
import pygame_menu
from pygame_menu.locals import ALIGN_LEFT

from src.config import GfxConfig, SimConfig

# Same font stack used for the legend, so the settings screen matches.
_FONT_STACK = "avenirnext,avenir,segoeui,trebuchetms,verdana,tahoma,arial"

# Left edge every widget aligns against (a vertical "bar" is drawn here).
_LEFT_X = 40

# "Bubble" look shared by every widget: soft rounded, translucent white
# panel with a light border, reads as a playful water-themed pill/bubble.
# Kept modest (small padding/border) so widgets don't visually touch/
# overlap their neighbors even with theme.widget_margin spacing them out.
_BUBBLE_STYLE = dict(
    background_color=(255, 255, 255, 170),
    border_color=(255, 255, 255),
    border_width=1,
    border_radius=14,
    padding=(4, 10),
    align=ALIGN_LEFT,
    margin=(_LEFT_X, 18),
)


def show_settings_menu(sim_config: SimConfig, gfx_config: GfxConfig) -> tuple[SimConfig, GfxConfig, bool]:
    """Blocking settings screen. Returns (sim_config, gfx_config, applied).

    `applied` is False if the user hit Cancel (or closed the window without
    applying) -- callers should keep their existing configs in that case.
    Closing the window here exits the whole program, same as the main sim.
    """
    screen = pygame.display.set_mode((gfx_config.window_width, gfx_config.window_height))
    pygame.display.set_caption("Molecular Evolution Simulator - Settings")

    font_path = pygame.font.match_font(_FONT_STACK)

    theme = pygame_menu.themes.THEME_DARK.copy()
    if font_path:
        theme.widget_font = font_path
        theme.title_font = font_path
    theme.title_font_size = 28
    theme.widget_font_size = 18
    theme.title_background_color = (20, 60, 110, 210)
    theme.title_font_color = (255, 255, 255)
    theme.widget_font_color = (20, 30, 40)
    theme.selection_color = (255, 210, 80)
    # Vertical gap between widgets -- without this they render touching
    # edge-to-edge, which both looks stacked and makes clicks land on the
    # wrong (overlapping) widget.
    theme.widget_margin = (0, 18)
    theme.widget_alignment = ALIGN_LEFT

    water_bg = "assets/waterDrawing.png"
    if os.path.exists(water_bg):
        theme.background_color = pygame_menu.BaseImage(
            image_path=water_bg, drawing_mode=pygame_menu.baseimage.IMAGE_MODE_FILL,
        )
    else:
        theme.background_color = (180, 215, 240)

    menu = pygame_menu.Menu(
        "Settings",
        gfx_config.window_width, gfx_config.window_height,
        theme=theme,
    )

    # Vertical accent bar that every widget's left edge lines up against.
    # Decorator coordinates are relative to the menu's center, not its
    # top-left corner -- offset accordingly so the bar lands at _LEFT_X.
    bar_x = _LEFT_X - gfx_config.window_width / 2
    bar_y1 = -gfx_config.window_height / 2
    bar_y2 = gfx_config.window_height / 2
    menu.get_decorator().add_vline(bar_x, bar_y1, bar_y2, (255, 255, 255, 140), width=2)

    applied = {"value": False}
    values = {
        "num_blocks": sim_config.num_blocks,
        "speed_scale": sim_config.speed_scale,
        "formation_reactivity_mean": sim_config.formation_reactivity_mean,
        "breaking_reactivity_mean": sim_config.breaking_reactivity_mean,
        "block_radius": gfx_config.block_radius,
        "use_illustrated_blocks": gfx_config.use_illustrated_blocks,
        "bg_color": tuple(gfx_config.bg_color),
        "sprite_tint_opacity": gfx_config.sprite_tint_opacity,
        "animated_molecule_min_n": gfx_config.animated_molecule_min_n,
    }

    menu.add.label("Simulation", font_size=20, font_color=(255, 255, 255), margin=(_LEFT_X, 10))
    menu.add.range_slider(
        "Num Blocks", values["num_blocks"], (50, 2000), 10,
        onchange=lambda v: values.update(num_blocks=int(v)), **_BUBBLE_STYLE,
    )
    menu.add.range_slider(
        "Speed Scale", values["speed_scale"], (0.5, 5.0), 0.1,
        onchange=lambda v: values.update(speed_scale=round(v, 2)), **_BUBBLE_STYLE,
    )
    menu.add.range_slider(
        "Formation Reactivity", values["formation_reactivity_mean"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(formation_reactivity_mean=round(v, 2)), **_BUBBLE_STYLE,
    )
    menu.add.range_slider(
        "Breaking Reactivity", values["breaking_reactivity_mean"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(breaking_reactivity_mean=round(v, 2)), **_BUBBLE_STYLE,
    )

    menu.add.label("Graphics", font_size=20, font_color=(255, 255, 255), margin=(_LEFT_X, 10))
    menu.add.range_slider(
        "Block Radius", values["block_radius"], (4, 20), 1,
        onchange=lambda v: values.update(block_radius=float(v)), **_BUBBLE_STYLE,
    )
    menu.add.toggle_switch(
        "Illustrated Blocks", values["use_illustrated_blocks"],
        onchange=lambda v: values.update(use_illustrated_blocks=bool(v)), **_BUBBLE_STYLE,
    )
    menu.add.color_input(
        "Background Color", color_type="rgb", default=values["bg_color"],
        onchange=lambda v: values.update(bg_color=v), **_BUBBLE_STYLE,
    )
    menu.add.range_slider(
        "Tint Opacity", values["sprite_tint_opacity"], (0.0, 1.0), 0.05,
        onchange=lambda v: values.update(sprite_tint_opacity=round(v, 2)), **_BUBBLE_STYLE,
    )
    menu.add.range_slider(
        "Min Animated Size (n)", values["animated_molecule_min_n"], (0, 30), 1,
        onchange=lambda v: values.update(animated_molecule_min_n=int(v)), **_BUBBLE_STYLE,
    )

    def _apply():
        applied["value"] = True
        menu.disable()

    menu.add.vertical_margin(20)
    apply_btn = menu.add.button(
        "Apply & Restart", _apply, align=ALIGN_LEFT, margin=(_LEFT_X, 18),
        font_color=(20, 50, 20), border_radius=22, accept_kwargs=True,
    )
    apply_btn.set_background_color((90, 200, 120, 220))
    apply_btn.set_border(width=2, color=(255, 255, 255), inflate=(10, 10))
    apply_btn.set_padding((10, 26))

    cancel_btn = menu.add.button(
        "Cancel", pygame_menu.events.CLOSE, align=ALIGN_LEFT, margin=(_LEFT_X, 18),
        font_color=(40, 40, 40), border_radius=22, accept_kwargs=True,
    )
    cancel_btn.set_background_color((220, 220, 220, 180))
    cancel_btn.set_border(width=2, color=(255, 255, 255), inflate=(10, 10))
    cancel_btn.set_padding((8, 22))

    menu.mainloop(screen)

    if not applied["value"]:
        return sim_config, gfx_config, False

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
        bg_color=list(values["bg_color"]),
        sprite_tint_opacity=values["sprite_tint_opacity"],
        animated_molecule_min_n=values["animated_molecule_min_n"],
    )
    return new_sim, new_gfx, True

