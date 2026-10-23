# Storm-POMDP Benchmarking

The current experiment suite contains **19 instances and 34 configurations
(646 runs)**: 32 explicit cut-offs from 10,000 to 50,000,000 and static
discretisation at resolutions 4 and 5.

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

Runs execute sequentially. Ctrl+C stops the current process group and exits
the runner. Execution errors produce a nonzero exit code after the remaining
invocations have been attempted. To run just one invocation, append its zero-based
index, for example `python3 scripts/run.py inv-toolpaper.json 0`. The runner
writes one self-contained `.log` per invocation into the selected log directory.
Each log includes the command, benchmark, configuration, time limit, runtime,
and return code; no per-run JSON file is needed for postprocessing.
The invocation JSON file is still used to schedule runs. Existing invocation
files retain their stored commands and time limits.

The timeout sends SIGKILL to the entire benchmark process group immediately,
without a termination grace period. The full suite's worst-case runtime at
600 seconds per run is 107 hours 40 minutes, plus overhead.
Runtime and failures depend on the machine. Record
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

One command parses the logs and generates the results and aggregate plots:

```sh
python3 scripts/postprocess.py logs-paper
```

This regenerates the paper results from the shipped logs without running Storm.
To process new runs, replace `logs-paper` with your experiment's log directory,
for example `python3 scripts/postprocess.py logs-reviewer`.
Every run writes to the same `data/` folder: HTML pages, CSV data,
plot sources, PDF, and PNG. Matching output files are overwritten.
Both the shipped logs and new runner logs are self-contained.
Legacy per-run JSON files with their logs are also accepted.
The Python code uses the standard library; plot rendering requires LuaLaTeX
with PGFPlots and the `llncs` class, and `pdftoppm`.
There are no output-selection or reference-selection switches.

The file guide and aggregate plots use nine files. The HTML export additionally contains its index, two
assets, and one log page per measured run:

- `html/index.html`: offline results table with sorting, filtering,
  configuration toggles, and bound/runtime views. Click a run to open its
  individual invocation, metadata, and log page in `html/logs/`. Share the
  entire `html/` folder, including its CSS and JavaScript assets.
- `README.md`: a short guide to the generated files.
- `plots/plot-data.csv`: the single dataset for all aggregate panels, including
  actual exploration counts, raw bounds, both selected references, and their relative gaps.
- `plots/plot-series.csv` and `plots/plot-curves.csv`: compact tables used directly
  by PGFPlots in the paper; one row per instance and per threshold, respectively.
- `plots/aggregate-plots.tex`: reusable PGFPlots commands.
- `plots/paper-figure.tex`: the figure environment, caption, and label for the paper.
- `plots/runtime-comparison.tex`, `.pdf`, and `.png`: the combined three-panel
  comparison, with one shared instance legend.

The panels show runtime versus configured size limit, gap to the best
under-approximation, and gap to the best over-approximation. They sit side by side
in a 12.2 cm wide LNCS figure with 2.1 cm tall axes and a shared legend
in a centered thin frame fitted to its contents. Entries align in five columns,
automatically falling back to four or three if needed to fit the available width.
All lettering is 6 pt;
the figure is drawn at its final print size without scaling.
Each included instance
appears on the same axes with a consistent colour and marker. Colours use the
Tol vibrant palette (`T-Q-V1`–`T-Q-V6`) from
[colorblind](https://ctan.org/pkg/colorblind); the 19 instances have distinct
colour/marker combinations. Existing palette colours are reused when available;
standalone previews use the same RGB values. Each point is an
independent run. All three panels use the configured size limit on the x-axis and
reserve dedicated categorical lines
above the numeric range: separate solid `TO` and `MO` lines aligned at the same
heights across all three panels, for timeouts and
memory-outs, including killed runs treated as MO, and `Failed` for other failures
when present. Failure points
use the same colour and marker as their benchmark's successful points.
These line positions denote outcomes; measured runtimes remain in the CSV.
Failed runs supply no numeric bound or explored-belief point.

Legend names follow Tables 1–2 of
[TACAS 2022](https://arxiv.org/pdf/2201.08772) and Tables 2/5 of the
[CAV 2023 SAYNT paper](https://arxiv.org/pdf/2305.14149): for example,
`Grid-4-0.1`, `Grid-av-4-0.1`, `Rocks-12`, `Drone-4-2`, `Netw-2-8-20`,
`Netw-p-2-8-20`, `Maze2-0.1`, and `Refuel-06`. Parameter letters are omitted;
their order follows the papers. Added drone and maze variants use the same
notation. The local `lanes-100` model is `Lanes+` (see the SAYNT paper's
Appendix C); `Grid-large-30-5` retains its explicit artifact dimensions.

Probability and reward bounds have different units. Each bound panel therefore
shows `100 * abs(bound-best) / max(abs(bound), abs(best))`, with zero gap when
both values are zero. The first reference is the best successful under-approximation
observed for that instance across the cut-off sweep: the highest lower bound for
maximisation or the lowest upper bound for minimisation. Runtime breaks exact
numerical ties. Smaller deviations are better; zero means matching the best
observed bound. This measures progress relative to the observed best value,
rather than a certified interval around the optimum. The selected configuration,
bound, and runtime are recorded in the CSV; reference runtime is excluded from
each plotted run's time.

The second reference is the tightest successful over-approximation from
belief discretisation at resolutions 4 and 5. Both comparisons are always generated.
For maximisation this selects the smallest upper bound; for minimisation it
selects the largest lower bound. The same formula then measures relative
interval width between the cut-off and over-approximation bounds.

Threshold and runtime axes are logarithmic. Both gap axes are linear so matching
best bounds appear at zero. Partial
experiments remain usable; absent runs and unavailable references are recorded
as missing data. Runtime totals count measured configurations once. A
non-timeout SIGKILL retains source status `killed` in audits and is classified
as `memout` in the plot dataset's `plot_status` column.
All CSV files use commas. Source logs are read without modification.

To extend an existing paper's `plots.tex`, append the contents of the generated
`data/plots/aggregate-plots.tex` to it. Copy `plot-series.csv` and `plot-curves.csv`
from `data/plots` into the paper's `data/pomdp/` folder. The new commands follow
the existing `\resultsdir` convention and load the CSVs when called:

```tex
% Preamble: keep the paper's existing \input{plots.tex}.
% Document body:
\begin{figure}[t]
  \centering
  \pomdpplots
  \caption{Runtime and bound quality across all benchmark instances.}
  \label{fig:pomdp-benchmarks}
\end{figure}
```

`\pomdpplots` draws the complete three-panel figure and shared legend.
For a custom arrangement, use `\pomdpruntimeplot`, `\pomdpundergapplot`,
`\pomdpovergapplot`, and `\pomdplegend`. Individual panels accept optional
PGFPlots axis settings. The CSV location defaults to `\resultsdir/pomdp` and
can be changed by redefining `\pomdpresultsdir`. The extension preserves
existing plot commands and applies its compatibility settings only to POMDP axes.
All added colours, styles, and private helpers use POMDP-specific names. The
existing `\resultsdir` is read without being redefined; no existing plot definitions
need editing.

Alternatively, to use a separate plotting file in Overleaf, create a
`pomdp-plots/` folder in the paper project and upload `aggregate-plots.tex`,
`paper-figure.tex`, `plot-series.csv`, and `plot-curves.csv` from `data/plots/`
into that folder.

Load the plotting commands and CSV data in the paper's preamble:

```tex
\input{pomdp-plots/aggregate-plots.tex}
\StormPOMDPLoadAggregateData{pomdp-plots}
```

Insert the figure at the desired location in the document body:

```tex
\input{pomdp-plots/paper-figure.tex}
```

Compile twice for the shared legend and reference the figure with
`Fig.~\ref{fig:pomdp-benchmarks}`. PGFPlots draws all three panels directly from
the two CSV files; Python, shell escape, and pre-rendered PDFs are not needed
in the paper project. Edit the caption and label in `paper-figure.tex` as needed.
At LNCS text width the figure retains its intended 6 pt lettering and compact
side-by-side layout.

`plot-curves.csv` stores one threshold per row and three columns per instance:
`runtime_N`, `under_gap_N`, and `over_gap_N`, where `N` is the instance index in
`plot-series.csv`. Successful runs contain their runtime or gap; failed runs
use their categorical line position, and missing values use `nan`.
`plot-series.csv` stores instance names, colour/marker indices, axis limits,
and TO/MO positions. The full per-run values and statuses remain available in
`plot-data.csv` for auditing.

Individual panels remain available as `\StormPOMDPAllRuntimeThresholdPlot`,
`\StormPOMDPAllUnderBoundThresholdPlot`, and `\StormPOMDPAllOverBoundThresholdPlot`.

The implementation is split by responsibility: `postprocess.py` handles parsing
and the command; `plots.py` generates the aggregate comparison;
`html_results.py` builds the results table and linked log pages.
Generated outputs are ignored by Git. Successful plot builds remove temporary
LaTeX files; failed builds retain their logs for diagnosis.
