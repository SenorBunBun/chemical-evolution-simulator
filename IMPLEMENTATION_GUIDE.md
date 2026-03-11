# Molecular Evolution Simulator - Implementation Guide

Comprehensive development guide for all phases. Any developer or AI session can pick up from any phase using this document.

**Related documents:**
- `chem_evo_proposal_planning.md` - Original proposal with biological rationale
- `FORMULAS.md` - All mathematical formulas with variable definitions

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Design Decisions](#2-architecture--design-decisions)
3. [Project Structure](#3-project-structure)
4. [Data Model](#4-data-model)
5. [Module Responsibilities](#5-module-responsibilities)
6. [Phase 1: Core Simulation](#6-phase-1-core-simulation)
7. [Phase 2: Assembly Logic](#7-phase-2-assembly-logic)
8. [Phase 3: Catalysis](#8-phase-3-catalysis)
9. [Phase 4: Live Graphs & Data Export](#9-phase-4-live-graphs--data-export)
10. [Rendering & UI](#10-rendering--ui)
11. [Configuration System](#11-configuration-system)
12. [Testing & Debugging](#12-testing--debugging)

---

## 1. Project Overview

A particle-based 2D simulator where:

1. **Building blocks** (particles with chemical properties) bounce around in a 2D space with billiard-ball physics.
2. **Bonds** form when blocks collide, based on probabilistic chemistry rules.
3. **Molecules** are linear chains of bonded blocks that move as rigid bodies.
4. **Assemblies** (Phase 2) form when molecules with matching H-bond types join via hydrogen bonds.
5. **Catalysts** (Phase 3) are assemblies that can generate new blocks and boost nearby reactivity.
6. **Data tracking** (Phase 4) records simulation metrics over time for graphing and export.

### Biological Analogy

| Simulation Concept | Biological Equivalent |
|---|---|
| Building Block | Ions, functional groups, monomers |
| Mobility | Molecular weight (inverse) |
| Formation Reactivity | Nucleophilicity/Electrophilicity |
| Breaking Reactivity | Hydrolysis susceptibility |
| H-bond Type | Hydrogen bond donor/acceptor |
| Molecule | Polymer chain |
| Assembly | Supramolecular complex |
| Catalysis | Enzymatic activity |

---

## 2. Architecture & Design Decisions

### Core Principles

1. **Properties as 0.0-1.0 floats** - All chemical properties are floats in [0, 1] used directly as probabilities. No integer-to-probability mapping layer. `random.random() < value` is the universal check.

2. **ID-based references** - All entity cross-references use integer IDs, not object references. This enables easy serialization, prevents circular references, and makes debugging straightforward (print an ID, look it up).

3. **Centralized SimulationState** - One `SimulationState` dataclass holds ALL entities (dicts of id -> entity). Every function takes `state` as its first argument. Easy to inspect, reset, serialize, or snapshot.

4. **Linear chains only** - Max 2 bonds per building block means molecules are always simple chains. A bond break always produces exactly 2 fragments. No graph traversal or cycle detection needed -- just walk left and right from the break point.

5. **Translation only, no rotation** - Rigid bodies translate but don't rotate. Molecules maintain their shape but only change position and direction. This dramatically simplifies physics while being visually acceptable.

6. **Spatial hashing for collisions** - O(N) collision detection using a grid-based spatial hash. Cell size = bond_length ensures any colliding pair is in the same or adjacent cells.

7. **Bond length = collision radius** - When two blocks are at bond_length distance, they are colliding. This means blocks within an assembly that lose a bond are still touching and can immediately re-bond (structural support from assembly).

8. **Velocity as Vector2** - Direction encoded in the vector itself, magnitude proportional to mobility. When mobility changes (merge/split), rescale magnitude but keep direction.

### What This Is NOT

- Not a molecular dynamics simulator (no force fields, no integration)
- Not GPU-accelerated (pure Python + Pygame, designed for readability)
- Not a distributed system (single process, single thread)
- Not physically accurate (simplified collisions, no angular momentum)

---

## 3. Project Structure

```
chem-evo-sim/
├── main.py                    # Entry point, CLI argument parsing, game loop
├── configs/
│   ├── default.json           # Default simulation parameters (overrides only)
│   └── scenarios/
│       └── two_block_test.json  # Debug scenario: 2 blocks aimed at each other
├── src/
│   ├── __init__.py
│   ├── config.py              # SimConfig dataclass, load_config()
│   ├── entities.py            # BuildingBlock, Bond, Molecule, Assembly, SimulationState, HBondType
│   ├── simulation.py          # create_initial_state(), step(), record_history()
│   ├── physics.py             # move_all(), SpatialHash, detect_collisions(), wall_bounce(), deflect()
│   ├── chemistry.py           # handle_collisions(), form_bond(), hydrolysis_step(), split_molecule()
│   ├── renderer.py            # Renderer class: draw(), handle_events(), legend panel, debug overlay
│   └── id_gen.py              # IdGen class: simple incrementing ID generator
├── requirements.txt           # pygame
├── IMPLEMENTATION_GUIDE.md    # This file
├── FORMULAS.md                # All simulation formulas
└── chem_evo_proposal_planning.md  # Original proposal
```

---

## 4. Data Model

All defined in `src/entities.py`. Pure dataclasses -- no methods with logic.

### 4.1 HBondType (Enum)

```python
class HBondType(Enum):
    DONOR = "donor"
    ACCEPTOR = "acceptor"
```

### 4.2 BuildingBlock

```python
@dataclass
class BuildingBlock:
    id: int
    position: Vector2              # absolute world position (pixels)
    velocity: Vector2              # only meaningful if free (molecule_id is None)

    # Chemical properties (all 0.0 - 1.0)
    mobility: float                # speed factor
    formation_reactivity: float    # bond formation probability factor
    breaking_reactivity: float     # bond breaking probability factor
    h_bond_type: HBondType         # donor or acceptor
    latent_catalytic_potential: float  # contributes to catalysis score in assemblies

    # Structural state (managed by chemistry module)
    bond_ids: list[int] = field(default_factory=list)  # IDs of bonds (max 2)
    molecule_id: Optional[int] = None     # molecule this block belongs to, or None
    assembly_id: Optional[int] = None     # assembly this block belongs to (Phase 2)
```

**Key invariants:**
- `len(bond_ids) <= 2` always (linear bonding rule)
- If `molecule_id is None`, block is "free" and uses its own `velocity`
- If `molecule_id is not None`, block moves with its molecule's velocity
- `position` is always kept in sync (even for blocks in molecules)

### 4.3 Bond

```python
@dataclass
class Bond:
    id: int
    block_a_id: int
    block_b_id: int
    is_h_bond: bool = False        # True for hydrogen bonds (Phase 2)
```

**No stored breaking chance** -- computed on the fly from constituent blocks to stay in sync.

### 4.4 Molecule

```python
@dataclass
class Molecule:
    id: int
    block_ids: list[int]           # ordered chain of block IDs
    anchor_block_id: int           # the block whose position drives all others
    offsets: dict[int, Vector2]    # block_id -> offset from anchor's position
    velocity: Vector2              # single velocity vector for the whole molecule
    assembly_id: Optional[int] = None  # Phase 2
```

**Key invariants:**
- `anchor_block_id in block_ids`
- `offsets[anchor_block_id] == Vector2(0, 0)`
- All block positions = `blocks[anchor_block_id].position + offsets[block_id]`
- `block_ids` is ordered along the chain (from one end to the other)

**Property `n`:** `len(block_ids)` -- the size of the molecule.

### 4.5 Assembly (Phase 2)

```python
@dataclass
class Assembly:
    id: int
    molecule_ids: list[int]        # molecules in this assembly
    h_bond_ids: list[int]          # bond IDs that are H-bonds connecting molecules
    anchor_molecule_id: int        # molecule whose anchor drives the assembly
    offsets: dict[int, Vector2]    # molecule_id -> offset of mol's anchor from assembly anchor
    velocity: Vector2              # single velocity for the whole assembly
    is_catalytic: bool = False     # Phase 3
    catalysis_score: float = 0.0   # Phase 3
```

### 4.6 SimulationState

```python
@dataclass
class SimulationState:
    config: SimConfig              # reference to config for easy access
    blocks: dict[int, BuildingBlock]    # id -> block
    bonds: dict[int, Bond]              # id -> bond
    molecules: dict[int, Molecule]      # id -> molecule
    assemblies: dict[int, Assembly]     # id -> assembly (empty in Phase 1)
    tick: int = 0
    paused: bool = False
    speed_multiplier: int = 1
    history: dict[str, list] = field(default_factory=lambda: {
        "tick": [], "num_blocks": [], "num_bonds": [],
        "num_molecules": [], "avg_molecule_size": [],
        "num_assemblies": [], "num_catalytic": [],
    })
```

### 4.7 Helper Functions (in entities.py)

```python
def can_bond(state: SimulationState, block_id: int) -> bool:
    """True if block has fewer than 2 bonds."""
    return len(state.blocks[block_id].bond_ids) < 2

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
```

---

## 5. Module Responsibilities

### `main.py` - Entry Point

- Parse CLI arguments: optional config path, `--verbose` flag
- Call `load_config()` to get `SimConfig`
- Call `create_initial_state()` to build `SimulationState`
- Create `Renderer`, `SpatialHash`, `IdGen`
- Run the main game loop:
  ```
  while running:
      running = renderer.handle_events(state)
      if not state.paused:
          for _ in range(state.speed_multiplier):
              step(state, spatial_hash, id_gen)
      renderer.draw(state)
      clock.tick(config.target_fps)
  ```

### `src/config.py` - Configuration

- `SimConfig` dataclass with ALL parameters and their defaults
- `load_config(path: Optional[str]) -> SimConfig`: load JSON, merge with defaults
- Scenario mode: if JSON contains `scenario_blocks` list, those define exact block placements

### `src/entities.py` - Data Model

- All dataclass definitions (BuildingBlock, Bond, Molecule, Assembly, SimulationState)
- `HBondType` enum
- Helper functions (can_bond, get/set_entity_velocity, shift_entity)
- No simulation logic

### `src/simulation.py` - Orchestration

- `create_initial_state(config, id_gen) -> SimulationState`: random or scenario-based initialization
- `step(state, spatial_hash, id_gen)`: one simulation tick (calls physics and chemistry)
- `record_history(state)`: snapshot current metrics into `state.history`

### `src/physics.py` - Movement & Collisions

- `move_all(state)`: move free blocks and molecules by their velocities
- `wall_bounce(block, config)` / `wall_bounce_molecule(molecule, state)`: reflect at boundaries
- `SpatialHash` class: insert blocks, query nearby blocks
- `update_spatial_hash(state, spatial_hash)`: rebuild hash from current positions
- `detect_collisions(state, spatial_hash) -> list[tuple[int, int]]`: find colliding block pairs
- `deflect(state, a_id, b_id)`: elastic collision response
- `compute_molecule_mobility(molecule, blocks, penalty) -> float`: mobility formula

### `src/chemistry.py` - Chemical Logic

- `handle_collisions(state, collisions, id_gen)`: process all collision pairs (bond/assembly/deflect)
- `form_bond(state, a_id, b_id, id_gen)`: create bond + handle molecule creation/merging
- `create_molecule_from_pair(state, a_id, b_id, id_gen)`: two free blocks -> new molecule
- `add_block_to_molecule(state, free_id, mol_id, bonded_to_id, id_gen)`: free block joins molecule
- `merge_molecules(state, mol_a_id, mol_b_id, connect_a_id, connect_b_id, id_gen)`: two molecules merge
- `hydrolysis_step(state, id_gen)`: check all bonds for breaking
- `break_bond(state, bond_id, id_gen)`: remove bond and split molecule
- `split_molecule(state, molecule, break_a_id, break_b_id, id_gen)`: split into fragments
- `walk_chain(state, start_id, exclude_neighbor) -> list[int]`: walk a linear chain

### `src/renderer.py` - Visualization

- `Renderer` class with:
  - `draw(state)`: full frame render (sim area + legend panel)
  - `handle_events(state) -> bool`: process keyboard/mouse, return False on quit
  - `_draw_blocks(state)`: colored circles for blocks
  - `_draw_bonds(state)`: colored lines for bonds
  - `_draw_legend(state)`: heatmap gradient bars + stats + controls reference
  - `_draw_debug(state)`: debug overlay (IDs, velocities, grid)
  - `debug_mode: bool`: toggle with D key

### `src/id_gen.py` - ID Generation

- `IdGen` class: `next() -> int`, starts at 0, increments
- Single shared instance for globally unique IDs across all entity types

---

## 6. Phase 1: Core Simulation

### What Phase 1 Delivers

- Building blocks with all chemical properties, randomly generated or from scenario
- Billiard-ball physics: movement, wall bouncing, elastic collisions
- Bond formation on collision with probabilistic chemistry
- Bond breaking (hydrolysis) at configurable intervals
- Molecule formation, merging, and splitting as rigid bodies
- Color-coded rendering with heatmap legend panel
- Pause/play, step, speed controls
- Debug overlay and scenario config support
- History tracking (data only, no graphs)

### Implementation Steps (in order)

#### Step 1: `src/id_gen.py`

Simple class:
```python
class IdGen:
    def __init__(self):
        self._next = 0

    def next(self) -> int:
        val = self._next
        self._next += 1
        return val
```

#### Step 2: `src/config.py`

`SimConfig` dataclass with all parameters having defaults. See `FORMULAS.md` Section 6 for the full parameter table.

`load_config()`:
- If no path: return `SimConfig()` with all defaults
- If path given: read JSON, convert tuples from lists, construct `SimConfig(**data)`
- JSON only needs to specify overrides; everything else keeps defaults

#### Step 3: `src/entities.py`

All dataclasses and helpers as defined in Section 4 above. Test by creating instances manually.

#### Step 4: `src/simulation.py` - Initialization

`create_initial_state(config, id_gen) -> SimulationState`:

**Random mode** (no `scenario_blocks`):
```python
for _ in range(config.num_blocks):
    block = BuildingBlock(
        id=id_gen.next(),
        position=Vector2(
            random.uniform(margin, sim_width - margin),
            random.uniform(margin, sim_height - margin)
        ),
        velocity=random_direction() * mobility * config.speed_scale,
        mobility=random.uniform(*config.mobility_range),
        formation_reactivity=random.uniform(*config.formation_reactivity_range),
        breaking_reactivity=random.uniform(*config.breaking_reactivity_range),
        h_bond_type=random.choice([HBondType.DONOR, HBondType.ACCEPTOR]),
        latent_catalytic_potential=random.uniform(*config.latent_catalytic_range),
    )
```

Where `random_direction()` returns a unit Vector2 at a random angle.

**Scenario mode** (`scenario_blocks` present):
```python
for spec in config.scenario_blocks:
    block = BuildingBlock(
        id=id_gen.next(),
        position=Vector2(spec["position"][0], spec["position"][1]),
        velocity=Vector2(spec["velocity"][0], spec["velocity"][1]),
        mobility=spec["mobility"],
        ...
    )
```

#### Step 5: `src/renderer.py` - Basic Window

```python
class Renderer:
    LEGEND_WIDTH = 200  # right panel width
    BG_COLOR = (26, 26, 26)

    def __init__(self, config):
        pygame.init()
        self.screen = pygame.display.set_mode((config.window_width, config.window_height))
        pygame.display.set_caption("Molecular Evolution Simulator")
        self.font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("consolas", 11)
        self.sim_width = config.window_width - self.LEGEND_WIDTH
        self.debug_mode = False
        self.config = config
```

**Drawing order in `draw(state)`:**
1. Fill background
2. Draw bonds (lines, below blocks)
3. Draw blocks (circles, with color-coding)
4. Draw legend panel (right side)
5. If `debug_mode`: draw debug overlay
6. `pygame.display.flip()`

**Legend panel (`_draw_legend(state)`):**
- Draw a dark panel background on the right
- Formation Reactivity gradient bar (vertical, blue at top to red at bottom) with label
- Bond Strength gradient bar (vertical, green at top to red at bottom) with label
- Stats: tick, blocks, bonds, molecules, avg N
- Controls reference: key -> action

#### Step 6: `src/physics.py` - Movement

`move_all(state)`:

1. **Free blocks** (molecule_id is None):
   ```python
   speed = block.mobility * config.speed_scale
   if block.velocity.length() > 0:
       block.velocity = block.velocity.normalize() * speed
   block.position += block.velocity
   wall_bounce(block, config, sim_width)
   ```

2. **Molecules:**
   ```python
   mobility = compute_molecule_mobility(molecule, state.blocks, config.molec_mobility_penalty)
   speed = mobility * config.speed_scale
   if molecule.velocity.length() > 0:
       molecule.velocity = molecule.velocity.normalize() * speed
   anchor = state.blocks[molecule.anchor_block_id]
   anchor.position += molecule.velocity
   wall_bounce_molecule(molecule, state)
   # Reposition all blocks
   for bid in molecule.block_ids:
       state.blocks[bid].position = anchor.position + molecule.offsets[bid]
   ```

3. **Assemblies (Phase 2):** Same pattern, one more nesting level.

`compute_molecule_mobility(molecule, blocks, penalty) -> float`:
```python
avg = sum(blocks[bid].mobility for bid in molecule.block_ids) / len(molecule.block_ids)
return max(0.01, avg - penalty * len(molecule.block_ids))
```

#### Step 7: `src/physics.py` - Spatial Hash

```python
class SpatialHash:
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
```

**Cell size = `config.bond_length`** ensures that any pair within collision distance is in the same or adjacent cells.

`detect_collisions(state, spatial_hash) -> list[tuple[int, int]]`:
```python
collisions = []
for block_id, block in state.blocks.items():
    nearby = spatial_hash.query_nearby(block.position)
    for other_id in nearby:
        if other_id <= block_id:
            continue  # avoid self and duplicates
        other = state.blocks[other_id]
        # Skip same rigid group
        if block.molecule_id is not None and block.molecule_id == other.molecule_id:
            continue
        if block.assembly_id is not None and block.assembly_id == other.assembly_id:
            continue
        dist = block.position.distance_to(other.position)
        if dist < state.config.bond_length:
            collisions.append((block_id, other_id))
return collisions
```

#### Step 8: `src/chemistry.py` - Bond Formation

`handle_collisions(state, collisions, id_gen)`:
```python
for a_id, b_id in collisions:
    a, b = state.blocks[a_id], state.blocks[b_id]

    both_can_bond = can_bond(state, a_id) and can_bond(state, b_id)

    if both_can_bond:
        prob = (a.formation_reactivity + b.formation_reactivity) / 2
        if random.random() < prob:
            form_bond(state, a_id, b_id, id_gen)
            continue

    # No bond formed -> deflect
    deflect(state, a_id, b_id)
```

`form_bond(state, a_id, b_id, id_gen)`:
```python
bond = Bond(id=id_gen.next(), block_a_id=a_id, block_b_id=b_id)
state.bonds[bond.id] = bond
state.blocks[a_id].bond_ids.append(bond.id)
state.blocks[b_id].bond_ids.append(bond.id)

a_mol = state.blocks[a_id].molecule_id
b_mol = state.blocks[b_id].molecule_id

if a_mol is None and b_mol is None:
    create_molecule_from_pair(state, a_id, b_id, id_gen)
elif a_mol is None:
    add_block_to_molecule(state, a_id, b_mol, b_id, id_gen)
elif b_mol is None:
    add_block_to_molecule(state, b_id, a_mol, a_id, id_gen)
else:
    merge_molecules(state, a_mol, b_mol, a_id, b_id, id_gen)
```

**`create_molecule_from_pair(state, a_id, b_id, id_gen)`:**
- Direction from A to B, normalized, scaled to bond_length
- Snap B position to A.position + direction * bond_length
- Anchor = A, offset of A = Vector2(0,0), offset of B = direction * bond_length
- Velocity = weighted average (both weight 1), rescaled to new mobility
- Create Molecule, set both blocks' molecule_id

**`add_block_to_molecule(state, free_id, mol_id, bonded_to_id, id_gen)`:**
- Direction from bonded_to block toward free block, normalized, scaled to bond_length
- Free block's offset = molecule.offsets[bonded_to_id] + direction * bond_length
- Snap free block position
- Add to molecule.block_ids, update molecule velocity (blend in free block's velocity weighted 1/N)
- Set free block's molecule_id

**`merge_molecules(state, mol_a_id, mol_b_id, connect_a_id, connect_b_id, id_gen)`:**
- Keep larger molecule as "base", smaller as "absorbed" (tie-break: keep mol_a)
- For each block in absorbed molecule:
  - New offset = base.offsets[connect_a_id] + (direction from connect_a to connect_b * bond_length) + (absorbed.offsets[block] - absorbed.offsets[connect_b_id])
- Transfer all block IDs and offsets to base molecule
- New velocity = weighted average by block count, rescaled to new mobility
- Delete absorbed molecule, update all transferred blocks' molecule_id
- Snap all block positions

#### Step 9: `src/chemistry.py` - Bond Breaking

`hydrolysis_step(state, id_gen)`:
```python
bonds_to_break = []
for bond in list(state.bonds.values()):
    if bond.is_h_bond:
        continue  # H-bonds don't break via hydrolysis
    a = state.blocks[bond.block_a_id]
    b = state.blocks[bond.block_b_id]
    break_prob = (a.breaking_reactivity + b.breaking_reactivity) / 2
    # Phase 2: assembly protection
    if random.random() < break_prob:
        bonds_to_break.append(bond.id)

for bond_id in bonds_to_break:
    if bond_id in state.bonds:  # might have been removed by prior break in same step
        break_bond(state, bond_id, id_gen)
```

`break_bond(state, bond_id, id_gen)`:
```python
bond = state.bonds.pop(bond_id)
state.blocks[bond.block_a_id].bond_ids.remove(bond_id)
state.blocks[bond.block_b_id].bond_ids.remove(bond_id)

mol_id = state.blocks[bond.block_a_id].molecule_id
if mol_id is None:
    return  # shouldn't happen for bonded blocks, but safety check

molecule = state.molecules[mol_id]
split_molecule(state, molecule, bond.block_a_id, bond.block_b_id, id_gen)
```

`split_molecule(state, molecule, break_a_id, break_b_id, id_gen)`:
```python
frag_a_ids = walk_chain(state, break_a_id, exclude_neighbor=break_b_id)
frag_b_ids = walk_chain(state, break_b_id, exclude_neighbor=break_a_id)

old_vel_dir = molecule.velocity.normalize() if molecule.velocity.length() > 0 else Vector2(1, 0)
del state.molecules[molecule.id]

for frag_ids in (frag_a_ids, frag_b_ids):
    if len(frag_ids) == 1:
        bid = frag_ids[0]
        state.blocks[bid].molecule_id = None
        perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
        direction = old_vel_dir + perturbation
        if direction.length() > 0:
            direction = direction.normalize()
        state.blocks[bid].velocity = direction * state.blocks[bid].mobility * state.config.speed_scale
    else:
        anchor_id = frag_ids[0]
        anchor_pos = state.blocks[anchor_id].position
        offsets = {bid: state.blocks[bid].position - anchor_pos for bid in frag_ids}
        new_mol = Molecule(
            id=id_gen.next(),
            block_ids=frag_ids,
            anchor_block_id=anchor_id,
            offsets=offsets,
            velocity=Vector2(0, 0),
        )
        mobility = compute_molecule_mobility(new_mol, state.blocks, state.config.molec_mobility_penalty)
        perturbation = Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
        direction = old_vel_dir + perturbation
        if direction.length() > 0:
            direction = direction.normalize()
        new_mol.velocity = direction * mobility * state.config.speed_scale
        state.molecules[new_mol.id] = new_mol
        for bid in frag_ids:
            state.blocks[bid].molecule_id = new_mol.id
```

`walk_chain(state, start_id, exclude_neighbor) -> list[int]`:
```python
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
```

#### Step 10: `src/physics.py` - Deflection

```python
def deflect(state, a_id, b_id):
    a, b = state.blocks[a_id], state.blocks[b_id]
    normal = b.position - a.position
    if normal.length() == 0:
        normal = Vector2(1, 0)
    normal = normal.normalize()

    vel_a = get_entity_velocity(state, a_id)
    vel_b = get_entity_velocity(state, b_id)

    rel_vel = vel_a - vel_b
    vel_along_normal = rel_vel.dot(normal)

    if vel_along_normal <= 0:
        return  # moving apart already

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
```

#### Step 11: `main.py` - Game Loop

```python
import sys
import pygame
from src.config import load_config
from src.simulation import create_initial_state, step, record_history
from src.renderer import Renderer
from src.physics import SpatialHash
from src.id_gen import IdGen

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    verbose = "--verbose" in sys.argv
    config = load_config(config_path)
    id_gen = IdGen()
    state = create_initial_state(config, id_gen)
    renderer = Renderer(config)
    spatial_hash = SpatialHash(config.bond_length)
    clock = pygame.time.Clock()

    running = True
    while running:
        running = renderer.handle_events(state)

        if not state.paused:
            for _ in range(state.speed_multiplier):
                step(state, spatial_hash, id_gen)

        renderer.draw(state)
        clock.tick(config.target_fps)

    pygame.quit()

if __name__ == "__main__":
    main()
```

#### Step 12: `src/simulation.py` - Step Function

```python
def step(state, spatial_hash, id_gen):
    physics.move_all(state)
    spatial_hash.clear()
    physics.update_spatial_hash(state, spatial_hash)
    collisions = physics.detect_collisions(state, spatial_hash)
    chemistry.handle_collisions(state, collisions, id_gen)
    if state.tick % state.config.hydrolysis_interval == 0 and state.tick > 0:
        chemistry.hydrolysis_step(state, id_gen)
    # Phase 2: assembly checks happen inside handle_collisions
    # Phase 3: catalysis_step here
    state.tick += 1
    if state.tick % 30 == 0:
        record_history(state)
```

### Phase 1 Testing Checklist

- [ ] Config loads from JSON, defaults work, scenario mode works
- [ ] Random initialization produces blocks within bounds
- [ ] Blocks move and bounce off walls correctly
- [ ] Spatial hash detects nearby pairs correctly
- [ ] Two colliding blocks with high reactivity form a bond
- [ ] Bonded blocks move together as a molecule
- [ ] Free block can join an existing molecule
- [ ] Two molecules can merge via bond between their end blocks
- [ ] Bonds break during hydrolysis at expected rates
- [ ] Molecule splits correctly into two fragments
- [ ] Single-block fragments become free blocks
- [ ] Failed bonds cause elastic deflection
- [ ] Color-coding matches formation_reactivity and breaking_reactivity
- [ ] Legend panel shows gradient bars and stats
- [ ] Pause, step, speed controls work
- [ ] Debug overlay shows IDs and velocity vectors
- [ ] Click-to-inspect prints block state
- [ ] 200+ blocks runs at 60fps

---

## 7. Phase 2: Assembly Logic

### Prerequisites
Phase 1 complete and all Phase 1 tests passing.

### What Phase 2 Adds
- H-bond matching between molecules
- Assembly formation when matching molecules collide
- Assembly as a higher-order rigid body
- Hydrolysis protection for assembled bonds
- Assembly displacement rule (larger molecule replaces smaller)
- H-bond visualization (dashed cyan lines)

### Implementation Steps

#### 2.1: H-Bond Matching (`chemistry.py`)

```python
def check_hbond_match(state, mol_a_id, mol_b_id) -> bool:
    mol_a = state.molecules[mol_a_id]
    mol_b = state.molecules[mol_b_id]
    if len(mol_a.block_ids) != len(mol_b.block_ids):
        return False  # must be same length for full match
    for a_bid, b_bid in zip(mol_a.block_ids, mol_b.block_ids):
        a_type = state.blocks[a_bid].h_bond_type
        b_type = state.blocks[b_bid].h_bond_type
        if a_type == b_type:  # must be opposite (donor-acceptor)
            return False
    return True
```

#### 2.2: Assembly Formation in Collision Handler

After the existing bond formation logic in `handle_collisions`, add:

```python
# Check assembly eligibility
a_mol_id = state.blocks[a_id].molecule_id
b_mol_id = state.blocks[b_id].molecule_id
if a_mol_id and b_mol_id:
    mol_a = state.molecules[a_mol_id]
    mol_b = state.molecules[b_mol_id]
    if mol_a.n >= config.min_assembly_n and mol_b.n >= config.min_assembly_n:
        if check_hbond_match(state, a_mol_id, b_mol_id):
            # Both bond and assembly possible?
            if both_can_bond:
                # Weighted random: bond vs assembly
                w_bond = (a.formation_reactivity + b.formation_reactivity) / 2
                p_asm = compute_assembly_chance(state, a_mol_id, b_mol_id)
                total = w_bond + p_asm
                if random.random() < p_asm / total:
                    attempt_assembly(state, a_mol_id, b_mol_id, id_gen)
                else:
                    attempt_bond(...)
            else:
                # Only assembly possible
                p_asm = compute_assembly_chance(state, a_mol_id, b_mol_id)
                if random.random() < p_asm:
                    attempt_assembly(state, a_mol_id, b_mol_id, id_gen)
```

#### 2.3: Flatten Logic

When an assembly forms, reposition molecules into parallel lines:
- Molecule A at y=0 (relative to assembly anchor)
- Molecule B at y=bond_length (one bond_length below)
- H-bonds connect vertically between corresponding block pairs
- Both molecules are laid out horizontally

#### 2.4: Assembly Rigid Body Movement (`physics.py`)

Add to `move_all()`:
```python
for assembly in state.assemblies.values():
    mobility = compute_assembly_mobility(assembly, state)
    speed = mobility * config.speed_scale
    if assembly.velocity.length() > 0:
        assembly.velocity = assembly.velocity.normalize() * speed
    # Move assembly anchor molecule's anchor block
    asm_anchor_mol = state.molecules[assembly.anchor_molecule_id]
    asm_anchor_block = state.blocks[asm_anchor_mol.anchor_block_id]
    asm_anchor_block.position += assembly.velocity
    # Position all molecules from assembly offsets
    for mol_id in assembly.molecule_ids:
        mol = state.molecules[mol_id]
        mol_anchor = state.blocks[mol.anchor_block_id]
        mol_anchor.position = asm_anchor_block.position + assembly.offsets[mol_id]
        # Position all blocks from molecule offsets
        for bid in mol.block_ids:
            state.blocks[bid].position = mol_anchor.position + mol.offsets[bid]
    wall_bounce_assembly(assembly, state)
```

#### 2.5: Assembly Bond Protection

In `hydrolysis_step()`, modify break probability:
```python
if a.assembly_id is not None and a.assembly_id == b.assembly_id:
    # Check if both blocks participate in H-bonding
    if block_has_hbond(state, bond.block_a_id) and block_has_hbond(state, bond.block_b_id):
        break_prob = max(0, break_prob - config.assembly_bond_resistance)
```

#### 2.6: Bond Break Inside Assembly

When a bond breaks inside an assembled molecule:
1. Split the molecule into two fragments (same as Phase 1)
2. Keep both fragments in the assembly with existing H-bonds
3. If either fragment becomes a single block (N=1), remove it from the assembly
4. If the assembly has fewer than 2 molecules after cleanup, dissolve the assembly

#### 2.7: Extended Displacement Rule

When Mol A collides with assembled Mol B (H-bonded on both sides):
```python
if mol_b_hbonded_both_sides(state, b_mol_id):
    mol_c_id = get_other_side_molecule(state, b_mol_id, assembly)
    if mol_a.n > state.molecules[mol_c_id].n:
        remove_from_assembly(state, mol_c_id)
        add_to_assembly(state, a_mol_id, assembly)
```

#### 2.8: Rendering Updates

- H-bonds: dashed cyan lines (`(0, 200, 255)`)
- Assembly blocks: subtle gold/yellow background circle behind the block
- Legend panel: add H-bond color swatch

### Phase 2 Testing Checklist

- [ ] H-bond matching correctly identifies full donor-acceptor correspondence
- [ ] Molecules with N >= 5 and matching types form assemblies
- [ ] Assembly moves as a single rigid body
- [ ] Bonds inside assemblies get hydrolysis protection (lower break rate)
- [ ] Bonds at molecule edges (not H-bonded) don't get protection
- [ ] Bond break inside assembly splits molecule but keeps fragments in assembly
- [ ] Single-block fragments are removed from assembly
- [ ] Displacement rule: larger molecule replaces smaller in contested assembly
- [ ] H-bonds render as dashed cyan lines
- [ ] Scenario test: two N=5 molecules with perfect matching, aimed at each other

---

## 8. Phase 3: Catalysis

### Prerequisites
Phase 2 complete and stable.

### What Phase 3 Adds
- Assemblies can become catalytic on formation/growth
- Catalytic assemblies generate new building blocks nearby
- Catalytic assemblies boost formation reactivity of nearby blocks
- Visual indicators for catalysts and their range

### Implementation Steps

#### 3.1: Catalysis Roll

In the assembly formation handler (after `form_assembly()` or `add_to_assembly()`):
```python
if not assembly.is_catalytic:
    if random.random() < config.catalysis_chance:
        assembly.is_catalytic = True
assembly.catalysis_score = compute_catalysis_score(state, assembly)
```

#### 3.2: Catalysis Score Computation

```python
def compute_catalysis_score(state, assembly):
    total = sum(
        state.blocks[bid].latent_catalytic_potential
        for mol_id in assembly.molecule_ids
        for bid in state.molecules[mol_id].block_ids
    )
    M = len(assembly.molecule_ids)
    return total * (1 + config.catalysis_m_bonus * M)
```

#### 3.3: Catalysis Step in Simulation Loop

Add to `step()`:
```python
if state.tick % config.catalysis_interval == 0 and state.tick > 0:
    chemistry.catalysis_step(state, id_gen)
```

`catalysis_step(state, id_gen)`:
```python
for assembly in state.assemblies.values():
    if not assembly.is_catalytic:
        continue

    # Block generation
    p_gen = min(1.0, assembly.catalysis_score * config.generation_factor)
    if random.random() < p_gen:
        spawn_block_near_assembly(state, assembly, id_gen)

    # Formation bonus is applied during handle_collisions, not here
    # Just mark the assembly's range for the collision handler to check
```

#### 3.4: Formation Bonus in Collision Handler

In `handle_collisions()`, when computing formation probability:
```python
bonus_a = get_catalysis_bonus(state, a_id)
bonus_b = get_catalysis_bonus(state, b_id)
effective_a = min(1.0, a.formation_reactivity + bonus_a)
effective_b = min(1.0, b.formation_reactivity + bonus_b)
prob = (effective_a + effective_b) / 2
```

```python
def get_catalysis_bonus(state, block_id):
    block = state.blocks[block_id]
    max_bonus = 0.0
    for asm in state.assemblies.values():
        if not asm.is_catalytic:
            continue
        # Check if block is within range of any assembly block
        for mol_id in asm.molecule_ids:
            for bid in state.molecules[mol_id].block_ids:
                if block.position.distance_to(state.blocks[bid].position) < state.config.catalysis_range:
                    bonus = asm.catalysis_score * state.config.reactivity_bonus_factor
                    max_bonus = max(max_bonus, bonus)
                    break  # found one in range, no need to check more blocks in this molecule
    return max_bonus
```

**Performance note:** This is O(catalysts * blocks_per_catalyst * colliding_blocks). For small numbers of catalysts, this is fine. If performance becomes an issue, use the spatial hash to only check catalysts near the collision.

#### 3.5: Rendering Updates

- Catalytic assemblies: gold border (`(255, 215, 0)`) around all constituent blocks
- Catalysis range: faint translucent gold circle
- Newly spawned blocks: brief white flash for ~10 frames
- Legend panel: add catalyst color swatch and range indicator

### Phase 3 Testing Checklist

- [ ] Assemblies become catalytic at expected rate
- [ ] Catalysis score computed correctly from block properties
- [ ] New blocks spawn within catalysis range
- [ ] Formation reactivity bonus applies to blocks in range
- [ ] Bonus is temporary (doesn't modify stored property)
- [ ] Multiple catalysts: max bonus used, not cumulative
- [ ] Catalyst visualization: gold border, range circle
- [ ] Scenario test: pre-built catalytic assembly, verify spawning and bonus

---

## 9. Phase 4: Live Graphs & Data Export

### Prerequisites
All prior phases complete. History tracking active since Phase 1.

### What Phase 4 Adds
- Live graph in the UI showing metrics over time
- CSV export of historical data
- Expanded metric tracking
- Optional: save/load simulation state

### Implementation Steps

#### 4.1: Expand History Tracking

Add to `record_history()`:
```python
state.history["num_assemblies"].append(len(state.assemblies))
state.history["num_catalytic"].append(sum(1 for a in state.assemblies.values() if a.is_catalytic))
state.history["avg_catalysis_score"].append(
    mean(a.catalysis_score for a in state.assemblies.values()) if state.assemblies else 0
)
state.history["total_blocks_generated"].append(total_blocks_generated_counter)
```

#### 4.2: Graph Panel

Option A: **Pygame primitives** (simpler, no extra dependency)
- Dedicate bottom 200px of the simulation area to a graph
- Plot selected metric as a line graph
- Auto-scale Y axis
- Cycle metrics with G key

Option B: **Matplotlib rendering** (prettier)
```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

def render_graph(history, metric, width, height):
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    ax.plot(history["tick"], history[metric])
    ax.set_xlabel("Tick")
    ax.set_ylabel(metric)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    raw = canvas.get_renderer().tostring_rgb()
    size = canvas.get_width_height()
    surface = pygame.image.fromstring(raw, size, "RGB")
    plt.close(fig)
    return surface
```

#### 4.3: CSV Export

```python
import csv
from datetime import datetime

def export_csv(state):
    filename = f"sim_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        headers = list(state.history.keys())
        writer.writerow(headers)
        rows = zip(*[state.history[h] for h in headers])
        writer.writerows(rows)
    print(f"Exported to {filename}")
```

Triggered by pressing E key.

#### 4.4: Save/Load State (Stretch Goal)

Serialize `SimulationState` to JSON:
- Vector2 -> [x, y]
- Enum -> string
- All other fields are already JSON-compatible

```python
def save_state(state, path):
    data = serialize_state(state)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_state(path):
    with open(path) as f:
        data = json.load(f)
    return deserialize_state(data)
```

### Phase 4 Testing Checklist

- [ ] History records all metrics at configured interval
- [ ] Graph displays and updates in real-time
- [ ] Metric cycling with G key works
- [ ] CSV export produces valid file with correct data
- [ ] Save/load round-trips without data loss (if implemented)

---

## 10. Rendering & UI

### Window Layout

```
Total window: config.window_width x config.window_height (default 1200 x 800)

+--------------------------------------------+------------------+
|                                            |                  |
|          SIMULATION AREA                   |   LEGEND PANEL   |
|          (window_width - 200) x height     |   200px wide     |
|                                            |                  |
+--------------------------------------------+------------------+
```

### Legend Panel Contents (cumulative by phase)

**Phase 1:**
- Title: "LEGENDS"
- Formation Reactivity: vertical gradient bar (blue to red), labeled 0.0-1.0
- Bond Strength: vertical gradient bar (green to red), labeled 0.0-1.0
- Stats section: Tick, Blocks, Bonds, Molecules, Avg N
- Controls section: key shortcuts

**Phase 2:**
- H-Bond: cyan dashed line sample
- Assemblies count in stats

**Phase 3:**
- Catalyst: gold glow sample
- Catalytic assemblies count in stats

**Phase 4:**
- Graph below simulation area or as togglable overlay

### Keyboard Controls (all phases)

| Key | Action | Phase |
|-----|--------|-------|
| SPACE | Pause/resume | 1 |
| RIGHT | Step 1 tick (paused only) | 1 |
| UP | Increase speed multiplier | 1 |
| DOWN | Decrease speed multiplier | 1 |
| R | Reset simulation | 1 |
| D | Toggle debug overlay | 1 |
| ESC | Quit | 1 |
| G | Cycle graph metric | 4 |
| E | Export CSV | 4 |

### Debug Overlay (D key)

- Block ID numbers drawn next to each block
- Velocity vectors as thin lines from block center
- Spatial hash grid lines (faint gray)
- Molecule bounding boxes (faint outline)
- Click-to-inspect: clicking a block while paused prints its full state to console

---

## 11. Configuration System

### Config Loading Priority

1. Hardcoded defaults in `SimConfig` dataclass
2. JSON file overrides (any field not in JSON keeps default)
3. CLI arguments (future: `--num-blocks 100`)

### JSON Format

**Default config (`configs/default.json`):**
```json
{
    "num_blocks": 50,
    "window_width": 1200,
    "window_height": 800,
    "speed_scale": 2.0,
    "hydrolysis_interval": 60
}
```

**Scenario config (`configs/scenarios/two_block_test.json`):**
```json
{
    "window_width": 800,
    "window_height": 600,
    "scenario_blocks": [
        {
            "position": [200, 300],
            "velocity": [3.0, 0.0],
            "mobility": 0.5,
            "formation_reactivity": 0.9,
            "breaking_reactivity": 0.1,
            "h_bond_type": "donor",
            "latent_catalytic_potential": 0.5
        },
        {
            "position": [600, 300],
            "velocity": [-3.0, 0.0],
            "mobility": 0.5,
            "formation_reactivity": 0.9,
            "breaking_reactivity": 0.1,
            "h_bond_type": "acceptor",
            "latent_catalytic_potential": 0.3
        }
    ]
}
```

### CLI Usage

```bash
# Default simulation
python main.py

# With config file
python main.py configs/default.json

# Scenario mode
python main.py configs/scenarios/two_block_test.json

# Verbose logging
python main.py --verbose
python main.py configs/default.json --verbose
```

---

## 12. Testing & Debugging

### Scenario-Based Testing

Create scenario configs for specific test cases:

1. **`two_block_test.json`**: Two blocks aimed at each other. Test bond formation.
2. **`chain_growth.json`**: Many blocks with high reactivity in a small area. Test chain growth.
3. **`hydrolysis_test.json`**: Pre-bonded blocks with high breaking_reactivity. Test breaking.
4. **`wall_bounce.json`**: Block aimed at corner. Test wall reflection.
5. **`assembly_test.json`** (Phase 2): Two N=5 molecules with matching H-bond types.
6. **`catalyst_test.json`** (Phase 3): Pre-built catalytic assembly with nearby free blocks.

### Logging

With `--verbose`:
```
[TICK 42] BOND FORMED: Block 3 + Block 7 (prob=0.65, rolled=0.42) -> Molecule 12
[TICK 42] DEFLECT: Block 5 + Block 9 (prob=0.30, rolled=0.88)
[TICK 60] HYDROLYSIS: Bond 4 BROKE (prob=0.25, rolled=0.18) -> Molecule 12 split into Molecule 15 (3 blocks) + free Block 7
[TICK 120] ASSEMBLY: Molecule 15 + Molecule 18 -> Assembly 1 (H-bond match, prob=0.35, rolled=0.21)
```

### Debug Overlay Features

1. **Block IDs**: Small text next to each block showing its ID
2. **Velocity arrows**: Thin lines from block center showing direction and relative speed
3. **Spatial hash grid**: Faint grid lines showing hash cell boundaries
4. **Click-to-inspect**: Print full block state to console:
   ```
   === Block 7 ===
   Position: (342.5, 218.3)
   Velocity: (1.2, -0.8)
   Mobility: 0.45
   Formation Reactivity: 0.72
   Breaking Reactivity: 0.15
   H-Bond Type: DONOR
   Catalytic Potential: 0.63
   Bonds: [4, 8]
   Molecule: 12
   Assembly: None
   ```

### Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Blocks clipping through walls | Wall bounce not checking all blocks in molecule | Check every block in molecule/assembly, not just anchor |
| Molecules overlapping without collision | Spatial hash cell too small | Cell size must be >= bond_length |
| Bonds forming between same-molecule blocks | Missing same-molecule check in collision detection | Skip pairs where both blocks have same molecule_id |
| Molecule drifting apart | Offsets not recomputed after merge | Always snap block positions after any structural change |
| Performance drops with many blocks | O(N^2) collision without spatial hash | Ensure spatial hash is being used, not brute force |
| Blocks stuck together after deflection | Insufficient separation distance | Add overlap correction in deflect() |
