"""Metric computation functions for headless data collection."""
from __future__ import annotations

from src.entities import SimulationState


def avg_hydrolytic_resistance(state: SimulationState) -> float:
    """Average (1 - breaking_reactivity) across all blocks in formed molecules (N>=2)."""
    total = 0.0
    count = 0
    for mol in state.molecules.values():
        if mol.n >= 2:
            for bid in mol.block_ids:
                total += 1.0 - state.blocks[bid].breaking_reactivity
                count += 1
    return total / count if count > 0 else 0.0


def pct_blocks_in_assemblies(state: SimulationState) -> float:
    """Percentage of blocks (in formed molecules N>=2) that are part of assemblies."""
    blocks_in_formed = 0
    blocks_in_asm = 0
    for mol in state.molecules.values():
        if mol.n >= 2:
            for bid in mol.block_ids:
                blocks_in_formed += 1
                if state.blocks[bid].assembly_id is not None:
                    blocks_in_asm += 1
    if blocks_in_formed == 0:
        return 0.0
    return (blocks_in_asm / blocks_in_formed) * 100.0


def pct_blocks_in_catalytic_assemblies(state: SimulationState) -> float:
    """Percentage of blocks (in formed molecules N>=2) that are part of catalytic assemblies."""
    blocks_in_formed = 0
    blocks_in_cat = 0
    for mol in state.molecules.values():
        if mol.n >= 2:
            for bid in mol.block_ids:
                blocks_in_formed += 1
                aid = state.blocks[bid].assembly_id
                if aid is not None and state.assemblies[aid].is_catalytic:
                    blocks_in_cat += 1
    if blocks_in_formed == 0:
        return 0.0
    return (blocks_in_cat / blocks_in_formed) * 100.0


def avg_molecule_size_formed(state: SimulationState) -> float:
    """Mean N (chain length) across all formed molecules; 0.0 if none exist."""
    if not state.molecules:
        return 0.0
    return sum(m.n for m in state.molecules.values()) / len(state.molecules)


def num_assemblies(state: SimulationState) -> float:
    """Number of assemblies currently present."""
    return float(len(state.assemblies))


def num_catalytic(state: SimulationState) -> float:
    """Number of catalytic assemblies currently present."""
    return float(sum(1 for a in state.assemblies.values() if a.is_catalytic))


# Registry: metric name -> function. Used by the headless runner to select columns.
METRIC_FUNCTIONS = {
    "avg_hydrolytic_resistance": avg_hydrolytic_resistance,
    "pct_blocks_in_assemblies": pct_blocks_in_assemblies,
    "pct_blocks_in_catalytic_assemblies": pct_blocks_in_catalytic_assemblies,
    "avg_molecule_size_formed": avg_molecule_size_formed,
    "num_assemblies": num_assemblies,
    "num_catalytic": num_catalytic,
}
