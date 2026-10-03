"""Pre-game / mid-game settings screen built with pygame_menu.

Lets a user type in a curated set of simulation parameters, styled to
match the main app (water background, legend's font, rounded "bubble"
widgets) instead of looking like a separate generic menu.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import replace

import pygame
import pygame_menu
from pygame_menu.locals import ALIGN_CENTER, INPUT_FLOAT, INPUT_INT

from src.config import GfxConfig, SimConfig

# Same font stack used for the legend, so the settings screen matches.
_FONT_STACK = "avenirnext,avenir,segoeui,trebuchetms,verdana,tahoma,arial"


def _blended_rect(surface, color, rect, border_radius=0, width=0):
    """Draw a (possibly translucent) rect with real alpha blending.

    The real game window's surface has a per-pixel alpha channel (unlike
    the dummy/test driver), and pygame.draw.rect() does not blend alpha --
    it writes the color's alpha straight into the destination, which
    punches actual transparent holes in the real window instead of
    visually blending. Drawing onto a throwaway SRCALPHA surface first
    and blitting that over `surface` blends properly in both cases.
    """
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, color, layer.get_rect(), width=width, border_radius=border_radius)
    surface.blit(layer, rect.topleft)


def _add_rounded_bubble(widget, color=(255, 255, 255, 180), radius=20, inflate=(4, 4), state=None):
    """Draw an actual rounded rect behind a widget. Returns a mutable

    {'color': ...} holder so callers can change the color later (e.g. to
    flash red for invalid input) without re-registering the decorator.
    Pass an existing holder via `state` to reuse/update it instead of
    creating a new one (useful when a callback needs the holder before
    the widget it decorates has been created).
    pygame_menu's own background_color/border_radius kwargs don't render
    rounded corners in this version -- this draws one manually with
    pygame.draw.rect's native border_radius support instead.
    """
    if state is None:
        state = {"color": color}
    else:
        state["color"] = color

    def _draw(surface, wid):
        rect = wid.get_rect(inflate=inflate, to_absolute_position=True)
        _blended_rect(surface, state["color"], rect, border_radius=radius)
    widget.get_decorator().add_callable(_draw, prev=True)
    return state


def _shade(color, factor):
    """Lighten (factor > 1) or darken (factor < 1) an RGB(A) color."""
    r, g, b = color[0], color[1], color[2]
    a = color[3] if len(color) > 3 else 255
    return (
        max(0, min(255, int(r * factor))),
        max(0, min(255, int(g * factor))),
        max(0, min(255, int(b * factor))),
        a,
    )


_BUBBLE_OUTLINE_PATH = "assets/buttonOutline.png"
_bubble_outline_src = None
_bubble_outline_cache = {}


def _get_bubble_outline(width, height):
    """Build (and cache) the hand-drawn bubble outline stretched to fit a

    box of the given size, using a 3-slice (left cap / stretchy middle /
    right cap) instead of a single non-uniform stretch -- a flat stretch
    badly squashes the art's rounded ends on the wide, flat label/input
    boxes (fine on the roughly pill-shaped buttons, but not here), while
    keeping the caps at their natural proportions reads correctly at any
    width. The source art is trimmed to its own ink bounding box first, so
    the stretched result fills `width`x`height` edge-to-edge instead of
    leaving a transparent margin (which made it look smaller than the
    colored fill behind it).
    """
    global _bubble_outline_src
    key = (int(width), int(height))
    if key in _bubble_outline_cache:
        return _bubble_outline_cache[key]
    if _bubble_outline_src is None:
        if os.path.exists(_BUBBLE_OUTLINE_PATH):
            raw = pygame.image.load(_BUBBLE_OUTLINE_PATH).convert_alpha()
            content = raw.get_bounding_rect(min_alpha=10)
            _bubble_outline_src = raw.subsurface(content).copy()
        else:
            _bubble_outline_src = False
    if _bubble_outline_src is False or width <= 0 or height <= 0:
        _bubble_outline_cache[key] = None
        return None

    src = _bubble_outline_src
    sw, sh = src.get_size()
    scale = height / sh
    cap_src_w = min(sw // 2, 150)
    cap_w = max(1, min(int(width) // 2, int(cap_src_w * scale)))
    mid_w = max(1, int(width) - 2 * cap_w)

    out = pygame.Surface((int(width), int(height)), pygame.SRCALPHA)
    left = pygame.transform.smoothscale(src.subsurface((0, 0, cap_src_w, sh)), (cap_w, int(height)))
    right = pygame.transform.smoothscale(src.subsurface((sw - cap_src_w, 0, cap_src_w, sh)), (cap_w, int(height)))
    mid = pygame.transform.smoothscale(src.subsurface((cap_src_w, 0, sw - 2 * cap_src_w, sh)), (mid_w, int(height)))
    out.blit(left, (0, 0))
    out.blit(mid, (cap_w, 0))
    out.blit(right, (cap_w + mid_w, 0))
    _bubble_outline_cache[key] = out
    return out


def _add_game_button(widget, color=(90, 200, 120, 230), radius=22, inflate=(16, 10)):
    """Pill button: solid fill plus the user's hand-drawn bubble outline

    (3-sliced so it doesn't squash at this width) instead of a flat drawn
    border.
    """
    def _draw(surface, wid):
        rect = wid.get_rect(inflate=inflate, to_absolute_position=True)
        _blended_rect(surface, color, rect, border_radius=radius)
        outline = _get_bubble_outline(rect.width, rect.height)
        if outline is not None:
            surface.blit(outline, rect.topleft)
    widget.get_decorator().add_callable(_draw, prev=True)


def _add_value_box(widget, label_text, label_font, gap=10,
                    label_bg=(225, 230, 240, 235), label_fg=(25, 35, 55),
                    input_color=(20, 35, 75, 220), inflate=(8, 6), box_pad=18, state=None):
    """Draw a light, dark-text label bubble (no bubble-outline art -- that

    only fit the roughly pill-shaped buttons, not these wide flat boxes)
    immediately to the left of a plain-value text_input's dark/white-text
    box. The two need separate text colors (light bubble needs dark text,
    dark input box needs white text), which isn't possible with a single
    pygame_menu widget's title+value sharing one font color -- so the
    label here is hand-rendered text, not the widget's own title (which is
    left empty; the widget only ever shows the editable number).
    Returns a mutable {'input_color': ...} holder so callers can flash the
    input box red for invalid values without re-registering the decorator.
    """
    if state is None:
        state = {"input_color": input_color}
    else:
        state["input_color"] = input_color
    label_w, label_h = label_font.size(label_text)
    label_total_w = label_w + 24

    def _draw(surface, wid):
        rect = wid.get_rect(to_absolute_position=True)
        _, _, _, pad_left = wid.get_padding()
        box_h = wid._font.get_height() + inflate[1]
        box_top = rect.centery - box_h // 2
        value_str = str(wid.get_value() or "0")
        value_w = wid._font.size(value_str)[0]
        input_rect = pygame.Rect(
            rect.left + pad_left - box_pad // 2, box_top,
            value_w + box_pad, box_h,
        )
        label_rect = pygame.Rect(
            input_rect.left - gap - label_total_w, box_top,
            label_total_w, box_h,
        )
        _blended_rect(surface, label_bg, label_rect, border_radius=14)
        label_outline = _get_bubble_outline(label_rect.width, label_rect.height)
        if label_outline is not None:
            surface.blit(label_outline, label_rect.topleft)
        else:
            _blended_rect(surface, _shade(label_bg, 0.85), label_rect, width=2, border_radius=14)
        label_surf = label_font.render(label_text, True, label_fg)
        surface.blit(label_surf, (label_rect.centerx - label_w // 2, label_rect.centery - label_h // 2))

        _blended_rect(surface, state["input_color"], input_rect, border_radius=0)
        _blended_rect(surface, _shade(state["input_color"], 1.6), input_rect, width=2, border_radius=0)
        if wid.is_selected():
            _blended_rect(surface, (255, 190, 60), input_rect, width=2, border_radius=0)
    widget.get_decorator().add_callable(_draw, prev=True)
    # The default selection highlight is one box spanning the whole widget
    # -- replaced with our own focus border drawn only around the input
    # box above, so it doesn't cover the separately-drawn label.
    widget.set_selection_effect(pygame_menu.widgets.NoneSelection())
    return state, label_total_w


def _make_numeric_field(menu, label, key, values, value_range, input_type, decimals=None):
    """A single row: a light, dark-text label bubble ('Label (lo-hi): ')

    immediately to the left of a separate dark input box showing just the
    editable number. Typing a value outside value_range turns the input
    box red and shows an inline "Outside range" message instead of
    silently clamping it; valid values are written into `values[key]`
    immediately.
    """
    lo, hi = value_range

    error_label = menu.add.label(
        "", font_size=13, font_color=(255, 140, 140), align=ALIGN_CENTER, margin=(0, 2),
    )

    def _on_change(v):
        try:
            num = float(v)
        except (TypeError, ValueError):
            error_label.set_title("Invalid value")
            box_state["input_color"] = (120, 40, 40, 220)
            return
        if not (lo <= num <= hi):
            error_label.set_title(f"Outside range ({lo}-{hi})")
            box_state["input_color"] = (120, 40, 40, 220)
            return
        error_label.set_title("")
        box_state["input_color"] = (20, 35, 75, 220)
        values[key] = int(num) if input_type == INPUT_INT else round(num, decimals or 2)

    label_text = f"{label} ({lo}-{hi}): "
    label_font_path = pygame.font.match_font(_FONT_STACK)
    label_font = pygame.font.Font(label_font_path, 18)
    label_w, _ = label_font.size(label_text)
    label_total_w = label_w + 24
    gap = 10
    # Shift the (otherwise centered) value box left by half the label +
    # gap width, so the label-plus-value group as a whole stays centered
    # instead of just the value box.
    shift_x = (label_total_w + gap) // 2

    field = menu.add.text_input(
        "", default=str(values[key]), input_type=input_type,
        font_color=(255, 255, 255), onchange=_on_change, onreturn=_on_change,
        padding=(6, 14), align=ALIGN_CENTER, margin=(shift_x, 4),
    )
    # Keep text white even while selected -- theme.selection_color (gold) would
    # otherwise recolor the value text itself, not just the outline.
    field.set_font(
        font=field._font_name, font_size=field._font_size,
        color=(255, 255, 255), selected_color=(255, 255, 255),
        readonly_color=(255, 255, 255), readonly_selected_color=(255, 255, 255),
        background_color=None,
    )
    box_state, _ = _add_value_box(field, label_text, label_font, gap=gap)



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
    # Flat title bar (no banner/diagonal shape) -- it read as a big button
    # holding the whole page; just plain text over the water art now.
    theme.title_bar_style = pygame_menu.widgets.MENUBAR_STYLE_NONE
    theme.title_font_color = (255, 255, 255)
    theme.title_font_shadow = True
    theme.widget_font_color = (255, 255, 255)
    theme.selection_color = (255, 210, 80)
    theme.widget_margin = (0, 8)

    # Composite the water drawing over a solid navy backdrop (so any
    # transparent/uncovered pixels in the art show this blue, not black),
    # saved as a JPG (no alpha channel at all) and loaded as
    # theme.background_color. Any PNG/BytesIO round-trip here -- even one
    # saved to a real file -- comes back with alpha stuck at 0 (fully
    # transparent) under the real ("cocoa") display driver in this
    # environment, which silently no-ops every draw/blit of it; a format
    # with no alpha channel at all sidesteps that entirely.
    _BG_BLUE = (24, 40, 90)
    water_bg_path = "assets/waterDrawing.png"
    theme.background_color = _BG_BLUE
    if os.path.exists(water_bg_path):
        win_size = (gfx_config.window_width, gfx_config.window_height)
        backdrop = pygame.Surface(win_size)
        backdrop.fill(_BG_BLUE)
        water_img = pygame.image.load(water_bg_path).convert_alpha()
        water_img = pygame.transform.smoothscale(water_img, win_size)
        backdrop.blit(water_img, (0, 0))
        composited_path = os.path.join(tempfile.gettempdir(), "_settings_bg_composited.jpg")
        pygame.image.save(backdrop, composited_path)
        theme.background_color = pygame_menu.BaseImage(
            image_path=composited_path, drawing_mode=pygame_menu.baseimage.IMAGE_MODE_FILL,
        )

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

    _make_numeric_field(menu, "Num Sprites", "num_blocks", values, (50, 2000), INPUT_INT)
    _make_numeric_field(menu, "Speed Scale", "speed_scale", values, (0.5, 5.0), INPUT_FLOAT)
    _make_numeric_field(menu, "Formation Reactivity", "formation_reactivity_mean", values, (0.0, 1.0), INPUT_FLOAT)
    _make_numeric_field(menu, "Breaking Reactivity", "breaking_reactivity_mean", values, (0.0, 1.0), INPUT_FLOAT)

    def _apply():
        applied["value"] = True
        menu.disable()

    def _cancel():
        # pygame_menu.events.CLOSE is a no-op on a root menu with no
        # parent to return to -- disable() is what actually ends mainloop().
        menu.disable()

    menu.add.vertical_margin(24)
    apply_btn = menu.add.button(
        "Apply & Restart", _apply, align=ALIGN_CENTER,
        font_color=(20, 50, 20), padding=(10, 26), margin=(0, 10),
    )
    _add_game_button(apply_btn, color=(90, 200, 120, 230))

    cancel_btn = menu.add.button(
        "Cancel", _cancel, align=ALIGN_CENTER,
        font_color=(40, 40, 40), padding=(8, 22), margin=(0, 10),
    )
    _add_game_button(cancel_btn, color=(225, 225, 225, 230))

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

