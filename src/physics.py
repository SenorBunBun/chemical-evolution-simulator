from __future__ import annotations

import math

from pygame.math import Vector2

from src.entities import SimulationState


# --- Spatial Hashing ---

class SpatialHash:
    """Grid-based spatial hash for O(N) collision detection."""

    def __init__(self, cell_size: float):
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list[int]] = {}

    def clear(self):
        self.cells.clear()

    def insert(self, block_id: int, position: Vector2):
        cx = int(position.x // self.cell_size)
        cy = int(position.y // self.cell_size)
        self.cells.setdefault((cx, cy), []).append(block_id)

    def query_nearby(self, position: Vector2) -> list[int]:
        cx = int(position.x // self.cell_size)
        cy = int(position.y // self.cell_size)
        result = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = self.cells.get((cx + dx, cy + dy))
                if cell:
                    result.extend(cell)
        return result


# --- Mobility ---

def compute_molecule_mobility(molecule, blocks: dict, penalty: float) -> float:
    """Molecule mobility = avg(block mobilities) - penalty * N, min 0.01."""
    avg = sum(blocks[bid].mobility for bid in molecule.block_ids) / molecule.n
    return max(0.01, avg - penalty * molecule.n)


# --- Movement ---

def move_all(state: SimulationState):
    """Move all entities by their velocities. Free blocks, then molecules."""
    config = state.config
    sim_width = state.gfx.window_width - 200  # legend panel width

    # Track which molecules we've already moved (avoid double-moving)
    moved_molecules = set()

    for block in state.blocks.values():
        if block.molecule_id is not None:
            if block.molecule_id not in moved_molecules:
                moved_molecules.add(block.molecule_id)
                _move_molecule(state, state.molecules[block.molecule_id], sim_width)
        else:
            # Free block
            speed = block.mobility * config.speed_scale
            if block.velocity.length_squared() > 0:
                block.velocity = block.velocity.normalize() * speed
            block.position += block.velocity
            _wall_bounce_block(block, config, state.gfx, sim_width)


def _move_molecule(state: SimulationState, molecule, sim_width: float):
    """Move a molecule as a rigid body."""
    config = state.config
    mobility = compute_molecule_mobility(molecule, state.blocks, config.molec_mobility_penalty)
    speed = mobility * config.speed_scale
    if molecule.velocity.length_squared() > 0:
        molecule.velocity = molecule.velocity.normalize() * speed

    anchor = state.blocks[molecule.anchor_block_id]
    anchor.position += molecule.velocity

    # Wall bounce checking all blocks
    _wall_bounce_molecule(molecule, state, sim_width)

    # Reposition all blocks from anchor
    for bid in molecule.block_ids:
        state.blocks[bid].position = Vector2(anchor.position) + molecule.offsets[bid]


def _wall_bounce_block(block, config, gfx, sim_width: float):
    """Bounce a free block off walls."""
    r = config.block_radius
    h = gfx.window_height

    if block.position.x < r:
        block.position.x = r
        block.velocity.x = abs(block.velocity.x)
    elif block.position.x > sim_width - r:
        block.position.x = sim_width - r
        block.velocity.x = -abs(block.velocity.x)

    if block.position.y < r:
        block.position.y = r
        block.velocity.y = abs(block.velocity.y)
    elif block.position.y > h - r:
        block.position.y = h - r
        block.velocity.y = -abs(block.velocity.y)


def _wall_bounce_molecule(molecule, state: SimulationState, sim_width: float):
    """Bounce a molecule off walls, checking all constituent blocks."""
    config = state.config
    r = config.block_radius
    h = state.gfx.window_height
    anchor = state.blocks[molecule.anchor_block_id]

    for bid in molecule.block_ids:
        pos = Vector2(anchor.position) + molecule.offsets[bid]

        if pos.x < r:
            anchor.position.x += (r - pos.x)
            molecule.velocity.x = abs(molecule.velocity.x)
        elif pos.x > sim_width - r:
            anchor.position.x -= (pos.x - (sim_width - r))
            molecule.velocity.x = -abs(molecule.velocity.x)

        if pos.y < r:
            anchor.position.y += (r - pos.y)
            molecule.velocity.y = abs(molecule.velocity.y)
        elif pos.y > h - r:
            anchor.position.y -= (pos.y - (h - r))
            molecule.velocity.y = -abs(molecule.velocity.y)


# --- Collision Detection ---

def update_spatial_hash(state: SimulationState, spatial_hash: SpatialHash):
    """Rebuild spatial hash from current block positions."""
    spatial_hash.clear()
    for block_id, block in state.blocks.items():
        spatial_hash.insert(block_id, block.position)


def detect_collisions(state: SimulationState, spatial_hash: SpatialHash) -> list[tuple[int, int]]:
    """Find all colliding block pairs from different rigid groups."""
    collisions = []
    bond_length = state.config.bond_length

    for block_id, block in state.blocks.items():
        nearby = spatial_hash.query_nearby(block.position)
        for other_id in nearby:
            if other_id <= block_id:
                continue  # skip self and deduplicate

            other = state.blocks[other_id]

            # Skip same molecule
            if block.molecule_id is not None and block.molecule_id == other.molecule_id:
                continue

            # Skip same assembly (Phase 2)
            if block.assembly_id is not None and block.assembly_id == other.assembly_id:
                continue

            dist_sq = (block.position - other.position).length_squared()
            if dist_sq < bond_length * bond_length:
                collisions.append((block_id, other_id))

    return collisions


# --- Deflection ---

def deflect(state: SimulationState, a_id: int, b_id: int):
    """Elastic collision response between two entities that don't bond."""
    from src.entities import get_entity_velocity, set_entity_velocity, shift_entity

    a = state.blocks[a_id]
    b = state.blocks[b_id]

    normal = b.position - a.position
    if normal.length_squared() == 0:
        normal = Vector2(1, 0)
    else:
        normal = normal.normalize()

    vel_a = Vector2(get_entity_velocity(state, a_id))
    vel_b = Vector2(get_entity_velocity(state, b_id))

    rel_vel = vel_a - vel_b
    vel_along_normal = rel_vel.dot(normal)

    if vel_along_normal <= 0:
        return  # already moving apart

    impulse = normal * vel_along_normal
    set_entity_velocity(state, a_id, vel_a - impulse)
    set_entity_velocity(state, b_id, vel_b + impulse)

    # Separate overlapping entities
    dist = a.position.distance_to(b.position)
    if dist < state.config.bond_length:
        overlap = state.config.bond_length - dist
        sep = normal * (overlap / 2 + 0.5)
        shift_entity(state, a_id, -sep)
        shift_entity(state, b_id, sep)
