# Storm-POMDP Benchmarking

Models, scripts, and paper logs for **19 POMDP instances and 34 configurations
(646 runs)**: 32 belief-exploration size limits from 10,000 to 50,000,000 and
static belief discretisation at resolutions 4 and 5.

Run all commands from the repository root.

## Generate results from the paper logs

Requirements:

- Python 3 (standard library only).
- LuaLaTeX with PGFPlots 1.18, PGFPlotstable, and the `standalone` and `llncs` classes.
- `pdftoppm` (Poppler).

Storm is not needed to process the supplied logs:

```sh
python3 scripts/postprocess.py logs-paper
```

Results are written to `data/`:

- `html/index.html`: offline results table with links to individual run logs.
- `plots/runtime-comparison.pdf` and `.png`: the three-panel figure.
- `plots/`: CSV data and LaTeX sources, including `paper-figure.tex`.

To share the HTML results, include the entire `data/html/` folder.

## Run new experiments

Requires a built `storm-pomdp` executable on Linux or macOS. Create a `bin`
symlink to your build's executable directory, or enter the executable path
when prompted:

```sh
ln -s /path/to/storm/build/bin bin
python3 scripts/benchmarks.py
python3 scripts/run.py
```

The first Python command checks the model and property files. The second
creates an invocation file interactively:

1. Choose the executable.
2. Select configuration families and benchmark sets (`a` selects all).
3. Choose the time limit (default **900 seconds**), log directory
   (e.g. `logs-reviewer`), and invocation filename (e.g. `inv-reviewer.json`).

Execute the invocations, then generate their results:

```sh
python3 scripts/run.py inv-reviewer.json
python3 scripts/postprocess.py logs-reviewer
```

For a quick check, append `0` to the execution command to run only the first
invocation. Partial experiments are supported; unavailable runs and bound
references appear as missing data.

Runs execute sequentially; Ctrl+C stops the current run and exits. The full
suite can take up to 161 hours 30 minutes at the default limit, plus overhead.
Use a separate log directory for each experiment. Logs are self-contained;
no per-run JSON files are needed. Record the Storm revision and machine
specifications with new results.

Postprocessing always uses the same `data/` folder and overwrites matching
output files.

## Instances

| Plot label | Benchmark ID | Objective |
| --- | --- | --- |
| Grid-4-0.1 | `grid_grid_rewmin_sl0.1` | Minimise expected reward |
| Grid-4-0.3 | `grid_grid_rewmin_sl0.3` | Minimise expected reward |
| Grid-av-4-0.1 | `grid-avoid_grid-avoid_prbmax_sl0.1` | Maximise reachability probability |
| Rocks-12 | `samplerocks_samplerocks_rewmin_N12` | Minimise expected reward |
| Rocks-16 | `samplerocks_samplerocks_rewmin_N16` | Minimise expected reward |
| Drone-4-1 | `drone_drone_prbmax_N4-R1` | Maximise reachability probability |
| Drone-4-2 | `drone_drone_prbmax_N4-R2` | Maximise reachability probability |
| Drone-5-3 | `drone_drone_prbmax_N5-R3` | Maximise reachability probability |
| Drone-6-3 | `drone_drone_prbmax_N6-R3` | Maximise reachability probability |
| Lanes+ | `lanes-100_lanes-100_rewmin_` | Minimise expected reward |
| Grid-large-30-5 | `grid-large-30-5_grid-large-30-5_rewmin_` | Minimise expected reward |
| Netw-2-8-20 | `network2_network2_rewmin_T8-K20` | Minimise expected reward |
| Netw-3-8-20 | `network3_network3_rewmin_T8-K20` | Minimise expected reward |
| Netw-p-2-8-20 | `network-priorities2_network-priorities2_rewmax_T8-K20` | Maximise expected reward |
| Netw-p-3-8-20 | `network-priorities3_network-priorities3_rewmax_T8-K20` | Maximise expected reward |
| Maze2-0.1 | `maze2_maze2_rewmin_sl0.1` | Minimise expected reward |
| Maze2-0.3 | `maze2_maze2_rewmin_sl0.3` | Minimise expected reward |
| Refuel-06 | `refuel_refuel_prbmax_N06` | Maximise reachability probability |
| Refuel-08 | `refuel_refuel_prbmax_N08` | Maximise reachability probability |

Instance definitions are in `scripts/benchmarkset.py`; configurations are in
`scripts/storm.py`.
