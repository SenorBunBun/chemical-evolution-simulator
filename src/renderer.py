from __future__ import annotations

import pygame
from pygame.math import Vector2

from src.config import GfxConfig, SimConfig
from src.entities import SimulationState


# --- Color Helpers ---

# Label and description for each colorable property
COLOR_BY_INFO = {
    "formation_reactivity": ("Formation Reactivity", "inert", "reactive"),
    "mobility":             ("Mobility",             "slow",  "fast"),
    "breaking_reactivity":  ("Breaking Reactivity",  "stable","fragile"),
    "latent_catalytic_potential": ("Catalytic Potential", "low", "high"),
    "h_bond_type":          ("H-Bond Type",          "donor", "acceptor"),
}


def _make_lerp_color_fn(low: tuple, high: tuple):
    """Create a color function that linearly interpolates between low and high."""
    def fn(value: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, value))
        return (
            int(low[0] + (high[0] - low[0]) * t),
            int(low[1] + (high[1] - low[1]) * t),
            int(low[2] + (high[2] - low[2]) * t),
        )
    return fn


class Renderer:
    LEGEND_WIDTH = 200
    LEGEND_BG = (36, 36, 36)
    TEXT_COLOR = (220, 220, 220)
    DIM_TEXT = (140, 140, 140)
    GRID_COLOR = (200, 200, 200)
    MOL_OUTLINE = (0, 0, 0)
    ASM_OUTLINE = (218, 165, 32)  # goldenrod

    def __init__(self, sim_config: SimConfig, gfx: GfxConfig):
        pygame.init()
        self.screen = pygame.display.set_mode((gfx.window_width, gfx.window_height))
        pygame.display.set_caption("Molecular Evolution Simulator")
        self.font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("consolas", 11)
        self.title_font = pygame.font.SysFont("consolas", 16, bold=True)
        self.sim_width = gfx.window_width - self.LEGEND_WIDTH
        self.sim_config = sim_config
        self.gfx = gfx
        self._block_color_fn = _make_lerp_color_fn(
            tuple(gfx.block_color_low), tuple(gfx.block_color_high)
        )
        self._bond_color_fn = _make_lerp_color_fn(
            tuple(gfx.bond_color_strong), tuple(gfx.bond_color_fragile)
        )
        self.debug_mode = False
        self._stepping = False

    def handle_events(self, state: SimulationState) -> bool:
        """Process input events. Returns False if quit requested."""
        self._stepping = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_SPACE:
                    state.paused = not state.paused
                elif event.key == pygame.K_RIGHT and state.paused:
                    self._stepping = True
                elif event.key == pygame.K_UP:
                    state.speed_multiplier = min(32, state.speed_multiplier * 2)
                elif event.key == pygame.K_DOWN:
                    state.speed_multiplier = max(1, state.speed_multiplier // 2)
                elif event.key == pygame.K_d:
                    self.debug_mode = not self.debug_mode
                elif event.key == pygame.K_r:
                    state._reset_requested = True

            if (event.type == pygame.MOUSEBUTTONDOWN
                    and state.paused and self.debug_mode):
                self._inspect_click(state, event.pos)

        return True

    @property
    def should_step(self) -> bool:
        return self._stepping

    def draw(self, state: SimulationState):
        """Render one frame: simulation area + legend panel."""
        self.screen.fill(tuple(self.gfx.bg_color))

        # Blocks first, bonds on top so they're visible when blocks touch
        self._draw_blocks(state)
        self._draw_bonds(state)

        if self.debug_mode:
            self._draw_debug(state)

        self._draw_legend(state)
        pygame.display.flip()

    def _draw_blocks(self, state: SimulationState):
        r = int(self.gfx.block_radius)
        color_by = self.gfx.block_color_by

        for block in state.blocks.values():
            x, y = int(block.position.x), int(block.position.y)
            if x < 0 or x > self.sim_width or y < 0 or y > self.gfx.window_height:
                continue

            color = self._get_block_color(block, color_by)
            pygame.draw.circle(self.screen, color, (x, y), r)

            if self.gfx.block_outline and block.molecule_id is not None:
                if block.assembly_id is not None:
                    pygame.draw.circle(self.screen, self.ASM_OUTLINE, (x, y), r + 1, 2)
                else:
                    pygame.draw.circle(self.screen, self.MOL_OUTLINE, (x, y), r, 1)

    def _draw_bonds(self, state: SimulationState):
        for bond in state.bonds.values():
            a = state.blocks[bond.block_a_id]
            b = state.blocks[bond.block_b_id]

            if bond.is_h_bond:
                color = (50, 120, 255)
                width = self.gfx.h_bond_width
            else:
                break_prob = (a.breaking_reactivity + b.breaking_reactivity) / 2
                color = self._bond_color_fn(break_prob)
                width = self.gfx.bond_width

            start = (int(a.position.x), int(a.position.y))
            end = (int(b.position.x), int(b.position.y))
            pygame.draw.line(self.screen, color, start, end, width)

    def _draw_legend(self, state: SimulationState):
        panel_x = self.sim_width
        panel_w = self.LEGEND_WIDTH
        panel_h = self.gfx.window_height

        pygame.draw.rect(self.screen, self.LEGEND_BG,
                         (panel_x, 0, panel_w, panel_h))
        pygame.draw.line(self.screen, (60, 60, 60),
                         (panel_x, 0), (panel_x, panel_h), 1)

        y = 15
        margin = 15

        title = self.title_font.render("LEGENDS", True, self.TEXT_COLOR)
        self.screen.blit(title, (panel_x + margin, y))
        y += 30

        # Block color gradient (matches block_color_by)
        color_by = self.gfx.block_color_by
        info = COLOR_BY_INFO.get(color_by, (color_by, "0.0", "1.0"))

        if color_by == "h_bond_type":
            # Discrete legend instead of gradient
            y = self._draw_discrete_legend(
                panel_x + margin, y, info[0],
                [("Donor", (80, 130, 255)), ("Acceptor", (255, 80, 80))]
            )
        else:
            y = self._draw_gradient_bar(
                panel_x + margin, y, panel_w - 2 * margin,
                info[0], self._block_color_fn,
                f"0.0 ({info[1]})", f"1.0 ({info[2]})",
            )
        y += 20

        # Bond strength gradient
        y = self._draw_gradient_bar(
            panel_x + margin, y, panel_w - 2 * margin,
            "Bond Strength", self._bond_color_fn,
            "0.0 (strong)", "1.0 (fragile)",
        )
        y += 15

        # H-bond swatch
        hb_label = self.font.render("H-Bond", True, self.TEXT_COLOR)
        self.screen.blit(hb_label, (panel_x + margin, y))
        hb_x = panel_x + margin + 60
        pygame.draw.line(self.screen, (50, 120, 255),
                         (hb_x, y + 8), (hb_x + 30, y + 8), 1)
        y += 20

        # Assembly swatch
        asm_label = self.font.render("Assembly", True, self.TEXT_COLOR)
        self.screen.blit(asm_label, (panel_x + margin, y))
        asm_x = panel_x + margin + 72
        pygame.draw.circle(self.screen, self.ASM_OUTLINE, (asm_x + 8, y + 8), 8, 2)
        y += 25

        # Divider
        pygame.draw.line(self.screen, (60, 60, 60),
                         (panel_x + margin, y), (panel_x + panel_w - margin, y), 1)
        y += 15

        # Stats
        stats_title = self.font.render("STATS", True, self.TEXT_COLOR)
        self.screen.blit(stats_title, (panel_x + margin, y))
        y += 22

        # Count bond types
        covalent_bonds = sum(1 for b in state.bonds.values() if not b.is_h_bond)
        h_bonds = sum(1 for b in state.bonds.values() if b.is_h_bond)

        stats = [
            f"Tick: {state.tick}",
            f"Blocks: {len(state.blocks)}",
            f"Bonds: {covalent_bonds}",
            f"H-Bonds: {h_bonds}",
            f"Molecules: {len(state.molecules)}",
        ]
        free_blocks = sum(1 for b in state.blocks.values() if b.molecule_id is None)
        total = len(state.blocks)
        if total > 0:
            pct_bonded = (total - free_blocks) / total * 100
            stats.append(f"Bonded: {pct_bonded:.0f}%")

        # Avg N: average blocks per entity (free blocks count as N=1)
        # Assemblies contribute their total block count as one entity
        assembled_mol_ids = set()
        for asm in state.assemblies.values():
            assembled_mol_ids.update(asm.molecule_ids)
        standalone_mols = [m for m in state.molecules.values() if m.id not in assembled_mol_ids]

        num_entities = free_blocks + len(standalone_mols) + len(state.assemblies)
        if num_entities > 0:
            total_n = free_blocks
            total_n += sum(m.n for m in standalone_mols)
            total_n += sum(
                sum(state.molecules[mid].n for mid in asm.molecule_ids)
                for asm in state.assemblies.values()
            )
            avg_n = total_n / num_entities
            stats.append(f"Avg N: {avg_n:.1f}")
        else:
            stats.append("Avg N: -")

        if state.molecules:
            avg_n_formed = sum(m.n for m in state.molecules.values()) / len(state.molecules)
            stats.append(f"Avg N (formed): {avg_n_formed:.1f}")
        else:
            stats.append("Avg N (formed): -")

        stats.append(f"Assemblies: {len(state.assemblies)}")

        # Avg M: average molecules per assembly
        if state.assemblies:
            avg_m = sum(len(a.molecule_ids) for a in state.assemblies.values()) / len(state.assemblies)
            stats.append(f"Avg M: {avg_m:.1f}")
        else:
            stats.append("Avg M: -")

        for line in stats:
            text = self.small_font.render(line, True, self.DIM_TEXT)
            self.screen.blit(text, (panel_x + margin, y))
            y += 16

        # Debug-only detailed stats
        if self.debug_mode:
            y += 10
            debug_label = self.font.render("DEBUG STATS", True, (255, 200, 80))
            self.screen.blit(debug_label, (panel_x + margin, y))
            y += 20

            mols = list(state.molecules.values())
            mol_sizes = [m.n for m in mols]

            n5_plus = sum(1 for n in mol_sizes if n >= 5)
            n10_plus = sum(1 for n in mol_sizes if n >= 10)
            max_n = max(mol_sizes) if mol_sizes else 0

            # Donor / acceptor counts
            donors = sum(1 for b in state.blocks.values() if b.h_bond_type.value == "donor")
            acceptors = len(state.blocks) - donors

            # Blocks currently H-bonded
            hbonded_block_ids = set()
            for bond in state.bonds.values():
                if bond.is_h_bond:
                    hbonded_block_ids.add(bond.block_a_id)
                    hbonded_block_ids.add(bond.block_b_id)

            # Avg formation & breaking reactivity
            if state.blocks:
                avg_form = sum(b.formation_reactivity for b in state.blocks.values()) / len(state.blocks)
                avg_break = sum(b.breaking_reactivity for b in state.blocks.values()) / len(state.blocks)
            else:
                avg_form = avg_break = 0.0

            # Largest assembly
            max_asm_mols = max((len(a.molecule_ids) for a in state.assemblies.values()), default=0)
            max_asm_blocks = 0
            for a in state.assemblies.values():
                n_blocks = sum(state.molecules[mid].n for mid in a.molecule_ids)
                if n_blocks > max_asm_blocks:
                    max_asm_blocks = n_blocks

            # Potential assembly matches: eligible mols (N >= min_assembly_n,
            # not already assembled) and how many pairs are H-bond compatible
            min_n = state.config.min_assembly_n
            eligible = [m for m in mols
                        if m.n >= min_n and m.assembly_id is None]
            match_pairs = 0
            for i in range(len(eligible)):
                for j in range(i + 1, len(eligible)):
                    a, b = eligible[i], eligible[j]
                    if a.n != b.n:
                        continue
                    fwd = all(
                        state.blocks[ab].h_bond_type != state.blocks[bb].h_bond_type
                        for ab, bb in zip(a.block_ids, b.block_ids)
                    )
                    rev = all(
                        state.blocks[ab].h_bond_type != state.blocks[bb].h_bond_type
                        for ab, bb in zip(a.block_ids, reversed(b.block_ids))
                    )
                    if fwd or rev:
                        match_pairs += 1

            debug_stats = [
                f"Mols N>=5: {n5_plus}",
                f"Mols N>=10: {n10_plus}",
                f"Max N: {max_n}",
                f"Donors: {donors}  Acc: {acceptors}",
                f"H-bonded blocks: {len(hbonded_block_ids)}",
                f"Avg form react: {avg_form:.2f}",
                f"Avg break react: {avg_break:.2f}",
                f"Largest asm: {max_asm_mols}M / {max_asm_blocks}N",
                f"Eligible (N>={min_n}): {len(eligible)}",
                f"Matching pairs: {match_pairs}",
            ]

            for line in debug_stats:
                text = self.small_font.render(line, True, (255, 220, 120))
                self.screen.blit(text, (panel_x + margin, y))
                y += 16

        y += 20

        # Divider
        pygame.draw.line(self.screen, (60, 60, 60),
                         (panel_x + margin, y), (panel_x + panel_w - margin, y), 1)
        y += 15

        # Controls
        controls_title = self.font.render("CONTROLS", True, self.TEXT_COLOR)
        self.screen.blit(controls_title, (panel_x + margin, y))
        y += 22

        paused_str = "PAUSED" if state.paused else "RUNNING"
        speed_str = f"Speed: {state.speed_multiplier}x"

        controls = [
            f"[{paused_str}] {speed_str}",
            "",
            "SPACE: pause/play",
            "RIGHT: step (paused)",
            "UP/DN: speed +/-",
            "R: reset",
            "D: debug overlay",
            "ESC: quit",
        ]
        for line in controls:
            text = self.small_font.render(line, True, self.DIM_TEXT)
            self.screen.blit(text, (panel_x + margin, y))
            y += 16

    def _draw_gradient_bar(self, x, y, width, label, color_fn, low_label, high_label):
        bar_height = 120
        bar_width = 20

        text = self.font.render(label, True, self.TEXT_COLOR)
        self.screen.blit(text, (x, y))
        y += 20

        bar_x = x + 5
        for row in range(bar_height):
            value = row / bar_height
            color = color_fn(value)
            pygame.draw.line(self.screen, color,
                             (bar_x, y + row), (bar_x + bar_width, y + row))

        low_text = self.small_font.render(low_label, True, self.DIM_TEXT)
        self.screen.blit(low_text, (bar_x + bar_width + 5, y))
        high_text = self.small_font.render(high_label, True, self.DIM_TEXT)
        self.screen.blit(high_text, (bar_x + bar_width + 5, y + bar_height - 12))

        return y + bar_height + 5

    def _draw_discrete_legend(self, x, y, label, items):
        """Draw a discrete color legend (for h_bond_type etc.)."""
        text = self.font.render(label, True, self.TEXT_COLOR)
        self.screen.blit(text, (x, y))
        y += 22
        for name, color in items:
            pygame.draw.circle(self.screen, color, (x + 10, y + 6), 6)
            lbl = self.small_font.render(name, True, self.DIM_TEXT)
            self.screen.blit(lbl, (x + 22, y))
            y += 18
        return y + 5

    def _draw_debug(self, state: SimulationState):
        cell = self.gfx.bond_length
        for gx in range(0, self.sim_width, int(cell)):
            pygame.draw.line(self.screen, self.GRID_COLOR,
                             (gx, 0), (gx, self.gfx.window_height), 1)
        for gy in range(0, self.gfx.window_height, int(cell)):
            pygame.draw.line(self.screen, self.GRID_COLOR,
                             (0, gy), (self.sim_width, gy), 1)

        for block in state.blocks.values():
            x, y = int(block.position.x), int(block.position.y)
            if x < 0 or x > self.sim_width:
                continue

            id_text = self.small_font.render(str(block.id), True, (255, 255, 100))
            self.screen.blit(id_text, (x + 10, y - 5))

            vel = block.velocity
            if block.molecule_id is not None:
                mol = state.molecules[block.molecule_id]
                vel = mol.velocity

            if vel.length_squared() > 0.01:
                arrow_len = min(vel.length() * 5, 30)
                end = block.position + vel.normalize() * arrow_len
                pygame.draw.line(self.screen, (100, 255, 100),
                                 (x, y), (int(end.x), int(end.y)), 1)

    def _get_block_color(self, block, color_by: str) -> tuple[int, int, int]:
        """Get the color for a block based on the configured color_by property."""
        if color_by == "h_bond_type":
            return (80, 130, 255) if block.h_bond_type.value == "donor" else (255, 80, 80)
        value = getattr(block, color_by, 0.5)
        return self._block_color_fn(value)

    def _inspect_click(self, state: SimulationState, pos: tuple[int, int]):
        click = Vector2(pos[0], pos[1])

        for block in state.blocks.values():
            if block.position.distance_to(click) < self.gfx.block_radius * 2:
                print(f"\n=== Block {block.id} ===")
                print(f"  Position: ({block.position.x:.1f}, {block.position.y:.1f})")
                print(f"  Velocity: ({block.velocity.x:.2f}, {block.velocity.y:.2f})")
                print(f"  Mobility: {block.mobility:.3f}")
                print(f"  Formation Reactivity: {block.formation_reactivity:.3f}")
                print(f"  Breaking Reactivity: {block.breaking_reactivity:.3f}")
                print(f"  H-Bond Type: {block.h_bond_type.value}")
                print(f"  Catalytic Potential: {block.latent_catalytic_potential:.3f}")
                print(f"  Bonds: {block.bond_ids}")
                print(f"  Molecule: {block.molecule_id}")
                print(f"  Assembly: {block.assembly_id}")
                if block.molecule_id is not None:
                    mol = state.molecules[block.molecule_id]
                    print(f"  Molecule N: {mol.n}")
                    print(f"  Molecule Vel: ({mol.velocity.x:.2f}, {mol.velocity.y:.2f})")
                print()
                return
