# Storm-POMDP Benchmarking

This artefact contains models, experiment scripts, and the paper's execution
logs for **19 POMDP instances and 34 configurations (646 runs)**. The
configurations comprise 32 belief-exploration size limits from 10,000 to
50,000,000 and two over-approximations using static belief discretisation
at resolutions 4 and 5.

All commands below run from the repository root.

## Regenerate the paper results

The supplied `logs-paper/` directory contains all 646 self-contained logs.
Generating HTML and plots from these logs does not require Storm.

Requirements:

- Python 3; the Python scripts use only the standard library.
- LuaLaTeX with PGFPlots 1.18, PGFPlotstable, and the `standalone` and `llncs` classes.
- `pdftoppm`, supplied by Poppler, for PNG rendering.

Run:

```sh
python3 scripts/postprocess.py logs-paper
```

Open `data/html/index.html` in a browser to inspect the results, or view
`data/plots/runtime-comparison.pdf` and `.png` for the three-panel figure.
The HTML works offline and supports sorting, filtering, configuration toggles,
and bound/runtime views. Each result links to a page containing the invocation,
metadata, and source log. Share the entire `data/html/` folder, including its
CSS, JavaScript, and `logs/` subfolder.

The supplied runs used a **900-second time limit**. Their cumulative recorded
runtime is **5 hours 54 minutes 42 seconds**, including unsuccessful runs.
This is the sum of run times, rather than the elapsed duration of a parallel batch.

## Run new experiments

Running benchmarks additionally requires a built `storm-pomdp` executable and
POSIX process groups (Linux or macOS). Record the Storm revision, CPU, RAM,
and external resource limits when collecting results.

The default executable is `$BENCH_HOME/bin/storm-pomdp`. The runner replaces
`$BENCH_HOME` with this repository's root; no environment variable is needed.
Create a `bin` symlink to the directory containing your Storm executables:

```sh
ln -s /path/to/storm/build/bin bin
```

Replace the example path with your build's actual `bin` directory. Alternatively,
enter your executable's path when the runner prompts for it.

Check the model/property files and create an invocation file:

```sh
python3 scripts/benchmarks.py
python3 scripts/run.py
```

In the interactive runner:

1. Accept the default executable or enter its path.
2. Select the `cutoff` and `discretisation` families, or `a` for both.
3. Select benchmark sets, or `a` for the full suite.
4. Choose a time limit, log directory, and invocation filename. For example,
   use `logs-reviewer` and `inv-reviewer.json`.

The time limit defaults to **900 seconds**, matching the paper logs.
Menus accept option numbers or identifiers, `a` (all), `c` (clear), and
`d` (done). Selecting `a` finishes that menu immediately.
Use a separate log directory for each experiment.

Execute the saved invocations:

```sh
python3 scripts/run.py inv-reviewer.json
```

For a first check, execute only invocation 0:

```sh
python3 scripts/run.py inv-reviewer.json 0
```

Runs execute sequentially. Ctrl+C kills the current benchmark process group
and exits the runner. A timeout immediately sends SIGKILL to the process
group. Runner errors produce a nonzero exit code after the remaining
invocations have been attempted.

At the default 900 seconds per run, the full suite's worst-case runtime is
161 hours 30 minutes, plus overhead. Actual runtime depends on the machine
and the selected instances.

Each invocation writes one self-contained `.log` containing its command,
benchmark, configuration, time limit, runtime, and return code. The invocation
JSON schedules runs; no per-run JSON sidecar is generated or required.
Existing invocation files retain their stored commands and time limits.

Generate HTML and plots from the new runs with the same postprocessor:

```sh
python3 scripts/postprocess.py logs-reviewer
```

All postprocessing writes to the single **`data/`** folder and overwrites
matching output files. Processing a partial experiment is supported: missing
runs and unavailable bound references appear as missing data. For example,
a single cut-off run has no over-approximation reference until discretisation
runs for that instance are available. Legacy JSON/log pairs are also accepted.

## Generated files

Paths below are relative to `data/`:

| Path | Contents |
| --- | --- |
| `html/index.html` | Interactive results table. |
| `html/logs/` | One page per measured run, including its source log. |
| `html/results.css`, `html/results.js` | Assets needed by the offline HTML export. |
| `README.md` | Guide to the generated files. |
| `plots/runtime-comparison.tex`, `.pdf`, `.png` | Standalone source and rendered three-panel figure. |
| `plots/paper-figure.tex` | Figure environment, caption, and label for a paper. |
| `plots/aggregate-plots.tex` | Reusable PGFPlots commands. |
| `plots/plot-series.csv` | Instance names and axis/failure-line settings. |
| `plots/plot-curves.csv` | Compact data read by PGFPlots. |
| `plots/plot-data.csv` | Per-cut-off runtimes, outcomes, bounds, references, gaps, and exploration counts when available. |

All CSV files use commas. `plot-curves.csv` contains one threshold per row,
with `runtime_N`, `under_gap_N`, and `over_gap_N` columns for each instance
index `N` in `plot-series.csv`. Missing values use `nan`.
Successful plot builds remove temporary LaTeX files; failed builds retain
logs for diagnosis. Source benchmark logs are read without modification.
Generated outputs are ignored by Git.

## Benchmark configuration

Instances are declared in `scripts/benchmarkset.py`; configurations are in
`scripts/storm.py`. The instance families are grid, grid-avoid, samplerocks,
drone, lanes, grid-large, network, network-priorities, maze2, and refuel.
All instances use the same 32 size limits:

| Range | Tested thresholds |
| --- | --- |
| Ten thousands | 10,000, 20,000, …, 90,000 |
| Hundred thousands | 100,000, 200,000, …, 900,000 |
| Millions | 1,000,000, 2,000,000, …, 9,000,000 |
| Ten millions | 10,000,000, 20,000,000, 30,000,000, 40,000,000, 50,000,000 |

The suite includes 14 of the 15 instances in Tables 1–2 of the
[TACAS 2022 paper](https://doi.org/10.1007/978-3-030-99527-0_2), plus five
additional instances. Grid-avoid/sl0 is excluded; the additions are Drone
N5-R3, Drone N6-R3, lanes-100, grid-large-30-5, and maze2/sl0.3.

## Interpreting the plots

The three panels show runtime, relative gap to the best computed
under-approximation, and relative gap to the best computed over-approximation.
All use the configured size limit on the horizontal axis. Size limits and
runtimes use logarithmic scales; gaps use linear scales.

For each instance, the under-approximation reference is the best successful
cut-off bound: the highest lower bound for maximisation or the lowest upper
bound for minimisation. The over-approximation reference is the tightest
successful bound from static belief discretisation at resolutions 4 and 5:
the smallest upper bound for maximisation or the largest lower bound for
minimisation. Runtime breaks exact numerical ties.

Both gap panels use:

```text
100 * abs(bound - reference) / max(abs(bound), abs(reference))
```

The gap is zero when both values are zero. The centre panel measures progress
relative to the best observed cut-off bound. The right panel measures relative
interval width against the over-approximation. Reference configurations,
values, and runtimes are recorded in `plot-data.csv`; their runtimes are not
added to the plotted cut-off runs.

Failure markers occupy categorical lines above the numeric range: `TO` for
timeouts, `MO` for memory exhaustion (including non-timeout SIGKILLs), and
`Failed` for other failures when present. A SIGKILL alone does not establish
memory exhaustion: it remains `killed` in the CSV's `status` column and is
mapped to `memout` in `plot_status` for plotting. Measured runtimes remain
in the CSV; failed runs supply no numeric bound or explored-belief point.

Each instance has a consistent colour and marker across all panels. The
figure uses the Tol vibrant palette, 6 pt lettering, and a shared legend
at LNCS text width (12.2 cm). Legend names follow the
[TACAS 2022](https://arxiv.org/pdf/2201.08772) and
[CAV 2023 SAYNT](https://arxiv.org/pdf/2305.14149) papers; the local lanes-100
instance is labelled `Lanes+`.

## Use the plots in a paper

Create a `pomdp-plots/` folder in the paper project and copy these four files
from `data/plots/` into it:

- `aggregate-plots.tex`
- `paper-figure.tex`
- `plot-series.csv`
- `plot-curves.csv`

Load the plotting commands and data in the preamble:

```tex
\input{pomdp-plots/aggregate-plots.tex}
\StormPOMDPLoadAggregateData{pomdp-plots}
```

Insert the figure in the document body:

```tex
\input{pomdp-plots/paper-figure.tex}
```

Compile twice for the shared legend and use
`Fig.~\ref{fig:pomdp-benchmarks}` to reference the figure. PGFPlots draws it
from the CSV files; the paper project does not need Python, shell escape,
or pre-rendered images. Edit the caption and label in `paper-figure.tex` as
needed. To preserve caption edits across postprocessing, also update
`save_paper_figure()` in `scripts/plots.py`.

To extend an existing `plots.tex`, append `aggregate-plots.tex` to it and copy
the two CSV files into `\resultsdir/pomdp/` (or `data/pomdp/` if `\resultsdir`
is undefined). Call `\pomdpplots` inside a figure environment. Override the
CSV location by redefining `\pomdpresultsdir`.
For custom arrangements, use `\pomdpruntimeplot`, `\pomdpundergapplot`,
`\pomdpovergapplot`, and `\pomdplegend`.

## Script layout

The `scripts/` directory contains:

- `run.py`, `commands.py`, `input.py`, `executing.py`: invocation creation,
  selection, execution, and log writing.
- `benchmarkset.py`, `benchmarks.py`: benchmark definitions and file checks.
- `storm.py`, `tools.py`: Storm configurations and command construction.
- `postprocess.py`: log parsing and the postprocessing command.
- `html_results.py`, `html_assets/`: offline HTML export.
- `plots.py`, `latex/pomdp-aggregate-plots.tex`: plot data, figure source,
  and rendering.
