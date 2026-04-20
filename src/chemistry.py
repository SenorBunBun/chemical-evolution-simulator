from __future__ import annotations

import logging
import math
import random

from pygame.math import Vector2

from src.entities import (
    Assembly, Bond, BuildingBlock, HBondType, Molecule, SimulationState,
    can_bond, get_entity_velocity,
)
from src.id_gen import IdGen
from src.physics import compute_molecule_mobility, deflect

logger = logging.getLogger(__name__)


# --- H-Bond Matching ---

def _all_opposite(state, a_ids, b_ids) -> bool:
    """True if every position has opposite H-bond types."""
    return all(
        state.blocks[a].h_bond_type != state.blocks[b].h_bond_type
        for a, b in zip(a_ids, b_ids)
    )


def check_hbond_match(state: SimulationState, mol_a_id: int, mol_b_id: int) -> bool:
    """Check if two molecules have full donor-acceptor H-bond correspondence.

    Requires same length and opposite H-bond types at every position.
    Checks both forward and reversed alignment of mol_b.
    """
    mol_a = state.molecules[mol_a_id]
    mol_b = state.molecules[mol_b_id]
    if mol_a.n != mol_b.n:
        return False
    if _all_opposite(state, mol_a.block_ids, mol_b.block_ids):
        return True
    if _all_opposite(state, mol_a.block_ids, list(reversed(mol_b.block_ids))):
        return True
    return False


def _align_for_hbond(state: SimulationState, mol_a: 'Molecule', mol_b: 'Molecule'):
    """Reverse mol_b's block_ids if needed so positions align donor-to-acceptor.

    Call this before creating H-bonds between the two molecules.
    """
    if _all_opposite(state, mol_a.block_ids, mol_b.block_ids):
        return  # already aligned
    if _all_opposite(state, mol_a.block_ids, list(reversed(mol_b.block_ids))):
        mol_b.block_ids = list(reversed(mol_b.block_ids))
        mol_b.anchor_block_id = mol_b.block_ids[0]


def _compute_assembly_chance(config, n_a: int, n_b: int, m: int) -> float:
    """P_assembly = base_chance * (min(N_a, N_b) / min_n) * (1 + growth_bonus * M)."""
    return (config.base_assembly_chance
            * (min(n_a, n_b) / config.min_assembly_n)
            * (1 + config.assembly_growth_bonus * m))


def _get_hbond_neighbors(state: SimulationState, mol_id: int, assembly: Assembly) -> set[int]:
    """Get molecule IDs that mol_id is H-bonded to within the assembly."""
    mol_blocks = set(state.molecules[mol_id].block_ids)
    neighbors = set()
    for hb_id in assembly.h_bond_ids:
        if hb_id not in state.bonds:
            continue
        bond = state.bonds[hb_id]
        if bond.block_a_id in mol_blocks:
            other = state.blocks[bond.block_b_id]
            if other.molecule_id is not None and other.molecule_id != mol_id:
                neighbors.add(other.molecule_id)
        elif bond.block_b_id in mol_blocks:
            other = state.blocks[bond.block_a_id]
            if other.molecule_id is not None and other.molecule_id != mol_id:
                neighbors.add(other.molecule_id)
    return neighbors


def _block_has_hbond(state: SimulationState, block_id: int) -> bool:
    """Check if a block participates in any H-bond within its assembly."""
    block = state.blocks[block_id]
    if block.assembly_id is None:
        return False
    asm = state.assemblies[block.assembly_id]
    for hb_id in asm.h_bond_ids:
        if hb_id not in state.bonds:
            continue
        bond = state.bonds[hb_id]
        if bond.block_a_id == block_id or bond.block_b_id == block_id:
            return True
    return False


# --- Assembly Formation & Management ---

def _flatten_molecule(molecule: Molecule, bond_length: float):
    """Re-lay a molecule's offsets horizontally (block_ids[0] at origin)."""
    for i, bid in enumerate(molecule.block_ids):
        molecule.offsets[bid] = Vector2(i * bond_length, 0)


def _reposition_assembly(state: SimulationState, assembly: Assembly):
    """Snap all block positions from assembly and molecule offsets."""
    anchor_mol = state.molecules[assembly.anchor_molecule_id]
    asm_anchor_pos = state.blocks[anchor_mol.anchor_block_id].position

    for mid in assembly.molecule_ids:
        mol = state.molecules[mid]
        mol_anchor_pos = Vector2(asm_anchor_pos) + assembly.offsets[mid]
        state.blocks[mol.anchor_block_id].position = Vector2(mol_anchor_pos)
        for bid in mol.block_ids:
            state.blocks[bid].position = Vector2(mol_anchor_pos) + mol.offsets[bid]


def _recompute_assembly_offsets(state: SimulationState, assembly: Assembly):
    """Recompute assembly offsets from current block positions."""
    anchor_mol = state.molecules[assembly.anchor_molecule_id]
    asm_anchor_pos = state.blocks[anchor_mol.anchor_block_id].position
    for mid in assembly.molecule_ids:
        mol = state.molecules[mid]
        mol_anchor_pos = state.blocks[mol.anchor_block_id].position
        assembly.offsets[mid] = Vector2(mol_anchor_pos) - Vector2(asm_anchor_pos)


def _form_assembly(state: SimulationState, mol_a_id: int, mol_b_id: int, id_gen: IdGen):
    """Create a new assembly from two molecules with matching H-bond types."""
    bond_length = state.gfx.bond_length
    config = state.config
    mol_a = state.molecules[mol_a_id]
    mol_b = state.molecules[mol_b_id]

    # Align mol_b so donor-acceptor pairs match, then flatten horizontally
    _align_for_hbond(state, mol_a, mol_b)
    _flatten_molecule(mol_a, bond_length)
    _flatten_molecule(mol_b, bond_length)

    # Assembly offsets: mol_a at origin, mol_b one bond_length below
    asm_offsets = {
        mol_a_id: Vector2(0, 0),
        mol_b_id: Vector2(0, bond_length),
    }

    # Create H-bonds between corresponding block pairs
    h_bond_ids = []
    for a_bid, b_bid in zip(mol_a.block_ids, mol_b.block_ids):
        hbond = Bond(id=id_gen.next(), block_a_id=a_bid, block_b_id=b_bid, is_h_bond=True)
        state.bonds[hbond.id] = hbond
        h_bond_ids.append(hbond.id)

    # Combined velocity (weighted by block count)
    n_a, n_b = mol_a.n, mol_b.n
    combined_vel = (mol_a.velocity * n_a + mol_b.velocity * n_b) / (n_a + n_b)

    asm = Assembly(
        id=id_gen.next(),
        molecule_ids=[mol_a_id, mol_b_id],
        h_bond_ids=h_bond_ids,
        anchor_molecule_id=mol_a_id,
        offsets=asm_offsets,
        velocity=combined_vel,
    )

    state.assemblies[asm.id] = asm
    mol_a.assembly_id = asm.id
    mol_b.assembly_id = asm.id
    for bid in mol_a.block_ids:
        state.blocks[bid].assembly_id = asm.id
    for bid in mol_b.block_ids:
        state.blocks[bid].assembly_id = asm.id

    # Snap all positions
    _reposition_assembly(state, asm)

    logger.debug(
        f"[TICK {state.tick}] ASSEMBLY FORMED: Assembly {asm.id} "
        f"(Mol {mol_a_id} + Mol {mol_b_id})"
    )


def _add_to_assembly(
    state: SimulationState, mol_id: int, neighbor_mol_id: int,
    assembly_id: int, id_gen: IdGen,
):
    """Add a molecule to an existing assembly, H-bonding it to neighbor_mol."""
    asm = state.assemblies[assembly_id]
    mol = state.molecules[mol_id]
    neighbor_mol = state.molecules[neighbor_mol_id]
    bond_length = state.gfx.bond_length

    # Align then flatten the new molecule
    _align_for_hbond(state, neighbor_mol, mol)
    _flatten_molecule(mol, bond_length)

    # Determine placement: go to the free side of the neighbor
    neighbor_offset = asm.offsets[neighbor_mol_id]
    neighbors_of_neighbor = _get_hbond_neighbors(state, neighbor_mol_id, asm)

    if neighbors_of_neighbor:
        existing_id = next(iter(neighbors_of_neighbor))
        existing_offset = asm.offsets[existing_id]
        if existing_offset.y < neighbor_offset.y:
            # Existing neighbor is above -> place new molecule below
            new_offset = Vector2(neighbor_offset.x, neighbor_offset.y + bond_length)
        else:
            new_offset = Vector2(neighbor_offset.x, neighbor_offset.y - bond_length)
    else:
        new_offset = Vector2(neighbor_offset.x, neighbor_offset.y + bond_length)

    asm.offsets[mol_id] = new_offset
    asm.molecule_ids.append(mol_id)

    # Create H-bonds between neighbor and new molecule
    for a_bid, b_bid in zip(neighbor_mol.block_ids, mol.block_ids):
        hbond = Bond(id=id_gen.next(), block_a_id=a_bid, block_b_id=b_bid, is_h_bond=True)
        state.bonds[hbond.id] = hbond
        asm.h_bond_ids.append(hbond.id)

    # Set assembly membership
    mol.assembly_id = assembly_id
    for bid in mol.block_ids:
        state.blocks[bid].assembly_id = assembly_id

    # Update velocity (weighted by total block count)
    total_blocks = sum(state.molecules[mid].n for mid in asm.molecule_ids)
    old_blocks = total_blocks - mol.n
    if old_blocks > 0:
        combined = (asm.velocity * old_blocks + mol.velocity * mol.n) / total_blocks
        asm.velocity = combined

    _reposition_assembly(state, asm)

    logger.debug(
        f"[TICK {state.tick}] ASSEMBLY GROW: Mol {mol_id} joined Assembly {assembly_id}"
    )


def _remove_from_assembly(state: SimulationState, mol_id: int, assembly_id: int):
    """Remove a molecule from an assembly."""
    asm = state.assemblies[assembly_id]
    mol = state.molecules[mol_id]
    config = state.config

    # Remove H-bonds involving this molecule's blocks
    mol_blocks = set(mol.block_ids)
    hbonds_to_remove = []
    for hb_id in asm.h_bond_ids:
        if hb_id not in state.bonds:
            continue
        bond = state.bonds[hb_id]
        if bond.block_a_id in mol_blocks or bond.block_b_id in mol_blocks:
            hbonds_to_remove.append(hb_id)
    for hb_id in hbonds_to_remove:
        asm.h_bond_ids.remove(hb_id)
        state.bonds.pop(hb_id, None)

    # Remove from assembly
    asm.molecule_ids.remove(mol_id)
    asm.offsets.pop(mol_id, None)

    # Clear membership
    mol.assembly_id = None
    for bid in mol.block_ids:
        state.blocks[bid].assembly_id = None

    # Give molecule independent velocity
    mobility = compute_molecule_mobility(mol, state.blocks, config.molec_mobility_penalty)
    perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
    direction = asm.velocity + perturbation
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)
    mol.velocity = direction * mobility * config.speed_scale

    # Handle anchor change
    if asm.anchor_molecule_id == mol_id and asm.molecule_ids:
        asm.anchor_molecule_id = asm.molecule_ids[0]
        _recompute_assembly_offsets(state, asm)

    # Check viability and connectivity
    if len(asm.molecule_ids) < 2:
        _dissolve_assembly(state, assembly_id)
    elif assembly_id in state.assemblies:
        _check_assembly_connectivity(state, assembly_id)

    logger.debug(
        f"[TICK {state.tick}] ASSEMBLY REMOVE: Mol {mol_id} left Assembly {assembly_id}"
    )


def _dissolve_assembly(state: SimulationState, assembly_id: int):
    """Dissolve an assembly, freeing all molecules."""
    asm = state.assemblies.pop(assembly_id)
    config = state.config

    # Remove all H-bonds
    for hb_id in asm.h_bond_ids:
        state.bonds.pop(hb_id, None)

    # Free all molecules
    for mid in asm.molecule_ids:
        if mid not in state.molecules:
            continue
        mol = state.molecules[mid]
        mol.assembly_id = None
        for bid in mol.block_ids:
            state.blocks[bid].assembly_id = None

        mobility = compute_molecule_mobility(mol, state.blocks, config.molec_mobility_penalty)
        perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
        direction = asm.velocity + perturbation
        if direction.length_squared() > 0:
            direction = direction.normalize()
        else:
            direction = Vector2(1, 0)
        mol.velocity = direction * mobility * config.speed_scale

    logger.debug(f"[TICK {state.tick}] ASSEMBLY DISSOLVED: Assembly {assembly_id}")


def _update_assembly_after_split(
    state: SimulationState, assembly_id: int,
    old_mol_id: int, new_mol_ids: list[int],
):
    """Update assembly state after a constituent molecule splits."""
    asm = state.assemblies[assembly_id]

    # Replace old mol with fragments
    if old_mol_id in asm.molecule_ids:
        asm.molecule_ids.remove(old_mol_id)
    asm.molecule_ids.extend(new_mol_ids)
    asm.offsets.pop(old_mol_id, None)

    # Handle anchor change
    if asm.anchor_molecule_id == old_mol_id:
        if new_mol_ids:
            asm.anchor_molecule_id = new_mol_ids[0]
        elif asm.molecule_ids:
            asm.anchor_molecule_id = asm.molecule_ids[0]

    # Recompute offsets from current positions
    if asm.molecule_ids:
        _recompute_assembly_offsets(state, asm)

    # Clean H-bonds: remove any referencing blocks no longer in assembly
    valid = []
    for hb_id in asm.h_bond_ids:
        if hb_id not in state.bonds:
            continue
        bond = state.bonds[hb_id]
        a = state.blocks.get(bond.block_a_id)
        b = state.blocks.get(bond.block_b_id)
        if a and b and a.assembly_id == assembly_id and b.assembly_id == assembly_id:
            valid.append(hb_id)
        else:
            state.bonds.pop(hb_id, None)
    asm.h_bond_ids = valid

    # Dissolve if < 2 molecules remain
    if len(asm.molecule_ids) < 2:
        _dissolve_assembly(state, assembly_id)
    elif assembly_id in state.assemblies:
        # Check if assembly is still connected
        _check_assembly_connectivity(state, assembly_id)


def _check_assembly_connectivity(state: SimulationState, assembly_id: int):
    """Check if an assembly's molecules are still connected via H-bonds.

    If the assembly has split into disconnected groups, split into
    separate assemblies (or dissolve groups that are too small).
    Only called after a molecule split or removal — not every tick.
    """
    if assembly_id not in state.assemblies:
        return
    asm = state.assemblies[assembly_id]

    # 2 molecules can't split further (already handled by < 2 check)
    if len(asm.molecule_ids) <= 2:
        return

    # Build adjacency: which molecules are connected by H-bonds?
    neighbors: dict[int, set[int]] = {mid: set() for mid in asm.molecule_ids}
    for hb_id in asm.h_bond_ids:
        if hb_id not in state.bonds:
            continue
        bond = state.bonds[hb_id]
        a_block = state.blocks.get(bond.block_a_id)
        b_block = state.blocks.get(bond.block_b_id)
        if not a_block or not b_block:
            continue
        mol_a = a_block.molecule_id
        mol_b = b_block.molecule_id
        if mol_a in neighbors and mol_b in neighbors and mol_a != mol_b:
            neighbors[mol_a].add(mol_b)
            neighbors[mol_b].add(mol_a)

    # BFS from the first molecule to find connected component
    start = asm.molecule_ids[0]
    visited = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for nbr in neighbors.get(current, set()):
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)

    # All connected — nothing to do
    if len(visited) == len(asm.molecule_ids):
        return

    # Assembly has split — find all connected components
    remaining = set(asm.molecule_ids) - visited
    components = [visited]
    while remaining:
        start = next(iter(remaining))
        component = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for nbr in neighbors.get(current, set()):
                if nbr not in component and nbr in remaining:
                    component.add(nbr)
                    queue.append(nbr)
        components.append(component)
        remaining -= component

    logger.debug(
        f"[TICK {state.tick}] ASSEMBLY SPLIT: Assembly {assembly_id} "
        f"split into {len(components)} groups: {[len(c) for c in components]}"
    )

    # Save H-bonds before dissolving (dissolve deletes them from state.bonds)
    saved_hbonds = {}
    for hb_id in asm.h_bond_ids:
        if hb_id in state.bonds:
            saved_hbonds[hb_id] = state.bonds[hb_id]

    # Dissolve the original assembly (frees all molecules, removes H-bonds)
    _dissolve_assembly(state, assembly_id)

    # Re-form assemblies for groups with >= 2 molecules
    # (single-molecule groups stay free from _dissolve_assembly)
    for component in components:
        if len(component) < 2:
            continue

        mol_list = list(component)
        # Restore H-bonds that connect molecules in this component
        comp_hbonds = []
        for hb_id, bond in saved_hbonds.items():
            a_block = state.blocks.get(bond.block_a_id)
            b_block = state.blocks.get(bond.block_b_id)
            if not a_block or not b_block:
                continue
            if a_block.molecule_id in component and b_block.molecule_id in component:
                state.bonds[hb_id] = bond  # re-add to state
                comp_hbonds.append(hb_id)

        if not comp_hbonds:
            # No H-bonds left — just leave them free
            continue

        # Create new assembly from this component
        new_asm_id = state.id_gen.next()

        anchor_mid = mol_list[0]
        anchor_mol = state.molecules[anchor_mid]
        anchor_pos = state.blocks[anchor_mol.anchor_block_id].position

        offsets = {}
        for mid in mol_list:
            mol = state.molecules[mid]
            mol_pos = state.blocks[mol.anchor_block_id].position
            offsets[mid] = Vector2(mol_pos) - Vector2(anchor_pos)

        new_asm = Assembly(
            id=new_asm_id,
            molecule_ids=mol_list,
            h_bond_ids=comp_hbonds,
            anchor_molecule_id=anchor_mid,
            offsets=offsets,
            velocity=Vector2(anchor_mol.velocity),
        )
        state.assemblies[new_asm_id] = new_asm

        for mid in mol_list:
            mol = state.molecules[mid]
            mol.assembly_id = new_asm_id
            mol.velocity = Vector2(new_asm.velocity)
            for bid in mol.block_ids:
                state.blocks[bid].assembly_id = new_asm_id

        logger.debug(
            f"[TICK {state.tick}] ASSEMBLY RE-FORMED: Assembly {new_asm_id} "
            f"with {len(mol_list)} molecules, {len(comp_hbonds)} H-bonds"
        )


# --- Collision Handling ---

def handle_collisions(state: SimulationState, collisions: list[tuple[int, int]], id_gen: IdGen):
    """Process all collision pairs: attempt bonds, assemblies, or deflect."""
    config = state.config

    for a_id, b_id in collisions:
        if a_id not in state.blocks or b_id not in state.blocks:
            continue

        a = state.blocks[a_id]
        b = state.blocks[b_id]

        if a.molecule_id is not None and a.molecule_id == b.molecule_id:
            continue

        # Blocks in assemblies cannot form new covalent bonds
        both_can_bond = (can_bond(state, a_id) and can_bond(state, b_id)
                         and a.assembly_id is None and b.assembly_id is None)

        # --- Assembly eligibility check ---
        assembly_action = None
        if config.assembly_enabled:
            assembly_action = _check_assembly_eligibility(state, a, b, config)

        if assembly_action is not None:
            acted = _handle_assembly_collision(
                state, a_id, b_id, a, b, assembly_action,
                both_can_bond, id_gen,
            )
            if acted:
                continue

        # --- Regular bond formation ---
        if both_can_bond:
            prob = (a.formation_reactivity + b.formation_reactivity) / 2
            # Phase 3: Catalysis bonus per bond (stacks across catalysts)
            prob = min(1.0, prob + get_bond_catalysis_bonus(state, a_id, b_id))
            roll = random.random()
            if roll < prob:
                logger.debug(
                    f"[TICK {state.tick}] BOND FORMED: Block {a_id} + Block {b_id} "
                    f"(prob={prob:.2f}, rolled={roll:.2f})"
                )
                form_bond(state, a_id, b_id, id_gen)
                continue

        deflect(state, a_id, b_id)


def _check_assembly_eligibility(state, a, b, config):
    """Check if an assembly action is possible. Returns action dict or None."""
    a_mol_id = a.molecule_id
    b_mol_id = b.molecule_id

    if a_mol_id is None or b_mol_id is None:
        return None
    if a_mol_id not in state.molecules or b_mol_id not in state.molecules:
        return None

    a_in_asm = a.assembly_id is not None
    b_in_asm = b.assembly_id is not None

    mol_a = state.molecules[a_mol_id]
    mol_b = state.molecules[b_mol_id]

    if mol_a.n < config.min_assembly_n or mol_b.n < config.min_assembly_n:
        return None
    if not check_hbond_match(state, a_mol_id, b_mol_id):
        return None

    # Both in different assemblies: pull molecule from smaller assembly into larger
    if a_in_asm and b_in_asm:
        if a.assembly_id == b.assembly_id:
            return None  # same assembly, nothing to do
        asm_a = state.assemblies[a.assembly_id]
        asm_b = state.assemblies[b.assembly_id]
        # Molecule from smaller assembly joins the larger one
        if len(asm_a.molecule_ids) >= len(asm_b.molecule_ids):
            return {"type": "transfer", "target_asm_id": a.assembly_id,
                    "target_mol_id": a_mol_id,
                    "source_asm_id": b.assembly_id, "source_mol_id": b_mol_id}
        else:
            return {"type": "transfer", "target_asm_id": b.assembly_id,
                    "target_mol_id": b_mol_id,
                    "source_asm_id": a.assembly_id, "source_mol_id": a_mol_id}

    if a_in_asm:
        return {"type": "join", "asm_mol_id": a_mol_id, "free_mol_id": b_mol_id,
                "asm_id": a.assembly_id}
    elif b_in_asm:
        return {"type": "join", "asm_mol_id": b_mol_id, "free_mol_id": a_mol_id,
                "asm_id": b.assembly_id}
    else:
        return {"type": "new", "mol_a_id": a_mol_id, "mol_b_id": b_mol_id}


def _handle_assembly_collision(state, a_id, b_id, a, b, action, both_can_bond, id_gen):
    """Handle assembly-related collision. Returns True if an action was taken."""
    config = state.config

    if action["type"] == "transfer":
        # Merge: pull all molecules from source assembly into target
        target_asm_id = action["target_asm_id"]
        target_mol_id = action["target_mol_id"]
        source_asm_id = action["source_asm_id"]
        source_mol_id = action["source_mol_id"]

        if (target_asm_id not in state.assemblies
                or source_asm_id not in state.assemblies
                or target_mol_id not in state.molecules
                or source_mol_id not in state.molecules):
            return False

        target_asm = state.assemblies[target_asm_id]
        M = len(target_asm.molecule_ids)
        p_asm = _compute_assembly_chance(
            config, state.molecules[target_mol_id].n,
            state.molecules[source_mol_id].n, M)

        if random.random() < p_asm:
            # Collect all molecules from source before dissolving
            source_asm = state.assemblies[source_asm_id]
            source_mols = list(source_asm.molecule_ids)
            _dissolve_assembly(state, source_asm_id)

            # Add each source molecule to target
            for mol_id in source_mols:
                if (mol_id not in state.molecules
                        or target_asm_id not in state.assemblies):
                    continue
                mol = state.molecules[mol_id]
                if mol.n < config.min_assembly_n:
                    continue
                if not check_hbond_match(state, target_mol_id, mol_id):
                    continue
                _add_to_assembly(state, mol_id, target_mol_id, target_asm_id, id_gen)

            # Catalysis roll once on the final merged assembly
            if target_asm_id in state.assemblies:
                try_catalysis_roll(state, state.assemblies[target_asm_id])
            return True
        return False

    elif action["type"] == "join":
        asm_mol_id = action["asm_mol_id"]
        free_mol_id = action["free_mol_id"]
        asm_id = action["asm_id"]

        # Safety: verify still valid
        if (asm_id not in state.assemblies
                or asm_mol_id not in state.molecules
                or free_mol_id not in state.molecules):
            return False

        asm = state.assemblies[asm_id]
        neighbors = _get_hbond_neighbors(state, asm_mol_id, asm)

        if len(neighbors) >= 2:
            # Displacement rule: incoming replaces smallest neighbor
            free_mol = state.molecules[free_mol_id]
            smallest_id = min(neighbors, key=lambda mid: state.molecules[mid].n)
            if free_mol.n > state.molecules[smallest_id].n:
                _remove_from_assembly(state, smallest_id, asm_id)
                if asm_id in state.assemblies:
                    _add_to_assembly(state, free_mol_id, asm_mol_id, asm_id, id_gen)
                    try_catalysis_roll(state, state.assemblies[asm_id])
                else:
                    _form_assembly(state, asm_mol_id, free_mol_id, id_gen)
                    # Find the newly formed assembly for the roll
                    new_asm_id = state.blocks[state.molecules[asm_mol_id].block_ids[0]].assembly_id
                    if new_asm_id and new_asm_id in state.assemblies:
                        try_catalysis_roll(state, state.assemblies[new_asm_id])
                return True
            return False  # displacement failed

        # Simple join
        M = len(asm.molecule_ids)
        p_asm = _compute_assembly_chance(
            config, state.molecules[asm_mol_id].n,
            state.molecules[free_mol_id].n, M)

        def _join_and_roll():
            _add_to_assembly(state, free_mol_id, asm_mol_id, asm_id, id_gen)
            if asm_id in state.assemblies:
                try_catalysis_roll(state, state.assemblies[asm_id])

        return _attempt_weighted_outcome(
            state, a_id, b_id, a, b, both_can_bond, p_asm,
            _join_and_roll, id_gen,
        )

    else:  # "new"
        mol_a_id = action["mol_a_id"]
        mol_b_id = action["mol_b_id"]
        if mol_a_id not in state.molecules or mol_b_id not in state.molecules:
            return False

        mol_a = state.molecules[mol_a_id]
        mol_b = state.molecules[mol_b_id]
        p_asm = _compute_assembly_chance(config, mol_a.n, mol_b.n, 0)

        def _form_and_roll():
            _form_assembly(state, mol_a_id, mol_b_id, id_gen)
            new_asm_id = state.blocks[state.molecules[mol_a_id].block_ids[0]].assembly_id
            if new_asm_id and new_asm_id in state.assemblies:
                try_catalysis_roll(state, state.assemblies[new_asm_id])

        return _attempt_weighted_outcome(
            state, a_id, b_id, a, b, both_can_bond, p_asm,
            _form_and_roll, id_gen,
        )


def _attempt_weighted_outcome(state, a_id, b_id, a, b, both_can_bond, p_asm, asm_fn, id_gen):
    """Weighted random between bond and assembly, then roll for success."""
    if both_can_bond:
        w_bond = (a.formation_reactivity + b.formation_reactivity) / 2
        total = w_bond + p_asm
        if total <= 0:
            return False

        if random.random() < p_asm / total:
            # Assembly path chosen
            if random.random() < p_asm:
                asm_fn()
                return True
        else:
            # Bond path chosen
            if random.random() < w_bond:
                logger.debug(
                    f"[TICK {state.tick}] BOND FORMED: Block {a_id} + Block {b_id} "
                    f"(weighted assembly/bond)"
                )
                form_bond(state, a_id, b_id, id_gen)
                return True
    else:
        # Only assembly possible
        if random.random() < p_asm:
            asm_fn()
            return True

    return False


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

    direction = b.position - a.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    b.position = Vector2(a.position) + direction * state.gfx.bond_length

    offsets = {
        a_id: Vector2(0, 0),
        b_id: Vector2(direction * state.gfx.bond_length),
    }

    combined_vel = (a.velocity + b.velocity) / 2

    mol = Molecule(
        id=id_gen.next(),
        block_ids=[a_id, b_id],
        anchor_block_id=a_id,
        offsets=offsets,
        velocity=combined_vel,
    )

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

    direction = free_block.position - bonded_block.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    free_offset = Vector2(molecule.offsets[bonded_to_id]) + direction * state.gfx.bond_length
    free_block.position = Vector2(anchor.position) + free_offset

    molecule.block_ids.append(free_id)
    molecule.offsets[free_id] = free_offset
    free_block.molecule_id = mol_id

    old_n = molecule.n - 1
    combined = (molecule.velocity * old_n + free_block.velocity) / molecule.n

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

    if mol_b.n > mol_a.n:
        mol_a, mol_b = mol_b, mol_a
        mol_a_id, mol_b_id = mol_b_id, mol_a_id
        connect_a_id, connect_b_id = connect_b_id, connect_a_id

    base = mol_a
    absorbed = mol_b
    base_anchor = state.blocks[base.anchor_block_id]

    ca = state.blocks[connect_a_id]
    cb = state.blocks[connect_b_id]
    direction = cb.position - ca.position
    if direction.length_squared() > 0:
        direction = direction.normalize()
    else:
        direction = Vector2(1, 0)

    connect_a_offset = base.offsets[connect_a_id]
    connect_b_offset = absorbed.offsets[connect_b_id]
    bridge = connect_a_offset + direction * state.gfx.bond_length

    for bid in absorbed.block_ids:
        new_offset = bridge + (absorbed.offsets[bid] - connect_b_offset)
        base.offsets[bid] = new_offset
        base.block_ids.append(bid)
        state.blocks[bid].molecule_id = base.id

    n_base_orig = base.n - absorbed.n
    combined = (base.velocity * n_base_orig + absorbed.velocity * absorbed.n) / base.n
    mobility = compute_molecule_mobility(base, state.blocks, config.molec_mobility_penalty)
    if combined.length_squared() > 0:
        base.velocity = combined.normalize() * mobility * config.speed_scale
    else:
        base.velocity = Vector2(0, 0)

    for bid in base.block_ids:
        state.blocks[bid].position = Vector2(base_anchor.position) + base.offsets[bid]

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
            continue

        a = state.blocks[bond.block_a_id]
        b = state.blocks[bond.block_b_id]
        break_prob = (a.breaking_reactivity + b.breaking_reactivity) / 2

        # Assembly protection: both blocks in same assembly and both H-bonded
        # Resistance scales with M (more molecules = stronger protection)
        if (a.assembly_id is not None and a.assembly_id == b.assembly_id
                and _block_has_hbond(state, bond.block_a_id)
                and _block_has_hbond(state, bond.block_b_id)):
            asm = state.assemblies[a.assembly_id]
            M = len(asm.molecule_ids)
            break_prob = max(0, break_prob - state.config.assembly_bond_resistance * (M - 1))

        roll = random.random()
        if roll < break_prob:
            bonds_to_break.append(bond.id)
            logger.debug(
                f"[TICK {state.tick}] BOND BREAK: Bond {bond.id} "
                f"(Block {bond.block_a_id} - Block {bond.block_b_id}, "
                f"prob={break_prob:.2f}, rolled={roll:.2f})"
            )

    for bond_id in bonds_to_break:
        if bond_id in state.bonds:
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
        return

    molecule = state.molecules[mol_id]
    _split_molecule(state, molecule, bond.block_a_id, bond.block_b_id, id_gen)


def _split_molecule(
    state: SimulationState,
    molecule: Molecule,
    break_a_id: int, break_b_id: int,
    id_gen: IdGen,
):
    """Split a molecule into two fragments after a bond break.

    Assembly-aware: fragments stay in the assembly if the molecule was assembled.
    Single-block fragments are removed from the assembly.
    """
    config = state.config
    assembly_id = molecule.assembly_id

    frag_a_ids = _walk_chain(state, break_a_id, exclude_neighbor=break_b_id)
    frag_b_ids = _walk_chain(state, break_b_id, exclude_neighbor=break_a_id)

    old_vel = molecule.velocity
    if assembly_id is not None and assembly_id in state.assemblies:
        old_vel = state.assemblies[assembly_id].velocity
    old_vel_dir = old_vel.normalize() if old_vel.length_squared() > 0 else Vector2(1, 0)

    old_mol_id = molecule.id
    del state.molecules[old_mol_id]

    new_mol_ids = []
    for frag_ids in (frag_a_ids, frag_b_ids):
        if len(frag_ids) == 1:
            # Becomes a free block
            bid = frag_ids[0]
            block = state.blocks[bid]
            block.molecule_id = None
            if assembly_id is not None:
                block.assembly_id = None

            perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
            direction = old_vel_dir + perturbation
            if direction.length_squared() > 0:
                direction = direction.normalize()
            else:
                direction = Vector2(1, 0)
            block.velocity = direction * block.mobility * config.speed_scale
            logger.debug(f"  -> Block {bid} became free")
        else:
            # Create new molecule fragment
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
                assembly_id=assembly_id,
            )

            if assembly_id is not None and assembly_id in state.assemblies:
                # Stay in assembly - use assembly velocity
                new_mol.velocity = Vector2(state.assemblies[assembly_id].velocity)
            else:
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

            new_mol_ids.append(new_mol.id)
            logger.debug(f"  -> Fragment -> Molecule {new_mol.id} ({new_mol.n} blocks)")

    if assembly_id is not None and assembly_id in state.assemblies:
        _update_assembly_after_split(state, assembly_id, old_mol_id, new_mol_ids)


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


# --- Phase 3: Catalysis ---

def compute_catalysis_scaling(state: SimulationState, assembly: Assembly) -> float:
    """Scaling factor proportional to both LCP sum and assembly size (M).

    scaling = (1 + M * catalysis_m_bonus) * (sum_lcp / 5.0)
    See FORMULAS.md Section 4 for details.
    """
    sum_lcp = sum(
        state.blocks[bid].latent_catalytic_potential
        for mid in assembly.molecule_ids
        for bid in state.molecules[mid].block_ids
    )
    M = len(assembly.molecule_ids)
    return (1 + M * state.config.catalysis_m_bonus) * (sum_lcp / 5.0)


def try_catalysis_roll(state: SimulationState, assembly: Assembly):
    """Roll to see if an assembly becomes catalytic.

    Called once per assembly formation or growth event.
    Already-catalytic assemblies stay catalytic.
    See FORMULAS.md Section 4.1.
    """
    if assembly.is_catalytic:
        return
    scaling = compute_catalysis_scaling(state, assembly)
    p_catalysis = state.config.base_catalysis_chance * scaling
    if random.random() < p_catalysis:
        assembly.is_catalytic = True
        logger.debug(
            f"[TICK {state.tick}] CATALYTIC: Assembly {assembly.id} "
            f"became catalytic (p={p_catalysis:.3f})"
        )


def _block_in_assembly_range(state: SimulationState, assembly: Assembly, pos: Vector2) -> bool:
    """Check if a position is within catalysis_range of any block in the assembly."""
    r = state.config.catalysis_range
    for mid in assembly.molecule_ids:
        for bid in state.molecules[mid].block_ids:
            if state.blocks[bid].position.distance_to(pos) < r:
                return True
    return False


def _spawn_block_near_assembly(state: SimulationState, assembly: Assembly, id_gen: IdGen):
    """Spawn a new building block in the external zone around a catalytic assembly."""
    config = state.config
    min_dist = state.gfx.bond_length  # must be outside the rigid body

    # Collect all block positions in the assembly
    asm_positions = [
        state.blocks[bid].position
        for mid in assembly.molecule_ids
        for bid in state.molecules[mid].block_ids
    ]

    # Try to find a valid spawn point (outside rigid body, inside catalysis range)
    pos = None
    for _ in range(10):
        origin = random.choice(asm_positions)
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(min_dist, config.catalysis_range)
        candidate = Vector2(origin) + Vector2(math.cos(angle) * dist, math.sin(angle) * dist)

        # Check it's not overlapping any assembly block
        if all(candidate.distance_to(p) >= min_dist for p in asm_positions):
            pos = candidate
            break

    if pos is None:
        return  # couldn't find valid spot, skip this tick

    # Clamp to simulation bounds
    sim_width = state.gfx.window_width - 200  # legend panel
    r = state.gfx.block_radius
    pos.x = max(r, min(sim_width - r, pos.x))
    pos.y = max(r, min(state.gfx.window_height - r, pos.y))

    # Sample properties from normal distributions (same as initial generation)
    from src.simulation import _sample_clamped_normal, _random_direction

    mobility = _sample_clamped_normal(config.mobility_mean, config.mobility_std)
    block = BuildingBlock(
        id=id_gen.next(),
        position=pos,
        velocity=_random_direction() * mobility * config.speed_scale,
        mobility=mobility,
        formation_reactivity=_sample_clamped_normal(
            config.formation_reactivity_mean, config.formation_reactivity_std
        ),
        breaking_reactivity=_sample_clamped_normal(
            config.breaking_reactivity_mean, config.breaking_reactivity_std
        ),
        h_bond_type=random.choice([HBondType.DONOR, HBondType.ACCEPTOR]),
        latent_catalytic_potential=_sample_clamped_normal(
            config.latent_catalytic_mean, config.latent_catalytic_std
        ),
    )
    state.blocks[block.id] = block
    logger.debug(
        f"[TICK {state.tick}] BLOCK SPAWNED: Block {block.id} near Assembly {assembly.id} "
        f"at ({pos.x:.0f}, {pos.y:.0f})"
    )


def catalysis_step(state: SimulationState, id_gen: IdGen):
    """Catalysis effects for all catalytic assemblies.

    Called every catalysis_interval ticks.
    - Block generation (Formula 4.2)
    - Formation bonus is applied during handle_collisions, not here
    """
    config = state.config

    for assembly in list(state.assemblies.values()):
        if not assembly.is_catalytic:
            continue

        scaling = compute_catalysis_scaling(state, assembly)

        # Block generation
        p_gen = config.base_generation_chance * scaling
        if random.random() < p_gen:
            _spawn_block_near_assembly(state, assembly, id_gen)


def get_bond_catalysis_bonus(state: SimulationState, a_id: int, b_id: int) -> float:
    """Get the formation reactivity bonus for a bond from nearby catalysts.

    A catalyst contributes its bonus if either block is within catalysis_range
    of any block in the assembly. Bonuses from different catalysts stack.
    See FORMULAS.md Section 4.3.
    """
    a_pos = state.blocks[a_id].position
    b_pos = state.blocks[b_id].position
    total_bonus = 0.0

    for asm in state.assemblies.values():
        if not asm.is_catalytic:
            continue

        if (_block_in_assembly_range(state, asm, a_pos)
                or _block_in_assembly_range(state, asm, b_pos)):
            scaling = compute_catalysis_scaling(state, asm)
            total_bonus += state.config.base_reactivity_bonus * scaling

    return total_bonus
