"""Pre-game / mid-game settings screen built with pygame_menu.

Lets a user type in a curated set of simulation parameters, styled to
match the main app (water background, legend's font, rounded "bubble"
widgets) instead of looking like a separate generic menu.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pygame
import pygame_menu
from pygame_menu.locals import ALIGN_CENTER, ALIGN_LEFT, INPUT_FLOAT, INPUT_INT

from src.config import GfxConfig, SimConfig

# Same font stack used for the legend, so the settings screen matches.
_FONT_STACK = "avenirnext,avenir,segoeui,trebuchetms,verdana,tahoma,arial"

# Left edge each field's text aligns against -- shifted in from the true
# window edge so the whole block of fields reads as roughly centered on
# screen rather than hugging the left margin.
_LEFT_X = 320

# Fields just get padding (room for the rounded bubble drawn separately
# below) -- background_color/border_radius on the widget itself don't
# actually render rounded corners in this pygame_menu version.
_FIELD_STYLE = dict(
    padding=(6, 14),
    align=ALIGN_LEFT,
    margin=(_LEFT_X, 18),
)


def _add_rounded_bubble(widget, color=(255, 255, 255, 180), radius=20, inflate=(4, 4)):
    """Draw an actual rounded rect behind a widget.

    pygame_menu's own background_color/border_radius kwargs don't render
    rounded corners in this version -- this draws one manually with
    pygame.draw.rect's native border_radius support instead.
    """
    def _draw(surface, wid):
        rect = wid.get_rect(inflate=inflate, to_absolute_position=True)
        pygame.draw.rect(surface, color, rect, border_radius=radius)
    widget.get_decorator().add_callable(_draw, prev=True)


def _make_numeric_field(menu, label, key, values, value_range, input_type, decimals=None):
    """A labeled text field that types a number, clamped to value_range."""
    lo, hi = value_range
    menu.add.label(
        f"{label} ({lo}-{hi})", font_size=16, font_color=(255, 255, 255),
        align=ALIGN_LEFT, margin=(_LEFT_X, 2),
    )

    def _on_change(v):
        try:
            num = float(v)
        except (TypeError, ValueError):
            return
        num = max(lo, min(hi, num))
        values[key] = int(num) if input_type == INPUT_INT else round(num, decimals or 2)

    field = menu.add.text_input(
        "", default=str(values[key]), input_type=input_type,
        onchange=_on_change, onreturn=_on_change, **_FIELD_STYLE,
    )
    _add_rounded_bubble(field)


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
    theme.widget_margin = (0, 18)

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

    applied = {"value": False}
    values = {
        "num_blocks": sim_config.num_blocks,
        "speed_scale": sim_config.speed_scale,
        "formation_reactivity_mean": sim_config.formation_reactivity_mean,
        "breaking_reactivity_mean": sim_config.breaking_reactivity_mean,
    }

    _make_numeric_field(menu, "Num Blocks", "num_blocks", values, (50, 2000), INPUT_INT)
    _make_numeric_field(menu, "Speed Scale", "speed_scale", values, (0.5, 5.0), INPUT_FLOAT)
    _make_numeric_field(menu, "Formation Reactivity", "formation_reactivity_mean", values, (0.0, 1.0), INPUT_FLOAT)
    _make_numeric_field(menu, "Breaking Reactivity", "breaking_reactivity_mean", values, (0.0, 1.0), INPUT_FLOAT)

    def _apply():
        applied["value"] = True
        menu.disable()

    menu.add.vertical_margin(24)
    apply_btn = menu.add.button(
        "Apply & Restart", _apply, align=ALIGN_CENTER,
        font_color=(20, 50, 20), padding=(10, 26),
    )
    _add_rounded_bubble(apply_btn, color=(90, 200, 120, 230), radius=22, inflate=(6, 6))

    cancel_btn = menu.add.button(
        "Cancel", pygame_menu.events.CLOSE, align=ALIGN_CENTER,
        font_color=(40, 40, 40), padding=(8, 22),
    )
    _add_rounded_bubble(cancel_btn, color=(225, 225, 225, 210), radius=22, inflate=(6, 6))

    menu.center_content()
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
    return new_sim, gfx_config, True

