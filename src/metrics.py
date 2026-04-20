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
