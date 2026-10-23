"""Build runtime and both bound-quality comparisons, including CSV paper exports."""

import csv
import math
from pathlib import Path
import shutil
import subprocess

INSTANCE_NAMES = {
    "grid": "Grid-4",
    "grid-avoid": "Grid-av-4",
    "samplerocks": "Rocks",
    "drone": "Drone",
    "lanes-100": "Lanes+",
    "grid-large-30-5": "Grid-large-30-5",
    "network2": "Netw-2",
    "network3": "Netw-3",
    "network-priorities2": "Netw-p-2",
    "network-priorities3": "Netw-p-3",
    "maze2": "Maze2",
    "refuel": "Refuel",
}
FAILURES = ("timeout", "memout", "failed")
FAILURE_GROUPS = {"memout": {"memout"}, "timeout": {"timeout"}, "failed": {"failed"}}


def instance_label(inst):
    """Use TACAS 2022 / CAV 2023 model names and positional parameters."""
    name = INSTANCE_NAMES.get(inst["name"], inst["name"])
    parameters = [
        f"{value:02d}" if inst["name"] == "refuel" else str(value)
        for value in inst["model"].get("open-parameters", {}).values()
    ]
    return "-".join([name, *parameters]).replace("_", r"\_").replace("%", r"\%")


def relative_gap(bound, reference):
    """Relative deviation from the best observed bound, including zero values."""
    scale = max(abs(bound), abs(reference))
    return 100 * abs(bound - reference) / scale if scale else 0


def approximation_score(p, run, inst, reference_kind):
    """Select the tightest bound on the chosen side, then the fastest exact tie."""
    relation, bound = p.parse_result_value(run["result"])
    method = "cut" if reference_kind == "under" else "discr"
    if relation not in ("=", p.expected_bound_relation(method, inst)):
        raise ValueError(
            f"Unexpected {reference_kind}-approximation bound in {run['id']}: {run['result']}"
        )
    seconds = float(run["wallclock-time"])
    if not math.isfinite(bound) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"Invalid bound or runtime in {run['id']}")
    maximise = (inst["property"]["dir"] == "max") == (reference_kind == "under")
    return bound if maximise else -bound, -seconds


def add_failure_lines(rows):
    """Put categorical failure markers above each threshold panel's numeric range."""
    statuses = {row["plot_status"] for row in rows}
    groups = [name for name, outcomes in FAILURE_GROUPS.items() if outcomes & statuses]
    times = [
        row["cutoff_seconds"] for row in rows if math.isfinite(row["cutoff_seconds"])
    ]
    minimum, maximum = min(times, default=1), max(times, default=1)
    lower_power = math.ceil(math.log10(minimum))
    upper_power = max(lower_power + 1, math.ceil(math.log10(maximum)))
    runtime_end = 10**upper_power
    gaps = [row["gap_percent"] for row in rows if math.isfinite(row["gap_percent"])]
    maximum_gap = max(gaps, default=0)
    target_step = max(maximum_gap, 1) / 4
    decade = 10 ** math.floor(math.log10(target_step))
    gap_step = next(
        multiplier * decade
        for multiplier in (1, 2, 5, 10)
        if multiplier * decade >= target_step
    )
    gap_end = max(gap_step, math.ceil(maximum_gap / gap_step) * gap_step)
    runtime_min = minimum * 0.8
    gap_min = -gap_end * 0.03
    levels = {}
    runtime_max, gap_max = runtime_end * 1.1, gap_end * 1.06
    if groups:
        # Reserve the same fractions of axis height for outcomes in every panel.
        # Interpolate runtime in log space and gaps in linear space.
        numeric_fraction = 0.94 - 0.12 * len(groups)
        runtime_span = math.log10(runtime_end / runtime_min) / numeric_fraction
        gap_span = (gap_end - gap_min) / numeric_fraction
        runtime_max = runtime_min * 10**runtime_span
        gap_max = gap_min + gap_span
        for index, name in enumerate(groups):
            position = numeric_fraction + 0.12 * (index + 1)
            levels[name] = (
                runtime_min * 10 ** (runtime_span * position),
                gap_min + gap_span * position,
            )
    metadata = dict(
        runtime_ymin=runtime_min,
        runtime_ymax=runtime_max,
        runtime_tick_min=lower_power,
        runtime_tick_max=upper_power,
        gap_ymin=gap_min,
        gap_ymax=gap_max,
        gap_tick_step=gap_step,
        gap_tick_count=round(gap_end / gap_step),
    )
    for name in FAILURE_GROUPS:
        metadata["has_" + name + "_line"] = int(name in groups)
        metadata["runtime_" + name + "_y"], metadata["gap_" + name + "_y"] = levels.get(
            name, (math.nan, math.nan)
        )
    for row in rows:
        row.update(metadata)
        for outcome in FAILURES:
            group = next(
                name for name, outcomes in FAILURE_GROUPS.items() if outcome in outcomes
            )
            runtime_y, gap_y = levels.get(group, (math.nan, math.nan))
            row[outcome + "_runtime_marker"] = (
                runtime_y if row["plot_status"] == outcome else math.nan
            )
            row[outcome + "_gap_marker"] = (
                gap_y if row["plot_status"] == outcome else math.nan
            )


def collect_reference_rows(p, execution, reference_kind):
    if reference_kind not in ("under", "over"):
        raise ValueError(f"Unknown bound reference: {reference_kind}")
    cutoffs = [
        cfg for cfg in p.TOOL_NAMES["storm"].CONFIGS if cfg["family"] == "cutoff"
    ]
    reference_configs = (
        cutoffs
        if reference_kind == "under"
        else [
            cfg
            for cfg in p.TOOL_NAMES["storm"].CONFIGS
            if cfg["family"] == "discretisation"
        ]
    )
    rows = []
    included = [
        inst
        for inst in p.benchmarks.INSTANCES
        if any(
            p.get_result(execution, "storm", cfg["id"], inst["id"]) for cfg in cutoffs
        )
    ]
    for index, inst in enumerate(included):
        runs = [
            p.get_result(execution, "storm", cfg["id"], inst["id"]) for cfg in cutoffs
        ]
        candidates = [
            p.get_result(execution, "storm", cfg["id"], inst["id"])
            for cfg in reference_configs
        ]
        reference = max(
            (run for run in candidates if p.is_successful_result(run)),
            key=lambda run: approximation_score(p, run, inst, reference_kind),
            default=None,
        )
        reference_bound = (
            p.parse_result_value(reference["result"])[1] if reference else math.nan
        )
        label = instance_label(inst)
        statuses = [p.runtime_status(run) if run else "missing" for run in runs]
        plot_statuses = [
            "memout" if status == "killed" else status for status in statuses
        ]
        for cfg, run, status, plot_status in zip(
            cutoffs, runs, statuses, plot_statuses
        ):
            success = status == "successful"
            runtime = float(run["wallclock-time"]) if run else math.nan
            if run and (not math.isfinite(runtime) or runtime <= 0):
                raise ValueError(f"Invalid runtime in {run['id']}")
            bound = p.parse_result_value(run["result"])[1] if success else math.nan
            if success and not math.isfinite(bound):
                raise ValueError(f"Non-finite bound in {run['id']}")
            gap = math.nan
            if success and math.isfinite(reference_bound):
                if reference_kind == "over":
                    lower, upper = (
                        (reference_bound, bound)
                        if inst["property"]["dir"] == "min"
                        else (bound, reference_bound)
                    )
                    if lower > upper + 1e-7 * max(abs(lower), abs(upper), 1):
                        raise ValueError(
                            f"Inconsistent bound interval in {run['id']}: [{lower}, {upper}]"
                        )
                gap = relative_gap(bound, reference_bound)
            exploration = run.get("belief-exploration", {}) if success else {}
            row = dict(
                instance=inst["id"],
                instance_index=index,
                aggregate_label=label,
                configuration=cfg["id"],
                threshold=cfg["size-threshold"],
                status=status,
                plot_status=plot_status,
                recorded_seconds=runtime,
                cutoff_seconds=runtime if success else math.nan,
                explored_beliefs=exploration.get("explored", math.nan),
                discovered_beliefs=exploration.get("discovered", math.nan),
                exploration_complete=(
                    int(exploration["complete"]) if exploration else -1
                ),
                constructed_states=(
                    run.get("belief-mdp", {}).get("states", math.nan)
                    if run
                    else math.nan
                ),
                cutoff_bound=bound,
                reference_configuration=(
                    reference["configuration-id"] if reference else ""
                ),
                reference_bound=reference_bound,
                reference_seconds=(
                    reference["wallclock-time"] if reference else math.nan
                ),
                reference_kind=reference_kind,
                gap_percent=gap,
            )
            for outcome in FAILURES:
                row[outcome + "_seconds"] = (
                    runtime if plot_status == outcome else math.nan
                )
                row["has_" + outcome] = int(outcome in plot_statuses)
            rows.append(row)
    for row in rows:
        row["runtime_gap_ymode"] = "linear"
        row["gap_ylabel"] = r"relative gap (\%)"
    add_failure_lines(rows)
    return rows


def collect_rows(p, execution):
    """Store both references beside each measured run, without duplicating runs."""
    under = collect_reference_rows(p, execution, "under")
    over = collect_reference_rows(p, execution, "over")
    rows = []
    for under_row, over_row in zip(under, over):
        if (under_row["instance"], under_row["configuration"]) != (
            over_row["instance"],
            over_row["configuration"],
        ):
            raise ValueError("Under- and over-approximation rows do not match")
        row = {
            key: value
            for key, value in under_row.items()
            if not key.startswith(("reference_", "gap_"))
            and key != "runtime_gap_ymode"
            and not key.endswith("_gap_marker")
        }
        for name, source in (("under", under_row), ("over", over_row)):
            for key, value in source.items():
                if key.startswith(("reference_", "gap_")) and key != "reference_kind":
                    row[name + "_" + key] = value
                elif key.endswith("_gap_marker"):
                    row[key.replace("_gap_marker", "_" + name + "_gap_marker")] = value
        rows.append(row)
    return rows


def save_paper_data(root, rows):
    """Export small tables so LaTeX reads each plotted point only once."""
    by_instance = {}
    for row in rows:
        by_instance.setdefault(row["instance"], row)
    series = list(by_instance.values())
    series.sort(key=lambda row: row["instance_index"])
    metadata_keys = ["instance", "instance_index", "aggregate_label"]
    metadata_keys += ["has_" + group + "_line" for group in FAILURE_GROUPS]
    metadata_keys += [
        "runtime_" + field
        for field in (
            "ymin",
            "ymax",
            "tick_min",
            "tick_max",
            "memout_y",
            "timeout_y",
            "failed_y",
        )
    ]
    for reference in ("under", "over"):
        metadata_keys += [
            reference + "_gap_" + field
            for field in (
                "ylabel",
                "ymin",
                "ymax",
                "tick_step",
                "tick_count",
                "memout_y",
                "timeout_y",
                "failed_y",
            )
        ]
    with (root / "plot-series.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=metadata_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(series)

    by_run = {(row["instance"], row["threshold"]): row for row in rows}
    metrics = {
        "runtime": "cutoff_seconds",
        "under_gap": "under_gap_percent",
        "over_gap": "over_gap_percent",
    }
    columns = [
        f"{metric}_{row['instance_index']}" for metric in metrics for row in series
    ]
    with (root / "plot-curves.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["threshold", *columns])
        writer.writeheader()
        for threshold in sorted({row["threshold"] for row in rows}):
            curve = {"threshold": threshold}
            for metric, value_key in metrics.items():
                for instance in series:
                    run = by_run[(instance["instance"], threshold)]
                    if run["plot_status"] in FAILURES:
                        value = run[metric + "_" + run["plot_status"] + "_y"]
                    else:
                        value = run[value_key]
                    curve[f"{metric}_{instance['instance_index']}"] = value
            writer.writerow(curve)


def save_paper_figure(root):
    (root / "paper-figure.tex").write_text(
        r"\begin{figure}[t]"
        + "\n"
        + r"  \centering"
        + "\n"
        + r"  \StormPOMDPAggregateFigure"
        + "\n"
        + r"  \caption{Belief exploration for $19$ POMDPs in \textsc{Storm} with different limits on the number of explored beliefs (size limit $\tau$)."
        + "\n"
        + r"    Left: runtime."
        + "\n"
        + r"    Centre: relative gap between computed bound value and the best computed under-approximation."
        + "\n"
        + r"    Right: relative gap between computed bound value and the best computed over-approximation (using belief interpolation)."
        + "\n"
        + r"    TO and MO indicate timeouts and memory exhaustion.}"
        + "\n"
        + r"  \label{fig:pomdp-benchmarks}"
        + "\n"
        + r"\end{figure}"
        + "\n",
        encoding="utf-8",
    )


def save_plots(p, execution):
    rows = collect_rows(p, execution)
    if not rows:
        print("No cut-off runs: aggregate plots not generated.")
        return None
    root = Path(p.OUT_DIR) / "plots"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "plot-data.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    save_paper_data(root, rows)
    shutil.copyfile(
        Path(__file__).parent / "latex" / "pomdp-aggregate-plots.tex",
        root / "aggregate-plots.tex",
    )
    save_paper_figure(root)
    (root / "runtime-comparison.tex").write_text(
        r"\documentclass[border={0pt 2pt 0pt 2pt},class=llncs]{standalone}"
        + "\n"
        + r"\input{aggregate-plots.tex}"
        + "\n"
        + r"\StormPOMDPLoadAggregateData{.}"
        + "\n"
        + r"\begin{document}"
        + "\n"
        + r"\begin{minipage}{12.2cm}"
        + "\n"
        + r"\StormPOMDPAggregateFigure"
        + "\n"
        + r"\end{minipage}"
        + "\n"
        + r"\end{document}"
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated aggregate plots for {len(set(row['instance'] for row in rows))} instances in {root}"
    )
    return root


def compile_plots(root):
    """Resolve the shared legend, render a PNG, then remove LaTeX build files."""
    command = [
        "lualatex",
        "--interaction=nonstopmode",
        "--halt-on-error",
        "runtime-comparison.tex",
    ]
    try:
        for _ in range(2):
            subprocess.run(
                command,
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        subprocess.run(
            [
                "pdftoppm",
                "-singlefile",
                "-r",
                "160",
                "-png",
                "runtime-comparison.pdf",
                "runtime-comparison",
            ],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout.decode(errors="replace"))
        raise
    for suffix in (
        ".aux",
        ".log",
        ".out",
        ".toc",
        ".fls",
        ".fdb_latexmk",
        ".synctex.gz",
    ):
        (root / ("runtime-comparison" + suffix)).unlink(missing_ok=True)
