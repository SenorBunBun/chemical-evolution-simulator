# Chemical Evolution Simulator

A simulation of simple chemical "building blocks" floating in a 2D space. They bump into each
other, form bonds, break apart, and gradually assemble into larger molecules. You watch it happen
in a window, in real time.

You do **not** need to know how to code to run this.

---

## 1. Install Python

You need Python 3.10 or newer.

Open a terminal and type:

```
python3 --version
```

If you see something like `Python 3.13.7`, you're set. If you get an error instead, download
Python from [python.org/downloads](https://www.python.org/downloads/) and install it, then try
again.

> **On Windows:** use `python` everywhere this guide says `python3`.

## 2. Install pygame

pygame is the only thing this project needs. Install it with:

```
pip3 install pygame
```

## 3. Run it

From inside this project folder:

```
python3 main.py
```

A window opens and the simulation starts. That's it.

---

## Controls

| Key | What it does |
|-----|--------------|
| `SPACE` | Pause / unpause |
| `UP` / `DOWN` | Run faster / slower |
| `RIGHT` | Advance one step (while paused) |
| `D` | Toggle the debug overlay |
| `R` | Restart the simulation |
| `ESC` | Quit |

While paused **with debug on (`D`)**, click any block to print its full details to the terminal.

---

## Changing things

All settings live in plain text files in the `configs/` folder. Open them in any text editor,
change a number, save, and run `python3 main.py` again to see the effect. No code changes needed.

There are two files:

### `configs/graphics_default.json` — how it *looks*

| Setting | What it does |
|---------|--------------|
| `window_width`, `window_height` | Size of the window, in pixels |
| `target_fps` | How smoothly it animates (60 is normal) |
| `bg_color` | Background color, as `[red, green, blue]` from 0–255 |
| `block_radius` | How big each block is drawn |
| `block_color_by` | **Which property decides a block's color** — see below |
| `block_color_low` | Color for a low value (default blue) |
| `block_color_high` | Color for a high value (default red) |
| `block_outline` | `true` or `false` — draw an outline around bonded blocks |

**Coloring the blocks.** `block_color_by` is the most useful setting for actually *seeing* what's
going on. It accepts exactly one of these five values:

| Value | Blocks are colored by... |
|-------|--------------------------|
| `"formation_reactivity"` | How eagerly a block forms bonds |
| `"breaking_reactivity"` | How easily its bonds fall apart |
| `"mobility"` | How fast it moves |
| `"latent_catalytic_potential"` | How strongly it catalyzes nearby reactions |
| `"h_bond_type"` | Its hydrogen-bond type — donor (blue) vs. acceptor (red) |

The first four fade smoothly from `block_color_low` to `block_color_high`. `"h_bond_type"` is the
odd one out: it's a yes/no property, so it uses two fixed colors and shows a two-swatch legend
instead of a gradient.

For example, to color blocks by hydrogen-bond type:

```json
"block_color_by": "h_bond_type"
```

> Spelling matters. A name that isn't in the table above won't produce an error — every block just
> turns the same flat mid-color. If the window looks uniformly purple, check this line first.

### `configs/simulation_default.json` — how it *behaves*

The ones worth trying first:

| Setting | What it does |
|---------|--------------|
| `num_blocks` | How many blocks to start with (500 by default; lower it if things run slowly) |
| `speed_scale` | How fast blocks move around |
| `assembly_enabled` | `true` or `false` — whether blocks can assemble into larger structures |
| `base_assembly_chance` | How likely assembly is when blocks meet |
| `hydrolysis_interval` | How often bonds get a chance to break (higher = more stable molecules) |
| `catalysis_range` | How far a block's catalytic influence reaches |

Most values sit between `0.0` and `1.0`, where higher means "more likely" or "stronger". The rest
of the file controls finer details of the chemistry — `FORMULAS.md` explains every one of them.

---

## Trying a preset scenario

`configs/scenarios/` holds small pre-built setups for watching one specific behavior. Run one by
naming it:

```
python3 main.py configs/scenarios/two_molecules.json
```

A scenario only overrides the settings it mentions; everything else falls back to
`simulation_default.json`.

## Running without a window

To run the simulation fast with no graphics and collect results into a spreadsheet:

```
python3 main.py --headless
```

Results are written to `output/headless_results.csv`. To turn those into charts:

```
pip3 install matplotlib pandas numpy
python3 plot_results.py
```

---

## If something goes wrong

**`ModuleNotFoundError: No module named 'pygame'`**
pygame didn't install, or installed for a different Python. Try `python3 -m pip install pygame`.

**`python3: command not found`**
Python isn't installed, or isn't on your PATH. Reinstall from python.org and tick
"Add Python to PATH" during setup.

**The window opens but everything is one flat color**
`block_color_by` is misspelled. See the table above for the five valid values.

**It runs very slowly**
Lower `num_blocks` in `configs/simulation_default.json`.

---

## Further reading

- `FORMULAS.md` — every equation and configuration value, explained
- `IMPLEMENTATION_GUIDE.md` — how the code is put together
