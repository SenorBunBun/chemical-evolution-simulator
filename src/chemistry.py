from __future__ import annotations

import logging
import random

from pygame.math import Vector2

from src.entities import (
    Bond, Molecule, SimulationState,
    can_bond, get_entity_velocity,
)
from src.id_gen import IdGen
from src.physics import compute_molecule_mobility, deflect

logger = logging.getLogger(__name__)


# --- Collision Handling ---

def handle_collisions(state: SimulationState, collisions: list[tuple[int, int]], id_gen: IdGen):
    """Process all collision pairs: attempt bonds or deflect."""
    for a_id, b_id in collisions:
        # Blocks may have been absorbed into molecules during this tick
        if a_id not in state.blocks or b_id not in state.blocks:
            continue

        a = state.blocks[a_id]
        b = state.blocks[b_id]

        # Skip if now in the same molecule (could happen after earlier merge this tick)
        if a.molecule_id is not None and a.molecule_id == b.molecule_id:
            continue

        both_can_bond = can_bond(state, a_id) and can_bond(state, b_id)

        if both_can_bond:
            prob = (a.formation_reactivity + b.formation_reactivity) / 2
            roll = random.random()
            if roll < prob:
                logger.debug(
                    f"[TICK {state.tick}] BOND FORMED: Block {a_id} + Block {b_id} "
                    f"(prob={prob:.2f}, rolled={roll:.2f})"
                )
                form_bond(state, a_id, b_id, id_gen)
                continue
            else:
                logger.debug(
                    f"[TICK {state.tick}] BOND FAILED: Block {a_id} + Block {b_id} "
                    f"(prob={prob:.2f}, rolled={roll:.2f})"
                )

        # No bond formed -> deflect
        deflect(state, a_id, b_id)


# --- Bond Formation ---

def form_bond(state: SimulationState, a_id: int, b_id: int, id_gen: IdGen):
    """Create a bond between two blocks and handle molecule creation/merging."""
    bond = Bond(id=id_gen.next(), block_a_id=a_id, block_b_id=b_id)
    state.bonds[bond.id] = bond
    state.blocks[a_id].bond_ids.append(bond.id)
    state.blocks[b_id].bond_ids.append(bond.id)

    a_mol = state.blocks[a_id].molecule_id
    b_mol = state.blocks[b_id].molecule_id

    if a_mol is None and b_mol is None:
        _create_molecule_from_pair(state, a_id, b_id, id_gen)
    elif a_mol is None:
        _add_block_to_molecule(state, a_id, b_mol, b_id)
    elif b_mol is None:
        _add_block_to_molecule(state, b_id, a_mol, a_id)
    else:
        _merge_molecules(state, a_mol, b_mol, a_id, b_id, id_gen)


def _create_molecule_from_pair(state: SimulationState, a_id: int, b_id: int, id_gen: IdGen):
    """Two free blocks -> new molecule."""
    config = state.config
    a = state.blocks[a_id]
    b = state.blocks[b_id]

    # Direction from A to B, normalized to bond_length
    direction = b.position - a.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    # Snap B to exact bond_length from A
    b.position = Vector2(a.position) + direction * config.bond_length

    offsets = {
        a_id: Vector2(0, 0),
        b_id: Vector2(direction * config.bond_length),
    }

    # Velocity: weighted average (both weight 1), rescaled
    combined_vel = (a.velocity + b.velocity) / 2

    mol = Molecule(
        id=id_gen.next(),
        block_ids=[a_id, b_id],
        anchor_block_id=a_id,
        offsets=offsets,
        velocity=combined_vel,
    )

    # Rescale velocity to new mobility
    mobility = compute_molecule_mobility(mol, state.blocks, config.molec_mobility_penalty)
    if mol.velocity.length_squared() > 0:
        mol.velocity = mol.velocity.normalize() * mobility * config.speed_scale

    state.molecules[mol.id] = mol
    a.molecule_id = mol.id
    b.molecule_id = mol.id

    logger.debug(f"  -> Created Molecule {mol.id} ({mol.n} blocks)")


def _add_block_to_molecule(state: SimulationState, free_id: int, mol_id: int, bonded_to_id: int):
    """Add a free block to an existing molecule."""
    config = state.config
    free_block = state.blocks[free_id]
    bonded_block = state.blocks[bonded_to_id]
    molecule = state.molecules[mol_id]
    anchor = state.blocks[molecule.anchor_block_id]

    # Direction from bonded block toward free block
    direction = free_block.position - bonded_block.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    # Free block's offset = bonded block's offset + direction * bond_length
    free_offset = Vector2(molecule.offsets[bonded_to_id]) + direction * config.bond_length

    # Snap free block position
    free_block.position = Vector2(anchor.position) + free_offset

    # Add to molecule
    molecule.block_ids.append(free_id)
    molecule.offsets[free_id] = free_offset
    free_block.molecule_id = mol_id

    # Blend velocity: incorporate free block's velocity weighted 1/N
    old_n = molecule.n - 1  # before adding
    combined = (molecule.velocity * old_n + free_block.velocity) / molecule.n

    # Rescale to new mobility
    mobility = compute_molecule_mobility(molecule, state.blocks, config.molec_mobility_penalty)
    if combined.length_squared() > 0:
        molecule.velocity = combined.normalize() * mobility * config.speed_scale
    else:
        molecule.velocity = Vector2(0, 0)

    logger.debug(f"  -> Block {free_id} joined Molecule {mol_id} (now {molecule.n} blocks)")


def _merge_molecules(
    state: SimulationState,
    mol_a_id: int, mol_b_id: int,
    connect_a_id: int, connect_b_id: int,
    id_gen: IdGen,
):
    """Merge two molecules into one via a bond between connect_a and connect_b."""
    config = state.config
    mol_a = state.molecules[mol_a_id]
    mol_b = state.molecules[mol_b_id]

    # Keep larger molecule as base
    if mol_b.n > mol_a.n:
        mol_a, mol_b = mol_b, mol_a
        mol_a_id, mol_b_id = mol_b_id, mol_a_id
        connect_a_id, connect_b_id = connect_b_id, connect_a_id

    base = mol_a
    absorbed = mol_b
    base_anchor = state.blocks[base.anchor_block_id]

    # Direction from connect_a to connect_b, normalized to bond_length
    ca = state.blocks[connect_a_id]
    cb = state.blocks[connect_b_id]
    direction = cb.position - ca.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    # For each block in absorbed: compute new offset relative to base anchor
    # new_offset = base.offsets[connect_a] + direction * bond_length + (absorbed.offsets[block] - absorbed.offsets[connect_b])
    connect_a_offset = base.offsets[connect_a_id]
    connect_b_offset = absorbed.offsets[connect_b_id]
    bridge = connect_a_offset + direction * config.bond_length

    for bid in absorbed.block_ids:
        new_offset = bridge + (absorbed.offsets[bid] - connect_b_offset)
        base.offsets[bid] = new_offset
        base.block_ids.append(bid)
        state.blocks[bid].molecule_id = base.id

    # Velocity: weighted average by block count
    n_base_orig = base.n - absorbed.n  # base's original count (before append)
    combined = (base.velocity * n_base_orig + absorbed.velocity * absorbed.n) / base.n
    mobility = compute_molecule_mobility(base, state.blocks, config.molec_mobility_penalty)
    if combined.length_squared() > 0:
        base.velocity = combined.normalize() * mobility * config.speed_scale
    else:
        base.velocity = Vector2(0, 0)

    # Snap all block positions
    for bid in base.block_ids:
        state.blocks[bid].position = Vector2(base_anchor.position) + base.offsets[bid]

    # Remove absorbed molecule
    del state.molecules[mol_b_id]

    logger.debug(
        f"  -> Molecules {mol_a_id} + {mol_b_id} merged into {base.id} ({base.n} blocks)"
    )


# --- Bond Breaking (Hydrolysis) ---

def hydrolysis_step(state: SimulationState, id_gen: IdGen):
    """Check all bonds for breaking. Called every hydrolysis_interval ticks."""
    bonds_to_break = []

    for bond in list(state.bonds.values()):
        if bond.is_h_bond:
            continue  # H-bonds don't break via hydrolysis

        a = state.blocks[bond.block_a_id]
        b = state.blocks[bond.block_b_id]
        break_prob = (a.breaking_reactivity + b.breaking_reactivity) / 2

        # Phase 2: assembly protection would reduce break_prob here

        roll = random.random()
        if roll < break_prob:
            bonds_to_break.append(bond.id)
            logger.debug(
                f"[TICK {state.tick}] BOND BREAK: Bond {bond.id} "
                f"(Block {bond.block_a_id} - Block {bond.block_b_id}, "
                f"prob={break_prob:.2f}, rolled={roll:.2f})"
            )

    for bond_id in bonds_to_break:
        if bond_id in state.bonds:  # may have been removed by prior break
            _break_bond(state, bond_id, id_gen)


def _break_bond(state: SimulationState, bond_id: int, id_gen: IdGen):
    """Remove a bond and split the molecule."""
    bond = state.bonds.pop(bond_id)
    a = state.blocks[bond.block_a_id]
    b = state.blocks[bond.block_b_id]

    a.bond_ids.remove(bond_id)
    b.bond_ids.remove(bond_id)

    mol_id = a.molecule_id
    if mol_id is None:
        return  # safety check

    molecule = state.molecules[mol_id]
    _split_molecule(state, molecule, bond.block_a_id, bond.block_b_id, id_gen)


def _split_molecule(
    state: SimulationState,
    molecule: Molecule,
    break_a_id: int, break_b_id: int,
    id_gen: IdGen,
):
    """Split a molecule into two fragments after a bond break."""
    config = state.config

    frag_a_ids = _walk_chain(state, break_a_id, exclude_neighbor=break_b_id)
    frag_b_ids = _walk_chain(state, break_b_id, exclude_neighbor=break_a_id)

    old_vel = molecule.velocity
    old_vel_dir = old_vel.normalize() if old_vel.length_squared() > 0 else Vector2(1, 0)

    # Delete old molecule
    del state.molecules[molecule.id]

    for frag_ids in (frag_a_ids, frag_b_ids):
        if len(frag_ids) == 1:
            # Becomes a free block
            bid = frag_ids[0]
            block = state.blocks[bid]
            block.molecule_id = None
            perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
            direction = old_vel_dir + perturbation
            if direction.length_squared() > 0:
                direction = direction.normalize()
            else:
                direction = Vector2(1, 0)
            block.velocity = direction * block.mobility * config.speed_scale
            logger.debug(f"  -> Block {bid} became free")
        else:
            # Create new molecule
            anchor_id = frag_ids[0]
            anchor_pos = state.blocks[anchor_id].position
            offsets = {}
            for bid in frag_ids:
                offsets[bid] = Vector2(state.blocks[bid].position) - Vector2(anchor_pos)

            new_mol = Molecule(
                id=id_gen.next(),
                block_ids=list(frag_ids),
                anchor_block_id=anchor_id,
                offsets=offsets,
                velocity=Vector2(0, 0),
            )

            mobility = compute_molecule_mobility(new_mol, state.blocks, config.molec_mobility_penalty)
            perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
            direction = old_vel_dir + perturbation
            if direction.length_squared() > 0:
                direction = direction.normalize()
            else:
                direction = Vector2(1, 0)
            new_mol.velocity = direction * mobility * config.speed_scale

            state.molecules[new_mol.id] = new_mol
            for bid in frag_ids:
                state.blocks[bid].molecule_id = new_mol.id

            logger.debug(f"  -> Fragment -> Molecule {new_mol.id} ({new_mol.n} blocks)")


def _walk_chain(state: SimulationState, start_id: int, exclude_neighbor: int) -> list[int]:
    """Walk a linear chain from start_id, not crossing through exclude_neighbor."""
    visited = [start_id]
    current = start_id
    prev = exclude_neighbor

    while True:
        block = state.blocks[current]
        next_id = None
        for bond_id in block.bond_ids:
            bond = state.bonds[bond_id]
            neighbor = bond.block_b_id if bond.block_a_id == current else bond.block_a_id
            if neighbor != prev:
                next_id = neighbor
                break
        if next_id is None:
            break
        visited.append(next_id)
        prev = current
        current = next_id

    return visited
