# Molecular Evolution Simulator - Formula Reference

All mathematical formulas used in the simulation, organized by category.
Each formula includes variable definitions and which module/function uses it.

---

## Table of Contents

1. [Movement & Physics](#1-movement--physics)
2. [Chemistry - Bonding](#2-chemistry---bonding)
3. [Chemistry - Assembly (Phase 2)](#3-chemistry---assembly-phase-2)
4. [Chemistry - Catalysis (Phase 3)](#4-chemistry---catalysis-phase-3)
5. [Color Mapping](#5-color-mapping)
6. [Configuration Parameters](#6-configuration-parameters)

---

## 1. Movement & Physics

**Module:** `src/physics.py`

### 1.1 Block Speed

```
speed = mobility * speed_scale
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `mobility` | float | 0.0 - 1.0 | Block's intrinsic mobility property |
| `speed_scale` | float | config | Global multiplier converting mobility to pixels/tick |
| `speed` | float | >= 0 | Resulting speed in pixels per tick |

**Used in:** `physics.move_all()` for free blocks (not in any molecule).

---

### 1.2 Molecule Mobility

```
mobility_mol = max(0.01, mean(block_i.mobility for i in molecule.block_ids) - molec_mobility_penalty * N)
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `block_i.mobility` | float | 0.0 - 1.0 | Each constituent block's mobility |
| `N` | int | >= 2 | Number of blocks in the molecule (`len(molecule.block_ids)`) |
| `molec_mobility_penalty` | float | config | Penalty per block (represents increasing mass) |
| `mobility_mol` | float | >= 0.01 | Effective mobility of the molecule |

**Floor of 0.01** prevents molecules from becoming completely immobile.

**Used in:** `physics.move_all()` to compute molecule speed: `speed_mol = mobility_mol * speed_scale`

---

### 1.3 Assembly Mobility (Phase 2)

```
mobility_asm = max(0.01, mean(mobility_mol_j for j in assembly.molecule_ids) - assembly_mobility_penalty * M)
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `mobility_mol_j` | float | >= 0.01 | Computed mobility of each constituent molecule (from 1.2) |
| `M` | int | >= 2 | Number of molecules in the assembly |
| `assembly_mobility_penalty` | float | config | Penalty per molecule in assembly |
| `mobility_asm` | float | >= 0.01 | Effective mobility of the assembly |

**Used in:** `physics.move_all()` to compute assembly speed: `speed_asm = mobility_asm * speed_scale`

---

### 1.4 Position Update (per tick)

```
For free blocks:
    block.position = block.position + block.velocity

For molecules:
    anchor.position = anchor.position + molecule.velocity
    for each block_id in molecule.block_ids:
        block.position = anchor.position + molecule.offsets[block_id]

For assemblies (Phase 2):
    asm_anchor_mol.anchor.position = asm_anchor_mol.anchor.position + assembly.velocity
    for each mol_id in assembly.molecule_ids:
        mol_anchor.position = asm_anchor.position + assembly.offsets[mol_id]
        for each block_id in molecule.block_ids:
            block.position = mol_anchor.position + molecule.offsets[block_id]
```

| Variable | Type | Description |
|----------|------|-------------|
| `block.position` | Vector2 | Absolute world position of the block |
| `block.velocity` | Vector2 | Velocity vector (free blocks only) |
| `molecule.velocity` | Vector2 | Velocity vector for entire molecule |
| `molecule.offsets[block_id]` | Vector2 | Block's offset from molecule anchor |
| `assembly.velocity` | Vector2 | Velocity vector for entire assembly |
| `assembly.offsets[mol_id]` | Vector2 | Molecule anchor offset from assembly anchor |

**Used in:** `physics.move_all()`

---

### 1.5 Wall Bounce

```
For each axis (x, y):
    if block.position.x < block_radius:
        block.position.x = block_radius
        entity_velocity.x = -entity_velocity.x
    if block.position.x > sim_width - block_radius:
        block.position.x = sim_width - block_radius
        entity_velocity.x = -entity_velocity.x
    (same for y axis with sim_height)
```

| Variable | Type | Description |
|----------|------|-------------|
| `block_radius` | float | config - visual/collision radius of a block |
| `sim_width` | float | Simulation area width (window_width * 0.8 for legend panel) |
| `sim_height` | float | Simulation area height (window_height) |
| `entity_velocity` | Vector2 | Velocity of the block/molecule/assembly this block belongs to |

**For molecules/assemblies:** Check ALL blocks. If ANY block exceeds bounds, reflect the entity velocity on that axis and shift the anchor so the offending block is exactly at the boundary.

**Used in:** `physics.wall_bounce()`, `physics.wall_bounce_molecule()`

---

### 1.6 Elastic Deflection (No Bond Formed)

```
normal = normalize(block_b.position - block_a.position)
rel_vel = vel_a - vel_b
vel_along_normal = dot(rel_vel, normal)

if vel_along_normal > 0:    # only if approaching
    impulse = normal * vel_along_normal
    vel_a = vel_a - impulse
    vel_b = vel_b + impulse

# Separation (prevent overlap)
overlap = bond_length - distance(block_a.position, block_b.position)
if overlap > 0:
    separation = normal * (overlap / 2 + 0.5)
    shift_entity(a, -separation)
    shift_entity(b, +separation)
```

| Variable | Type | Description |
|----------|------|-------------|
| `normal` | Vector2 | Unit vector from block A to block B (collision axis) |
| `rel_vel` | Vector2 | Relative velocity of A with respect to B |
| `vel_along_normal` | float | Component of relative velocity along collision normal |
| `impulse` | Vector2 | Velocity change applied to both entities |
| `vel_a`, `vel_b` | Vector2 | Entity velocities (molecule velocity if in molecule, else block velocity) |

**Equal mass assumption** for simplicity. Both entities receive equal and opposite impulse.

**Used in:** `physics.deflect()` or `chemistry.handle_collisions()` when bond fails to form.

---

### 1.7 Velocity on Merge (Bond Formation)

```
combined_vel = (vel_a * N_a + vel_b * N_b) / (N_a + N_b)
new_mobility = compute_molecule_mobility(merged_molecule)
new_speed = new_mobility * speed_scale
merged_velocity = normalize(combined_vel) * new_speed
```

| Variable | Type | Description |
|----------|------|-------------|
| `vel_a`, `vel_b` | Vector2 | Velocities of the two merging entities |
| `N_a`, `N_b` | int | Block counts (1 for free block, molecule.n for molecule) |
| `combined_vel` | Vector2 | Momentum-weighted average direction |
| `new_mobility` | float | Computed from formula 1.2 for the merged molecule |
| `new_speed` | float | Speed derived from new mobility |
| `merged_velocity` | Vector2 | Final velocity of the merged molecule |

**Conservation of momentum** determines direction, mobility determines magnitude.

**Used in:** `chemistry.form_bond()`, `chemistry.merge_molecules()`

---

### 1.8 Velocity on Split (Bond Breaking)

```
perturbation = Vector2(uniform(-0.3, 0.3), uniform(-0.3, 0.3))
direction = normalize(old_molecule.velocity + perturbation)
frag_mobility = compute_molecule_mobility(fragment)
frag_velocity = direction * frag_mobility * speed_scale
```

| Variable | Type | Description |
|----------|------|-------------|
| `perturbation` | Vector2 | Small random directional offset so fragments diverge |
| `old_molecule.velocity` | Vector2 | Velocity of the molecule before it split |
| `frag_mobility` | float | Computed from formula 1.2 for the fragment |
| `frag_velocity` | Vector2 | Velocity assigned to the fragment |

**For single-block fragments (N=1):** Use `block.mobility` directly instead of `compute_molecule_mobility`.

**Used in:** `chemistry.split_molecule()`

---

## 2. Chemistry - Bonding

**Module:** `src/chemistry.py`

### 2.1 Bond Formation Probability

```
P_bond = (block_a.formation_reactivity + block_b.formation_reactivity) / 2
Bond forms if: random() < P_bond
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `block_a.formation_reactivity` | float | 0.0 - 1.0 | Block A's tendency to form bonds |
| `block_b.formation_reactivity` | float | 0.0 - 1.0 | Block B's tendency to form bonds |
| `P_bond` | float | 0.0 - 1.0 | Probability of bond forming on this collision |

**Prerequisites:** Both blocks must have `len(bond_ids) < 2` (can_bond check).

**With catalysis bonus (Phase 3):**
```
effective_reactivity_a = min(1.0, block_a.formation_reactivity + catalysis_bonus_a)
effective_reactivity_b = min(1.0, block_b.formation_reactivity + catalysis_bonus_b)
P_bond = (effective_reactivity_a + effective_reactivity_b) / 2
```

**Used in:** `chemistry.handle_collisions()`

---

### 2.2 Bond Breaking Probability (Hydrolysis)

```
P_break = (block_a.breaking_reactivity + block_b.breaking_reactivity) / 2
Bond breaks if: random() < P_break
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `block_a.breaking_reactivity` | float | 0.0 - 1.0 | Block A's susceptibility to hydrolysis |
| `block_b.breaking_reactivity` | float | 0.0 - 1.0 | Block B's susceptibility to hydrolysis |
| `P_break` | float | 0.0 - 1.0 | Probability of bond breaking this hydrolysis check |

**Checked every `hydrolysis_interval` ticks**, not every tick.

**Used in:** `chemistry.hydrolysis_step()`

---

### 2.3 Bond Breaking with Assembly Protection (Phase 2)

```
P_break_base = (block_a.breaking_reactivity + block_b.breaking_reactivity) / 2

if both blocks are in the same assembly AND both participate in H-bonds:
    P_break = max(0, P_break_base - assembly_bond_resistance)
else:
    P_break = P_break_base
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `assembly_bond_resistance` | float | config | Penalty subtracted from break probability for protected bonds |
| `P_break` | float | 0.0 - 1.0 | Final adjusted break probability |

**Key rule:** Only bonds where BOTH constituent blocks participate in H-bonding get assembly protection. Bonds at the edges of molecules (not H-bonded) do NOT get protection.

**Used in:** `chemistry.hydrolysis_step()` (Phase 2+)

---

## 3. Chemistry - Assembly (Phase 2)

**Module:** `src/chemistry.py`

### 3.1 Assembly Eligibility

```
can_assemble = (
    N_a >= min_assembly_n
    AND N_b >= min_assembly_n
    AND full_hbond_match(mol_a, mol_b) == True
    AND neither block is a single free block
)
```

| Variable | Type | Description |
|----------|------|-------------|
| `N_a`, `N_b` | int | Block counts of the two colliding molecules |
| `min_assembly_n` | int | config - minimum molecule size for assembly (default 5) |
| `full_hbond_match` | bool | Every donor in mol_a pairs with an acceptor in mol_b and vice versa |

**H-bond matching:** Walk both molecule chains simultaneously. At each position, check that one block is DONOR and the other is ACCEPTOR. ALL pairs must match (full correspondence). The molecules must have the same N for full matching.

**Used in:** `chemistry.handle_collisions()`

---

### 3.2 Assembly Chance

```
P_assembly = base_assembly_chance * (min(N_a, N_b) / min_assembly_n) * (1 + assembly_growth_bonus * M)
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `base_assembly_chance` | float | config | Base probability of assembly formation |
| `N_a`, `N_b` | int | >= min_assembly_n | Block counts of the two molecules |
| `min_assembly_n` | int | config | Minimum molecule size for assembly |
| `assembly_growth_bonus` | float | config | Bonus per existing molecule in assembly (encourages growth) |
| `M` | int | >= 0 | Current number of molecules in the assembly (0 for new assembly) |
| `P_assembly` | float | 0.0 - 1.0 | Probability of assembly forming/growing |

**Scaling rationale:** Larger molecules (higher N) are more likely to assemble. Existing assemblies (higher M) attract more molecules.

**Used in:** `chemistry.handle_collisions()` when assembly is eligible

---

### 3.3 Weighted Collision Outcome (Both Bond + Assembly Possible)

```
When both bonding and assembly are possible for a collision:

W_bond = (block_a.formation_reactivity + block_b.formation_reactivity) / 2
W_assembly = P_assembly  (from formula 3.2)

total = W_bond + W_assembly
P_bond_outcome = W_bond / total
P_assembly_outcome = W_assembly / total

roll = random()
if roll < P_bond_outcome:
    attempt bond formation (still subject to the probability roll)
else:
    attempt assembly formation (still subject to the probability roll)
```

| Variable | Type | Description |
|----------|------|-------------|
| `W_bond` | float | Weight for bond outcome |
| `W_assembly` | float | Weight for assembly outcome |
| `P_bond_outcome` | float | Normalized probability of choosing bond path |
| `P_assembly_outcome` | float | Normalized probability of choosing assembly path |

**Two-stage process:** First pick which outcome to attempt (weighted), then roll the actual probability for that outcome.

**Used in:** `chemistry.handle_collisions()` when both are possible

---

### 3.4 Extended Assembly Displacement Rule

```
When Mol A collides with Mol B, and Mol B is in an assembly H-bonded on BOTH sides:

    Mol C = the molecule on the other side of Mol B from the collision

    if N_A > N_C:
        remove Mol C from assembly
        add Mol A to assembly (if H-bond match with Mol B)
    else:
        nothing happens (collision deflects)
```

| Variable | Type | Description |
|----------|------|-------------|
| `N_A` | int | Block count of the incoming molecule |
| `N_C` | int | Block count of the molecule to be potentially displaced |

**Used in:** `chemistry.handle_collisions()` (Phase 2)

---

## 4. Chemistry - Catalysis (Phase 3)

**Module:** `src/chemistry.py`

### 4.1 Catalysis Roll

```
When an assembly forms or a molecule is added to an existing assembly:

    if random() < catalysis_chance:
        assembly.is_catalytic = True
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `catalysis_chance` | float | config | Probability of becoming catalytic on formation/growth |

**Only rolled once** per assembly formation or growth event. An assembly that is already catalytic stays catalytic.

**Used in:** `chemistry.handle_collisions()` after assembly formation

---

### 4.2 Catalysis Score

```
catalysis_score = sum(block.latent_catalytic_potential for block in all_assembly_blocks) * (1 + catalysis_m_bonus * M)
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `block.latent_catalytic_potential` | float | 0.0 - 1.0 | Each block's intrinsic catalytic potential |
| `catalysis_m_bonus` | float | config | Scaling bonus per molecule in assembly |
| `M` | int | >= 2 | Number of molecules in the assembly |
| `catalysis_score` | float | >= 0 | Overall catalytic power of the assembly |

**Recomputed** whenever the assembly grows (molecule added or removed).

**Used in:** `chemistry.catalysis_step()` to determine generation and bonus effects

---

### 4.3 Block Generation Probability

```
P_generate = min(1.0, catalysis_score * generation_factor)

Checked every catalysis_interval ticks.
If random() < P_generate:
    spawn a new building block with random properties near the assembly
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `catalysis_score` | float | >= 0 | From formula 4.2 |
| `generation_factor` | float | config | Converts score to probability |
| `P_generate` | float | 0.0 - 1.0 | Probability of spawning a new block |
| `catalysis_interval` | int | config | Ticks between catalysis checks |

**Spawn location:** Random position within `catalysis_range` of the assembly's center.

**Used in:** `simulation.step()` -> `chemistry.catalysis_step()`

---

### 4.4 Formation Reactivity Bonus

```
For each block within catalysis_range of a catalytic assembly:

    catalysis_bonus = catalysis_score * reactivity_bonus_factor

Applied during collision handling:
    effective_reactivity = min(1.0, block.formation_reactivity + catalysis_bonus)
```

| Variable | Type | Range | Description |
|----------|------|-------|-------------|
| `catalysis_range` | float | config | Radius of catalytic influence (pixels) |
| `reactivity_bonus_factor` | float | config | Converts score to reactivity bonus |
| `catalysis_bonus` | float | >= 0 | Additive bonus to formation reactivity |

**Temporary effect** - does NOT modify the block's stored property. Applied only during collision probability computation for blocks within range.

**Multiple catalysts:** If a block is in range of multiple catalysts, use the maximum bonus (not cumulative), to prevent runaway effects.

**Used in:** `chemistry.handle_collisions()` (Phase 3)

---

## 5. Color Mapping

**Module:** `src/renderer.py`

### 5.1 Block Color (Formation Reactivity)

```
hue = (1.0 - formation_reactivity) * 240
color = HSV(hue, saturation=100%, value=100%)
```

| Reactivity | Hue | Color |
|-----------|-----|-------|
| 0.0 (low) | 240 | Blue |
| 0.25 | 180 | Cyan |
| 0.5 (mid) | 120 | Green |
| 0.75 | 60 | Yellow |
| 1.0 (high) | 0 | Red |

**Interpretation:** Hot colors (red/yellow) = highly reactive blocks that bond easily. Cool colors (blue/cyan) = inert blocks.

**Used in:** `renderer.draw_blocks()`

---

### 5.2 Bond Color (Breaking Strength)

```
avg_break = (block_a.breaking_reactivity + block_b.breaking_reactivity) / 2
hue = (1.0 - avg_break) * 120
color = HSV(hue, saturation=100%, value=100%)
```

| Break Prob | Hue | Color | Meaning |
|-----------|-----|-------|---------|
| 0.0 (stable) | 120 | Green | Strong bond, resistant to hydrolysis |
| 0.5 (mid) | 60 | Yellow | Moderate bond |
| 1.0 (fragile) | 0 | Red | Weak bond, breaks easily |

**Used in:** `renderer.draw_bonds()`

---

### 5.3 H-Bond Color (Phase 2)

```
color = fixed CYAN (0, 200, 255)
style = dashed line
```

**Used in:** `renderer.draw_bonds()` when `bond.is_h_bond == True`

---

### 5.4 Catalytic Assembly Highlight (Phase 3)

```
highlight_color = GOLD (255, 215, 0)
range_circle_color = GOLD with alpha 30 (255, 215, 0, 30)
```

- Catalytic assemblies get a gold border/glow around all constituent blocks.
- Catalysis range drawn as a faint gold circle centered on the assembly.

**Used in:** `renderer.draw_blocks()`, `renderer.draw_catalyst_range()`

---

## 6. Configuration Parameters

All tunable parameters and their defaults:

### Physics Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `speed_scale` | 2.0 | Multiplier: speed = mobility * speed_scale |
| `block_radius` | 8.0 | Visual and collision radius of a block (pixels) |
| `bond_length` | 16.0 | Distance between bonded block centers (= 2 * block_radius) |

### Chemistry Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hydrolysis_interval` | 60 | Bond breaking checks every N ticks |
| `molec_mobility_penalty` | 0.02 | Mobility reduction per block in a molecule |
| `assembly_bond_resistance` | 0.2 | Subtracted from break probability for H-bonded assembly bonds |
| `assembly_mobility_penalty` | 0.03 | Mobility reduction per molecule in an assembly |
| `base_assembly_chance` | 0.3 | Base probability of assembly formation |
| `assembly_growth_bonus` | 0.1 | Bonus to assembly chance per existing molecule |
| `min_assembly_n` | 5 | Minimum molecule size (N) for assembly eligibility |
| `catalysis_chance` | 0.1 | Probability of becoming catalytic on assembly formation/growth |
| `catalysis_range` | 100.0 | Radius of catalytic influence (pixels) |
| `catalysis_interval` | 60 | Catalysis effects checked every N ticks |
| `generation_factor` | 0.05 | Converts catalysis_score to block generation probability |
| `reactivity_bonus_factor` | 0.02 | Converts catalysis_score to formation reactivity bonus |
| `catalysis_m_bonus` | 0.1 | Catalysis score scaling per molecule in assembly |

### Property Sampling (Normal Distribution)

All building block properties are sampled from a **clamped normal distribution**:

```
value = clamp(N(mean, std), 0.0, 1.0)

Where:
    N(mean, std) = Gaussian/normal random variable with given mean and standard deviation
    clamp(x, lo, hi) = max(lo, min(hi, x))
```

This produces a bell-curve centered at `mean`, with ~68% of values within 1 std of the mean,
~95% within 2 std, clamped to the valid [0, 1] range.

| Property | Mean | Std Dev | ~68% Range | Rationale |
|----------|------|---------|------------|-----------|
| `mobility` | 0.5 | 0.15 | 0.35 - 0.65 | Centered; most blocks moderately mobile |
| `formation_reactivity` | 0.5 | 0.15 | 0.35 - 0.65 | Centered; balanced bond formation rates |
| `breaking_reactivity` | 0.25 | 0.10 | 0.15 - 0.35 | Lower mean; bonds should persist somewhat |
| `latent_catalytic_potential` | 0.5 | 0.20 | 0.30 - 0.70 | Wide spread; catalysis is emergent |

**Config parameters** (all modifiable in `configs/default.json`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mobility_mean` | 0.5 | Mean of mobility normal distribution |
| `mobility_std` | 0.15 | Std dev of mobility normal distribution |
| `formation_reactivity_mean` | 0.5 | Mean of formation reactivity distribution |
| `formation_reactivity_std` | 0.15 | Std dev of formation reactivity distribution |
| `breaking_reactivity_mean` | 0.25 | Mean of breaking reactivity distribution |
| `breaking_reactivity_std` | 0.10 | Std dev of breaking reactivity distribution |
| `latent_catalytic_mean` | 0.5 | Mean of catalytic potential distribution |
| `latent_catalytic_std` | 0.20 | Std dev of catalytic potential distribution |

**Implementation:** `src/simulation.py` -> `_sample_clamped_normal(mean, std)`

### Window Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `window_width` | 1200 | Total window width (pixels) |
| `window_height` | 800 | Total window height (pixels) |
| `target_fps` | 60 | Target frames per second |
| `num_blocks` | 50 | Number of building blocks to generate |
