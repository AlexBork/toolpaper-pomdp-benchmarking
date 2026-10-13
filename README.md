# Storm-POMDP Benchmarking

The current experiment suite contains **19 instances and 35 configurations
(665 runs)**: 32 explicit cut-offs from 10,000 to 50,000,000, static
discretisation at resolutions 4 and 5, and the fully observable MDP reference.

## Running the experiments

The Python utilities use the standard library. The runner requires a built
`storm-pomdp` executable and POSIX process groups (Linux or macOS).

The default executable path is `$BENCH_HOME/bin/storm-pomdp`. The runner
replaces `$BENCH_HOME` with this repository's root; no environment variable
needs to be set. From the repository root, create a `bin` symlink to the
directory containing your built Storm executables:

```sh
ln -s /path/to/storm/build/bin bin
```

Replace `/path/to/storm/build/bin` with your build's actual `bin` directory.
Then run these commands from the repository root:

```sh
python3 scripts/benchmarks.py
python3 scripts/run.py
```

The first command checks the model/property files and lists the registered
instances. The second creates an invocation file interactively:

1. Accept the default executable path to use the `bin` symlink, or enter
   another path to your `storm-pomdp` executable.
2. Select `a` in both the configuration-family and benchmark-set menus to
   include the full suite.
3. Choose the common time limit (default **600 seconds**), a log directory,
   and an invocation filename.

Menus also accept option numbers, identifiers, `c` (clear), and `d` (done).
Use a separate log directory for each experiment. Then execute the generated
invocation file:

```sh
python3 scripts/run.py inv-toolpaper.json
```

Runs execute sequentially. To run just one invocation, append its zero-based
index, for example `python3 scripts/run.py inv-toolpaper.json 0`. The runner
writes one `.log` and `.json` per invocation into the selected log directory.
Keep both files for postprocessing. Existing invocation files retain their
stored commands and time limits.

The timeout sends SIGKILL to the entire benchmark process group immediately,
without a termination grace period. The full suite's worst-case runtime at
600 seconds per run is 110 hours 50 minutes, plus overhead. A previous full
run took about 6.6 hours; runtime and failures depend on the machine. Record
the Storm revision, CPU, RAM, and external resource limits with the results.

## Benchmark configuration

Instances are declared in `scripts/benchmarkset.py`; configurations are in
`scripts/storm.py`. All instances use the same 32 cut-offs:

| Range | Tested thresholds |
| --- | --- |
| Ten thousands | 10,000, 20,000, …, 90,000 |
| Hundred thousands | 100,000, 200,000, …, 900,000 |
| Millions | 1,000,000, 2,000,000, …, 9,000,000 |
| Ten millions | 10,000,000, 20,000,000, 30,000,000, 40,000,000, 50,000,000 |

The instance families are grid, grid-avoid, samplerocks, drone, lanes,
grid-large, network, network-priorities, maze2, and refuel. The suite includes
14 of the 15 instances in Tables 1 and 2 of the
[TACAS 2022 paper](https://doi.org/10.1007/978-3-030-99527-0_2), plus five
additional instances. Grid-avoid/sl0 is excluded; the additional instances
are Drone N5-R3, Drone N6-R3, lanes-100, grid-large-30-5, and maze2/sl0.3.

## Postprocessing

```sh
python3 scripts/postprocess.py logs/toolpaper
```

Replace `logs/toolpaper` with the directory chosen during invocation creation.
The postprocessor reads source logs without modifying them and writes:

- `data/execution-data.json` and `benchmark-data.json`: parsed results and
  model statistics.
- `data/runtime-report.md` and `runtime-*.csv`: cumulative runtimes, outcomes,
  and per-run audits.
- `data/html/index.html`: an offline sortable/filterable table, with links
  to per-run commands, metadata, and logs. Share the entire `data/html/`
  directory to include its styles, script, and log pages.
- Shared CSV data, reusable TeX commands, and a per-instance plot preview.

Failures remain in the exports. A non-timeout SIGKILL is reported as
`killed`, which does not establish its cause. Runtime totals include failed
runs; derived best configurations are excluded from totals and the HTML
table. Bounds are compared separately for cut-offs and over-approximation
references, respecting minimisation/maximisation and breaking ties by runtime.
The audit CSV files are tab-separated; plotting CSVs use commas.

Use `--output-dir` to choose another export directory. The HTML table can
also be regenerated from existing exports with `python3 scripts/html_results.py`.
Historical dissertation outputs are optional via `--legacy-outputs`.

## Existing plot utilities

The per-instance plots use `data/cutoff-threshold-plot-data.csv` and
`data/pomdp-instance-plots.tex`:

```tex
% Document preamble:
\input{data/pomdp-instance-plots.tex}
\StormPOMDPLoadData{data/cutoff-threshold-plot-data.csv}
% Document body:
\StormPOMDPValuePlot{drone_drone_prbmax_N6-R3}
\StormPOMDPRuntimePlot[width=7cm,height=5cm]{drone_drone_prbmax_N6-R3}
```

Compile the generated instance preview from `data/`:

```sh
cd data
lualatex --interaction=nonstopmode --halt-on-error cutoff-threshold-preview.tex
```

The existing exploratory summary plots are separate from experiment execution:

```sh
python3 scripts/toolpaper_plots.py --compile
```

They use the audited exports and successful source logs, producing CSV-backed
commands and a combined preview under `data/general-plots/pomdp-tool-paper/`.
That directory's generated README documents the commands and metrics. Their
plot design is still being reconsidered. LuaLaTeX and `pdftoppm` are optional
requirements for PDF/PNG generation. Experimental data and generated exports
are ignored by Git.
