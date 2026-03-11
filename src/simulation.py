from __future__ import annotations

import math
import random

from pygame.math import Vector2

from src import chemistry, physics
from src.config import GfxConfig, SimConfig
from src.entities import Bond, BuildingBlock, HBondType, Molecule, SimulationState
from src.id_gen import IdGen
from src.physics import SpatialHash


def create_initial_state(config: SimConfig, gfx: GfxConfig, id_gen: IdGen) -> SimulationState:
    """Create initial simulation state from config.

    Random mode: generate blocks with normally-distributed properties.
    Scenario mode: create blocks from exact specs in config.scenario_blocks.
    """
    state = SimulationState(config=config, gfx=gfx)
    sim_width = gfx.window_width - 200  # legend panel

    if config.scenario_blocks is not None:
        _init_scenario(state, config, id_gen)
    else:
        _init_random(state, config, id_gen, sim_width)

    return state


def _sample_clamped_normal(mean: float, std: float) -> float:
    """Sample from N(mean, std) clamped to [0, 1].

    Sampling: value = clamp(N(mean, std), 0, 1)
    See FORMULAS.md Section 6 for documentation.
    """
    return max(0.0, min(1.0, random.gauss(mean, std)))


def _random_direction() -> Vector2:
    """Return a unit Vector2 in a random direction."""
    angle = random.uniform(0, 2 * math.pi)
    return Vector2(math.cos(angle), math.sin(angle))


def _init_random(state: SimulationState, config: SimConfig, id_gen: IdGen, sim_width: float):
    """Generate blocks with normally-distributed random properties."""
    margin = config.block_radius * 2

    for _ in range(config.num_blocks):
        mobility = _sample_clamped_normal(config.mobility_mean, config.mobility_std)
        block = BuildingBlock(
            id=id_gen.next(),
            position=Vector2(
                random.uniform(margin, sim_width - margin),
                random.uniform(margin, state.gfx.window_height - margin),
            ),
            velocity=Vector2(0, 0),  # set below
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
        # Velocity: random direction, magnitude = mobility * speed_scale
        block.velocity = _random_direction() * mobility * config.speed_scale
        state.blocks[block.id] = block


def _init_scenario(state: SimulationState, config: SimConfig, id_gen: IdGen):
    """Create blocks from exact scenario specs, then build any scenario molecules.

    scenario_blocks: list of block specs (position, velocity, properties)
    scenario_molecules: list of molecule specs, each with:
        - block_indices: list of indices into scenario_blocks (bonded in order)
        - velocity: [vx, vy] for the molecule
    Blocks in a molecule have their positions snapped to exact bond_length spacing.
    """
    # Map from scenario index -> block id
    index_to_id: list[int] = []

    for spec in config.scenario_blocks:
        block = BuildingBlock(
            id=id_gen.next(),
            position=Vector2(spec["position"][0], spec["position"][1]),
            velocity=Vector2(spec.get("velocity", [0, 0])[0], spec.get("velocity", [0, 0])[1]),
            mobility=spec["mobility"],
            formation_reactivity=spec["formation_reactivity"],
            breaking_reactivity=spec["breaking_reactivity"],
            h_bond_type=HBondType(spec["h_bond_type"]),
            latent_catalytic_potential=spec["latent_catalytic_potential"],
        )
        state.blocks[block.id] = block
        index_to_id.append(block.id)

    # Build molecules from scenario_molecules
    if config.scenario_molecules:
        for mol_spec in config.scenario_molecules:
            _build_scenario_molecule(state, config, id_gen, mol_spec, index_to_id)


def _build_scenario_molecule(
    state: SimulationState, config: SimConfig, id_gen: IdGen,
    mol_spec: dict, index_to_id: list[int],
):
    """Build a pre-bonded molecule from a scenario spec.

    Snaps block positions to enforce exact bond_length chain spacing
    starting from the first block's position.
    """
    indices = mol_spec["block_indices"]
    vel = Vector2(mol_spec["velocity"][0], mol_spec["velocity"][1])
    block_ids = [index_to_id[i] for i in indices]

    # Snap positions: first block keeps its position, rest are spaced at bond_length
    anchor_id = block_ids[0]
    anchor_block = state.blocks[anchor_id]

    for i in range(1, len(block_ids)):
        prev_block = state.blocks[block_ids[i - 1]]
        curr_block = state.blocks[block_ids[i]]
        direction = curr_block.position - prev_block.position
        if direction.length_squared() > 0:
            direction = direction.normalize()
        else:
            direction = Vector2(1, 0)
        curr_block.position = Vector2(prev_block.position) + direction * config.bond_length

    # Create bonds between consecutive blocks
    for i in range(len(block_ids) - 1):
        bond = Bond(id=id_gen.next(), block_a_id=block_ids[i], block_b_id=block_ids[i + 1])
        state.bonds[bond.id] = bond
        state.blocks[block_ids[i]].bond_ids.append(bond.id)
        state.blocks[block_ids[i + 1]].bond_ids.append(bond.id)

    # Compute offsets from anchor
    offsets = {}
    for bid in block_ids:
        offsets[bid] = Vector2(state.blocks[bid].position) - Vector2(anchor_block.position)

    mol = Molecule(
        id=id_gen.next(),
        block_ids=block_ids,
        anchor_block_id=anchor_id,
        offsets=offsets,
        velocity=vel,
    )
    state.molecules[mol.id] = mol
    for bid in block_ids:
        state.blocks[bid].molecule_id = mol.id


def step(state: SimulationState, spatial_hash: SpatialHash, id_gen: IdGen):
    """Execute one simulation tick."""
    physics.move_all(state)
    physics.update_spatial_hash(state, spatial_hash)
    collisions = physics.detect_collisions(state, spatial_hash)
    chemistry.handle_collisions(state, collisions, id_gen)

    if state.tick > 0 and state.tick % state.config.hydrolysis_interval == 0:
        chemistry.hydrolysis_step(state, id_gen)

    state.tick += 1

    if state.tick % state.config.history_interval == 0:
        record_history(state)


def record_history(state: SimulationState):
    """Snapshot current metrics into state.history."""
    h = state.history
    h["tick"].append(state.tick)
    h["num_blocks"].append(len(state.blocks))
    h["num_bonds"].append(len(state.bonds))
    h["num_molecules"].append(len(state.molecules))

    free_blocks = sum(1 for b in state.blocks.values() if b.molecule_id is None)
    total_entities = free_blocks + len(state.molecules)
    if total_entities > 0:
        total_n = free_blocks + sum(m.n for m in state.molecules.values())
        avg_n = total_n / total_entities
    else:
        avg_n = 0.0
    h["avg_molecule_size"].append(round(avg_n, 2))
    if state.molecules:
        avg_n_formed = sum(m.n for m in state.molecules.values()) / len(state.molecules)
    else:
        avg_n_formed = 0.0
    h["avg_molecule_size_formed"].append(round(avg_n_formed, 2))
    h["num_assemblies"].append(len(state.assemblies))
    h["num_catalytic"].append(
        sum(1 for a in state.assemblies.values() if a.is_catalytic)
    )
