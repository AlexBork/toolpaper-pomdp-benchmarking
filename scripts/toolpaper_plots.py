"""Compact POMDP tool-paper figures from the audited exports (stdlib only)."""

import argparse
import csv
import json
import math
import re
import shutil
import statistics
import subprocess
from collections import Counter
from pathlib import Path


THRESHOLDS = (10_000, 1_000_000, 10_000_000)
EXAMPLES = (
    ("drone_drone_prbmax_N6-R3", "Drone N6--R3"),
    ("network3_network3_rewmin_T8-K20", "Network3"),
    ("samplerocks_samplerocks_rewmin_N12", "Samplerocks N12"),
)
FIGURES = ("main-figure", "bound-improvement-figure", "heatmap-figure", "preview")
TEX_BUILD_SUFFIXES = (".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk", ".synctex.gz")
EXPLORATION_COUNTS = re.compile(
    r"Belief exploration (completed|stopped early): (\d+) beliefs discovered, (\d+) beliefs explored\."
)


def read_tsv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerows(rows)


def write_csv(path, columns, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def document(body, *, multipage=False):
    options = "multi=plotpage,border=5pt" if multipage else "border=5pt"
    return (rf"\documentclass[{options}]{{standalone}}" + "\n"
            + (r"\newenvironment{plotpage}{}{}" + "\n" if multipage else "")
            + r"\input{pomdp-aggregate-plots.tex}" + "\n"
            + r"\StormPOMDPLoadAggregateData{.}" + "\n"
            + r"\begin{document}" + "\n" + body + "\n"
            + r"\end{document}" + "\n")


def remove_build_files(output_dir, name):
    for suffix in TEX_BUILD_SUFFIXES:
        (Path(output_dir) / (name + suffix)).unlink(missing_ok=True)


def remove_obsolete_outputs(output_dir):
    """Remove only the standalone panel exports superseded by the main figure."""
    for name in ("aggregate-figure", "tradeoff-figure"):
        for suffix in (".tex", ".pdf", ".png"):
            (Path(output_dir) / (name + suffix)).unlink(missing_ok=True)
        remove_build_files(output_dir, name)


def tex_escape(text):
    return text.replace("_", r"\_").replace("%", r"\%")


def exploration_counts(run, data_dir):
    """Keep explored, discovered, and constructed-state counts distinct."""
    source = Path(run["log"])
    candidates = (source, data_dir.parent / source)
    path = next((path for path in candidates if path.is_file()), None)
    if path is None:
        raise ValueError(f"Source log required for actual exploration counts: {source}")
    matches = EXPLORATION_COUNTS.findall(path.read_text())
    if len(matches) != 1:
        raise ValueError(f"Expected one exploration summary in {path}; found {len(matches)}")
    outcome, discovered, explored = matches[0]
    discovered, explored = int(discovered), int(explored)
    if not 0 < explored <= discovered:
        raise ValueError(f"Invalid exploration counts in {path}")
    return explored, discovered, int(outcome == "completed")


def save_figures(data_dir, output_dir=None):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir or data_dir / "general-plots" / "pomdp-tool-paper")
    output_dir.mkdir(parents=True, exist_ok=True)
    observations = read_tsv(data_dir / "cutoff-threshold-observations.csv")
    references = read_tsv(data_dir / "cutoff-threshold-references.csv")
    runtime_rows = read_tsv(data_dir / "runtime-runs.csv")
    metadata = json.loads((data_dir / "benchmark-data.json").read_text())
    execution = json.loads((data_dir / "execution-data.json").read_text())["storm"]
    refs = {row["instance"]: row for row in references
            if row["reference"] == "best-discretisation"}
    run_status = {(row["instance"], row["configuration"]): row["status"]
                  for row in runtime_rows}
    instances = list(dict.fromkeys(row["instance"] for row in observations))
    thresholds = sorted({int(row["threshold"]) for row in observations})
    seen = set()
    for row in observations:
        key = (row["instance"], row["configuration"])
        if key in seen:
            raise ValueError(f"Duplicate observation: {key}")
        seen.add(key)
        row["status"] = run_status[key]  # Distinguish SIGKILL from other failures.
        row["threshold"] = int(row["threshold"])
        row["time"] = float(row["wallclock_seconds"])
        row["gap"] = None
        row["lower"] = row["upper"] = None
        row["explored"] = row["discovered"] = row["complete"] = None
        if row["status"] != "successful":
            continue
        cutoff = float(row["bound"])
        reference = float(refs[row["instance"]]["bound"])
        if not math.isfinite(cutoff) or not math.isfinite(reference):
            raise ValueError(f"Non-finite bound: {key}")
        lower, upper = ((reference, cutoff)
                        if metadata[row["instance"]]["property-dir"] == "min"
                        else (cutoff, reference))
        scale = max(abs(lower), abs(upper))
        if lower > upper + 1e-7 * max(scale, 1):
            raise ValueError(f"Inconsistent bound interval: {key}")
        row["lower"], row["upper"] = lower, upper
        row["gap"] = max(0, upper - lower) / scale if scale else 0
        if row["time"] <= 0:
            raise ValueError(f"Non-positive successful runtime: {key}")
        row["explored"], row["discovered"], row["complete"] = exploration_counts(
            execution[row["configuration"]][row["instance"]], data_dir)
    expected = {(inst, tau) for inst in instances for tau in thresholds}
    if {(row["instance"], row["threshold"]) for row in observations} != expected:
        raise ValueError("Incomplete threshold grid; heatmap requires all observations")

    initial, deepest, progress_axes = {}, {}, {}
    for inst in instances:
        successful = [row for row in observations
                      if row["instance"] == inst and row["status"] == "successful"]
        initial[inst] = min(successful, key=lambda row: row["threshold"])
        deepest[inst] = max(successful, key=lambda row: (row["explored"], -row["threshold"]))
        values = [float(row["bound"]) for row in successful]
        low, high = min(values), max(values)
        if metadata[inst]["property"] == "prb":
            progress_axes[inst] = (max(0, math.floor(low * 10) / 10),
                                   min(1.02, math.ceil(high * 10) / 10 + .02))
        else:
            padding = .08 * (high - low) if high > low else .05 * max(abs(high), 1)
            progress_axes[inst] = (low - padding, high + padding)
    reaches_million = sum(row["explored"] >= 1_000_000 for row in deepest.values())
    reaches_ten_million = sum(row["explored"] >= 10_000_000 for row in deepest.values())
    largest_instance = max(deepest, key=lambda inst: deepest[inst]["explored"])
    exploration_summary = [[
        "instance", "configuration", "explored_beliefs", "discovered_beliefs",
        "constructed_states", "exploration_complete", "wallclock_seconds",
        "objective", "direction", "initial_bound", "final_bound", "initial_interval_closed_percent",
    ]]
    for inst in instances:
        row = deepest[inst]
        first = float(initial[inst]["bound"])
        last = float(row["bound"])
        denominator = abs(first - float(refs[inst]["bound"]))
        closed = 100 * (1 - abs(last - float(refs[inst]["bound"])) / denominator) if denominator else "nan"
        exploration_summary.append([
            inst, row["configuration"], row["explored"], row["discovered"], row["states"],
            row["complete"], row["time"], metadata[inst]["property"], metadata[inst]["property-dir"],
            first, last, closed,
        ])
    write_tsv(output_dir / "exploration-summary.tsv", exploration_summary)

    audit = [["instance", "configuration", "threshold", "cutoff_seconds", "status",
              "lower_bound", "upper_bound", "relative_gap", "reference_configuration",
              "reference_seconds"]]
    for row in observations:
        ref = refs[row["instance"]]
        audit.append([row["instance"], row["configuration"], row["threshold"], row["time"],
                      row["status"], row["lower"], row["upper"], row["gap"],
                      ref["configuration"], ref["wallclock_seconds"]])
    write_tsv(output_dir / "gap-observations.tsv", audit)

    costs = [["instance", "selected_configuration", "selected_reference_seconds",
              "both_reference_runs_seconds"]]
    for inst in instances:
        ref = refs[inst]
        both = sum(float(row["wallclock_seconds"]) for row in runtime_rows
                   if row["instance"] == inst and row["family"] == "discretisation")
        costs.append([inst, ref["configuration"], ref["wallclock_seconds"], both])
    write_tsv(output_dir / "reference-costs.tsv", costs)

    summary = [["threshold", "successful", "width_le_1_percent", "width_le_5_percent",
                "width_le_10_percent", "median_cutoff_seconds"]]
    coverage_rows = []
    for tau in THRESHOLDS:
        runs = [row for row in observations if row["threshold"] == tau
                and row["status"] == "successful"]
        if len(runs) != len(instances):
            raise ValueError(f"Aggregate threshold {tau} must succeed on every instance")
        gaps = Counter(row["gap"] * 100 for row in runs)
        cumulative, coords = 0, [(0.1, 0)]
        for gap, count in sorted(gaps.items()):
            if gap < 0.1:
                raise ValueError("Aggregate log axis must be extended below 0.1 percent")
            cumulative += count
            coords.append((gap, cumulative))
        coords.append((100, cumulative))
        median = statistics.median(row["time"] for row in runs)
        summary.append([tau, len(runs), *[sum(row["gap"] <= eps for row in runs)
                        for eps in (.01, .05, .1)], median])
        exponent = int(math.log10(tau))
        coverage_rows.extend(dict(
            threshold=tau, threshold_exponent=exponent,
            gap_percent=gap, instances=count, total_instances=len(instances),
            median_cutoff_seconds=median,
        ) for gap, count in coords)
    write_tsv(output_dir / "aggregate-summary.tsv", summary)
    write_csv(output_dir / "coverage-plot-data.csv", [
        "threshold", "threshold_exponent", "gap_percent", "instances",
        "total_instances", "median_cutoff_seconds",
    ], coverage_rows)

    example_info = {inst: (i, label) for i, (inst, label) in enumerate(EXAMPLES)}
    missing_examples = set(example_info) - set(instances)
    if missing_examples:
        raise ValueError(f"Missing representative instances: {sorted(missing_examples)}")
    index = {(row["instance"], row["threshold"]): row for row in observations}
    outcome_counts = Counter(row["status"] for row in observations)
    status_codes = {"successful": 0, "killed": 1, "timeout": 2, "memout": 3, "failed": 4, "missing": 5}
    gap_rows = []
    for iy, inst in enumerate(instances):
        model = metadata[inst]
        label = tex_escape(model["name"] + (" / " + model["par"] if model["par"] else ""))
        representative_index, curve_label = example_info.get(inst, (-1, label))
        capacity_label = {"network2": "Network2", "network-priorities2": "Priorities2",
                          "refuel": "Refuel N6"}.get(model["name"], label)
        reference_bound = float(refs[inst]["bound"])
        initial_interval = abs(float(initial[inst]["bound"]) - reference_bound)
        for ix, tau in enumerate(thresholds):
            row = index[inst, tau]
            success = row["status"] == "successful"
            gap_percent = row["gap"] * 100 if success else "nan"
            tick = tau in (10_000, 100_000, 1_000_000, 10_000_000, max(thresholds))
            threshold_label = (rf"$10^{{{int(math.log10(tau))}}}$"
                               if tau in (10_000, 100_000, 1_000_000, 10_000_000)
                               else rf"${tau/1_000_000:g}\cdot10^{{6}}$") if tick else "none"
            gap_rows.append(dict(
                instance=inst, instance_index=iy, instance_label=label,
                curve_label=curve_label, representative_index=representative_index,
                threshold=tau, threshold_index=ix, threshold_tick=int(tick),
                threshold_label=threshold_label, cutoff_seconds=row["time"] if success else "nan",
                recorded_seconds=row["time"], gap_percent=gap_percent,
                log_gap_percent=math.log10(max(.1, gap_percent)) if success else "nan",
                status=row["status"], status_code=status_codes[row["status"]],
                annotation_exponent=int(math.log10(tau)) if tau in THRESHOLDS else 0,
                total_instances=len(instances), total_thresholds=len(thresholds),
                explored_beliefs=row["explored"] if success else "nan",
                discovered_beliefs=row["discovered"] if success else "nan",
                constructed_states=row["states"] if success else "nan",
                exploration_complete=row["complete"] if success else -1,
                cutoff_bound=float(row["bound"]) if success else "nan",
                property_type=model["property"], property_direction=model["property-dir"],
                capacity_partial_seconds=row["time"] if row is deepest[inst] and not row["complete"] else "nan",
                capacity_complete_seconds=row["time"] if row is deepest[inst] and row["complete"] else "nan",
                capacity_label=capacity_label if row is deepest[inst] and (row["complete"] or inst == largest_instance) else "none",
                reaches_million=reaches_million, reaches_ten_million=reaches_ten_million,
                interval_closed_percent=100 * (1 - abs(float(row["bound"]) - reference_bound) / initial_interval)
                    if success and initial_interval else "nan",
                progress_label=(f"{float(row['bound']):.3f} ({row['time']:.0f} s)" if row is deepest[inst]
                                else f"{float(row['bound']):.3f}" if row is initial[inst] else "none"),
                progress_ymin=progress_axes[inst][0], progress_ymax=progress_axes[inst][1],
                progress_ylabel=("Probability" if model["property"] == "prb" else "Reward")
                    + (" upper bound" if model["property-dir"] == "min" else " lower bound"),
                configuration=row["configuration"],
            ))
    write_csv(output_dir / "gap-plot-data.csv", [
        "instance", "instance_index", "instance_label", "curve_label", "representative_index",
        "threshold", "threshold_index", "threshold_tick", "threshold_label", "cutoff_seconds",
        "recorded_seconds", "gap_percent", "log_gap_percent", "status", "status_code",
        "annotation_exponent", "total_instances", "total_thresholds",
        "explored_beliefs", "discovered_beliefs", "constructed_states", "exploration_complete",
        "cutoff_bound", "property_type", "property_direction", "capacity_partial_seconds",
        "capacity_complete_seconds", "capacity_label", "reaches_million", "reaches_ten_million",
        "interval_closed_percent", "progress_label",
        "progress_ymin", "progress_ymax", "progress_ylabel",
        "configuration",
    ], gap_rows)
    shutil.copyfile(Path(__file__).parent / "latex" / "pomdp-aggregate-plots.tex",
                    output_dir / "pomdp-aggregate-plots.tex")
    for filename, kind in (("aggregate", "coverage"), ("tradeoff", "tradeoff"), ("heatmap", "heatmap"),
                           ("exploration", "exploration"), ("bound-improvement", "improvement")):
        (output_dir / (filename + ".tex")).write_text(
            "% Load pomdp-aggregate-plots.tex and the two CSV files in the preamble first.\n"
            + rf"\StormPOMDPAggregatePlot{{{kind}}}" + "\n")
    main_body = (
        r"\input{exploration.tex}\hspace{2mm}"
        + rf"\StormPOMDPBoundProgressPlot[title={{(b) Drone N6--R3}}]{{{EXAMPLES[0][0]}}}"
        + r"\hspace{2mm}"
        + rf"\StormPOMDPBoundProgressPlot[title={{(c) Network3}}]{{{EXAMPLES[1][0]}}}"
    )
    improvement_body = (
        r"\input{bound-improvement.tex}\hspace{4mm}"
        + rf"\StormPOMDPBoundProgressPlot[width=8.1cm,height=6.4cm,title={{(b) Samplerocks N12}}]{{{EXAMPLES[2][0]}}}"
    )
    (output_dir / "main-figure.tex").write_text(document(main_body))
    (output_dir / "bound-improvement-figure.tex").write_text(document(improvement_body))
    (output_dir / "heatmap-figure.tex").write_text(document(
        r"\begin{tabular}{c}\input{heatmap.tex}\\[-1mm]"
        + r"\small Grey $\times$: non-timeout SIGKILL; red T: timeout."
        + r"\end{tabular}"))
    (output_dir / "preview.tex").write_text(document(
        r"\begin{plotpage}" + main_body + r"\end{plotpage}" + "\n"
        + r"\begin{plotpage}" + improvement_body + r"\end{plotpage}" + "\n"
        + r"\begin{plotpage}\begin{tabular}{c}\input{heatmap.tex}\\[-1mm]"
        + r"\small Grey $\times$: non-timeout SIGKILL; red T: timeout."
        + r"\end{tabular}\end{plotpage}", multipage=True))

    caption = (
        "Deep belief exploration and tighter POMDP bounds. (a) Deepest successful cut-off "
        "run for each of the 19 instances, selected by the number of beliefs actually "
        "explored; ties use the smallest configured cut-off. Circles indicate reaching "
        "the cut-off, and stars indicate complete belief exploration. Runtime includes "
        "exploration, construction, and solving. (b,c) Increasing exploration improves "
        "the probability lower bound for Drone N6-R3 and the reward upper bound for "
        "Network3. Markers are separate runs, connected in increasing cut-off order; "
        "endpoint labels show rounded bounds and the deepest run's runtime. Explored "
        "counts come from the logs and exclude unexpanded frontier beliefs."
    )
    readme = f"""# POMDP figures for the Storm tool paper

`preview.pdf`: combined three-page preview: main figure, bound-improvement alternatives, heatmap.
`main-figure.pdf` / `.png`: exploration capacity and raw-bound progress for Drone N6-R3 and Network3.
`bound-improvement-figure.pdf` / `.png`: initial interval closed versus explored beliefs,
plus raw-bound progress for Samplerocks N12.
`heatmap-figure.pdf` / `.png`: appendix overview of all {len(instances)} instances and {len(thresholds)} thresholds.
`coverage-plot-data.csv`: comma-separated coverage curves and median runtimes.
`gap-plot-data.csv`: comma-separated gap/runtime observations for all instances,
including heatmap coordinates, labels, outcomes, and default-series selections.
`pomdp-aggregate-plots.tex`: reusable CSV-backed PGFPlots commands.
`exploration-summary.tsv`: deepest successful run per instance, actual counts,
completion, runtime, and initial/final bounds.
`exploration.tex`, `bound-improvement.tex`, `heatmap.tex`: small command wrappers.
`aggregate.tex` and `tradeoff.tex`: earlier coverage/runtime plot wrappers retained for reuse.

## Using the commands in a paper

Copy `pomdp-aggregate-plots.tex`, `coverage-plot-data.csv`, and
`gap-plot-data.csv` into one directory in the paper project. Load the TeX
file and data directory in the preamble, then select a plot by identifier:

```tex
% Preamble (change the paths to match the paper project):
\\input{{data/general-plots/pomdp-tool-paper/pomdp-aggregate-plots.tex}}
\\StormPOMDPLoadAggregateData{{data/general-plots/pomdp-tool-paper}}

% Document body:
\\StormPOMDPAggregatePlot{{exploration}}
\\StormPOMDPBoundProgressPlot{{drone_drone_prbmax_N6-R3}}
\\StormPOMDPBoundProgressPlot{{network3_network3_rewmin_T8-K20}}
\\StormPOMDPAggregatePlot{{improvement}}
\\StormPOMDPAggregatePlot[width=15cm,height=9cm]{{heatmap}}
```

All plot commands accept optional PGFPlots axis settings. The defaults read
representative instance identifiers from the CSV files. Earlier `coverage`
and `tradeoff` identifiers remain available.
To choose a subset or a different ordering, pass a comma-separated list:

```tex
\\StormPOMDPCoveragePlot[width=7cm]{{10000,10000000}}
\\StormPOMDPBoundImprovementPlot[width=7cm]{{drone_drone_prbmax_N6-R3,network3_network3_rewmin_T8-K20}}
```

Coverage thresholds must appear in `coverage-plot-data.csv`; trade-off
identifiers can be any instance in `gap-plot-data.csv`. Unknown identifiers
produce a LaTeX error. Colours and markers follow the requested series order.
The first selected legacy trade-off curve receives threshold annotations. Heatmap
rows and columns follow the order in the generated CSV. Its symbols mean
SIGKILL (cross), timeout (T), memory-out (M), or other unavailable result (?).

### CSV fields

`coverage-plot-data.csv` stores one step-coordinate row per threshold:
`threshold`, `gap_percent`, and `instances` identify the plotted curves,
with `median_cutoff_seconds` and `total_instances` supplying the legends
and denominator. `threshold_exponent` supplies the power-of-ten legend label.

`gap-plot-data.csv` stores every tested instance/threshold pair. Successful
rows supply `cutoff_seconds`, `gap_percent`, and `log_gap_percent`; failed
rows keep their actual time in `recorded_seconds` and use `nan` for plotting.
`instance_index` and `threshold_index` locate heatmap cells, while
`instance_label`, `threshold_label`, and `threshold_tick` supply axis labels.
`status` and `status_code` identify outcomes. `representative_index` selects
the default trade-off curves and their order (negative means not selected),
and `curve_label` supplies legend text. `annotation_exponent` marks the
labelled thresholds; `total_instances` and `total_thresholds` supply dimensions.

Actual counts are in `explored_beliefs` and `discovered_beliefs`, parsed from
the successful source logs; `constructed_states` is the belief-MDP size.
`exploration_complete` distinguishes completed exploration from reaching a
cut-off. `capacity_partial_seconds` and `capacity_complete_seconds` contain
one selected successful run per instance; ties in explored count use the
smallest configured cut-off. All 19 instances reach one million explored
beliefs, and 10 reach ten million. The largest successful run explores
38,720,258 beliefs in 263.35 seconds.

`cutoff_bound` supplies raw bounds. `interval_closed_percent` is
100 * (1 - abs(b_tau-r)/abs(b_initial-r)), where b_initial is the bound at
the smallest cut-off and r is the fixed selected discretisation reference.
It is undefined (`nan`) if the initial interval has zero width. It measures
progress relative to that reference interval, rather than error against a
known optimum. The raw-bound panels use linear y-axes with visible numeric
limits; endpoint labels round bounds to three decimals and times to seconds.

## Definition and timing

For each successful cut-off run, pair its bound with the selected
best-discretisation reference from `cutoff-threshold-references.csv`.
For minimisation, L = discretisation and U = cut-off; for maximisation,
L = cut-off and U = discretisation. Relative gap is (U-L)/max(|L|,|U|),
with gap zero when both bounds are zero. Figures show this as a percentage.
This is interval width, not measured error against a known optimum.

The reference is selected by bound quality from resolutions 4 and 5, with
runtime breaking ties, as in the existing postprocessor. It is fixed for
each instance throughout the sweep. Reference cost is excluded from all
runtime axes. `reference-costs.tsv` records both the selected run's time
and the sum of both reference runs, to make selection costs explicit.
For Drone N6-R3, the selected reference takes
{float(refs[EXAMPLES[0][0]]['wallclock_seconds']):.2f} seconds.
The curves connect independent runs in threshold order; they are not traces
of one anytime execution and no cumulative sweep timing is implied.

The capacity plot uses the deepest successful run for every instance.
Failed runs supply neither explored counts nor valid bounds for these curves.
The legacy coverage plot uses thresholds with successful runs on all instances.
The heatmap includes every outcome: {outcome_counts['successful']} successful,
{outcome_counts['killed']} non-timeout SIGKILL exits, {outcome_counts['timeout']} timeouts.
SIGKILL does not establish a memory-out. Failed runs have no gap value.
Heatmap columns are equally spaced tested configurations, rather than a
continuous logarithmic axis; colour encodes log10(gap in percent), floored
at 0.1 percent for display. No best-so-far envelope or smoothing is applied.

## Suggested main-figure caption

{caption}

## Suggested appendix caption

Relative bound gap for every benchmark and tested cut-off. Successful cells
use the same fixed discretisation reference as the main figure. Colour
encodes gap on a logarithmic scale; smaller is tighter. Grey crosses mark
non-timeout SIGKILL exits, and red T cells mark timeouts. Each tested
threshold occupies one equal-width column.

## Regeneration

From the repository root:

```sh
python3 scripts/toolpaper_plots.py --compile
```

This reads the current audited exports in `data/`. Use `--data-dir` and
`--output-dir` for other exports/destinations. PDF compilation requires
LuaLaTeX; PNG previews require `pdftoppm`. Generation itself uses only the
Python standard library. Source logs referenced by `execution-data.json`
must be available to extract actual exploration counts. Audit values are in
`gap-observations.tsv`, `exploration-summary.tsv`, and `aggregate-summary.tsv`.
The combined preview reads the CSV files directly and can be compiled on its
own. Successful builds remove temporary LaTeX files; failures keep their logs.
Individual panel PDFs are superseded by the main figure and reusable commands.
"""
    (output_dir / "README.md").write_text(readme)
    remove_obsolete_outputs(output_dir)
    return output_dir


def compile_figures(output_dir):
    for name in FIGURES:
        subprocess.run(["lualatex", "--interaction=nonstopmode", "--halt-on-error",
                        name + ".tex"], cwd=output_dir, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if name != "preview":
            subprocess.run(["pdftoppm", "-singlefile", "-r", "160", "-png",
                            name + ".pdf", name], cwd=output_dir, check=True)
        remove_build_files(output_dir, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--compile", action="store_true", help="Compile PDFs and render PNG previews")
    args = parser.parse_args()
    output_dir = save_figures(args.data_dir, args.output_dir)
    if args.compile:
        try:
            compile_figures(output_dir)
        except subprocess.CalledProcessError as error:
            if error.stdout:
                print(error.stdout.decode(errors="replace"))
            raise
    print(f"Generated POMDP tool-paper figures in {output_dir}")


if __name__ == "__main__":
    main()
