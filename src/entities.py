from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pygame.math import Vector2

from src.config import GfxConfig, SimConfig
from src.id_gen import IdGen


class HBondType(Enum):
    DONOR = "donor"
    ACCEPTOR = "acceptor"


@dataclass
class BuildingBlock:
    id: int
    position: Vector2
    velocity: Vector2  # only meaningful if free (molecule_id is None)

    # Chemical properties (all 0.0 - 1.0)
    mobility: float
    formation_reactivity: float
    breaking_reactivity: float
    h_bond_type: HBondType
    latent_catalytic_potential: float

    # Structural state
    bond_ids: list[int] = field(default_factory=list)  # max 2
    molecule_id: Optional[int] = None
    assembly_id: Optional[int] = None


@dataclass
class Bond:
    id: int
    block_a_id: int
    block_b_id: int
    is_h_bond: bool = False  # Phase 2


@dataclass
class Molecule:
    id: int
    block_ids: list[int]  # ordered chain
    anchor_block_id: int
    offsets: dict[int, Vector2]  # block_id -> offset from anchor position
    velocity: Vector2
    assembly_id: Optional[int] = None  # Phase 2

    @property
    def n(self) -> int:
        return len(self.block_ids)


@dataclass
class Assembly:
    """Phase 2 stub. Defined here so imports are ready."""
    id: int
    molecule_ids: list[int]
    h_bond_ids: list[int]
    anchor_molecule_id: int
    offsets: dict[int, Vector2]  # molecule_id -> offset from assembly anchor
    velocity: Vector2
    is_catalytic: bool = False
    catalysis_score: float = 0.0


@dataclass
class SimulationState:
    config: SimConfig
    gfx: GfxConfig
    id_gen: IdGen = field(default_factory=IdGen)
    blocks: dict[int, BuildingBlock] = field(default_factory=dict)
    bonds: dict[int, Bond] = field(default_factory=dict)
    molecules: dict[int, Molecule] = field(default_factory=dict)
    assemblies: dict[int, Assembly] = field(default_factory=dict)
    tick: int = 0
    paused: bool = False
    speed_multiplier: int = 1
    history: dict[str, list] = field(default_factory=lambda: {
        "tick": [],
        "num_blocks": [],
        "num_bonds": [],
        "num_molecules": [],
        "avg_molecule_size": [],
        "avg_molecule_size_formed": [],
        "num_assemblies": [],
        "num_h_bonds": [],
        "num_catalytic": [],
    })


# --- Helper functions ---

def can_bond(state: SimulationState, block_id: int) -> bool:
    """True if block has fewer than 2 bonds (linear bonding rule)."""
    return len(state.blocks[block_id].bond_ids) < 2


def get_entity_mass(state: SimulationState, block_id: int) -> float:
    """Get the effective mass of the rigid group this block belongs to.

    Mass = 1 / mobility.  Lower mobility means heavier.
    """
    block = state.blocks[block_id]
    if block.assembly_id is not None:
        from src.physics import compute_assembly_mobility
        asm = state.assemblies[block.assembly_id]
        return 1.0 / compute_assembly_mobility(asm, state)
    if block.molecule_id is not None:
        from src.physics import compute_molecule_mobility
        mol = state.molecules[block.molecule_id]
        mob = compute_molecule_mobility(mol, state.blocks, state.config.molec_mobility_penalty)
        return 1.0 / mob
    return 1.0 / max(0.01, block.mobility)


def get_entity_velocity(state: SimulationState, block_id: int) -> Vector2:
    """Get the velocity of the rigid group this block belongs to."""
    block = state.blocks[block_id]
    if block.assembly_id is not None:
        return state.assemblies[block.assembly_id].velocity
    if block.molecule_id is not None:
        return state.molecules[block.molecule_id].velocity
    return block.velocity


def set_entity_velocity(state: SimulationState, block_id: int, velocity: Vector2):
    """Set the velocity of the rigid group this block belongs to."""
    block = state.blocks[block_id]
    if block.assembly_id is not None:
        state.assemblies[block.assembly_id].velocity = velocity
    elif block.molecule_id is not None:
        state.molecules[block.molecule_id].velocity = velocity
    else:
        block.velocity = velocity


def shift_entity(state: SimulationState, block_id: int, offset: Vector2):
    """Shift the anchor position of the rigid group this block belongs to."""
    block = state.blocks[block_id]
    if block.assembly_id is not None:
        asm = state.assemblies[block.assembly_id]
        anchor_mol = state.molecules[asm.anchor_molecule_id]
        state.blocks[anchor_mol.anchor_block_id].position += offset
    elif block.molecule_id is not None:
        mol = state.molecules[block.molecule_id]
        state.blocks[mol.anchor_block_id].position += offset
    else:
        block.position += offset
