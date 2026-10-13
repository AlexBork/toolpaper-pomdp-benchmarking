"""Per-instance PGFPlots for explicit cut-offs and fixed reference runs."""

import csv
import math
import os
import shutil
from pathlib import Path


def save_plots(p, execution, instances):
    root = os.path.join(p.GENERAL_PLOT_DIR, "cutoff-threshold")
    os.makedirs(root, exist_ok=True)
    configurations = sorted(
        (cfg["size-threshold"], cfg["id"])
        for cfg in p.storm.CONFIGS
        if cfg["family"] == "cutoff"
    )
    discretisations = [cfg["id"] for cfg in p.storm.CONFIGS if cfg["family"] == "discretisation"]
    thresholds = [threshold for threshold, _ in configurations]
    powers = list(range(math.ceil(math.log10(thresholds[0])), math.floor(math.log10(thresholds[-1])) + 1))
    observations = [["instance", "configuration", "threshold", "states", "bound", "wallclock_seconds", "status"]]
    references = [["instance", "reference", "configuration", "bound", "wallclock_seconds"]]
    summary = [["instance", "runs", "successful", "wallclock_seconds"]]
    plot_columns = [
        "instance", "configuration", "threshold", "states", "value", "runtime",
        "wallclock_seconds", "status", "discretisation_configuration",
        "discretisation_value", "discretisation_runtime", "mdp_value", "mdp_runtime",
        "xmin", "xmax", "x_tick_min", "x_tick_max", "runtime_ymin", "runtime_ymax",
        "runtime_tick_min", "runtime_tick_max", "failure_y", "has_discretisation",
        "has_mdp", "has_failures", "has_timeout", "has_memout", "has_killed",
        "has_failed", "timeout_marker", "memout_marker", "killed_marker", "failed_marker",
    ]
    plot_rows = []
    shutil.copyfile(Path(__file__).parent / "latex" / "pomdp-instance-plots.tex",
                    Path(p.OUT_DIR) / "pomdp-instance-plots.tex")
    preview = [
        r"\documentclass[a4paper,10pt]{article}" + "\n",
        r"\usepackage[margin=20mm]{geometry}" + "\n",
        r"\usepackage{pgfplots}\pgfplotsset{compat=1.18}" + "\n",
        r"\input{pomdp-instance-plots.tex}" + "\n",
        r"\StormPOMDPLoadData{cutoff-threshold-plot-data.csv}" + "\n",
        r"\begin{document}" + "\n",
    ]
    all_runs = [run for cfg in p.storm.CONFIGS
                for run in execution.get(p.storm.NAME, {}).get(cfg["id"], {}).values()]
    total_seconds = sum(run.get("wallclock-time", 0) for run in all_runs)
    preview.append(f"{len(all_runs)} runs; cumulative wall-clock runtime: {total_seconds:.2f} seconds "
                   + f"({total_seconds / 3600:.3f} hours).\n\n")
    logdirs = sorted({os.path.dirname(run["log"]) for run in all_runs})
    preview.append("Sources: " + ", ".join(r"\texttt{\detokenize{" + directory + "}}"
                                           for directory in logdirs) + ".\n\n")
    count = 0
    for benchmark in p.benchmarks.INSTANCES:
        inst_id = benchmark["id"]
        if not any(p.get_result(execution, p.storm.NAME, cfg["id"], inst_id)
                   for cfg in p.storm.CONFIGS):
            continue
        direction = benchmark["property"]["dir"]
        runs = [p.get_result(execution, p.storm.NAME, cfg["id"], inst_id)
                for cfg in p.storm.CONFIGS]
        runs = [run for run in runs if run is not None]
        summary.append([inst_id, len(runs), sum(p.is_successful_result(run) for run in runs),
                        sum(run.get("wallclock-time", 0) for run in runs)])
        candidates = [p.get_result(execution, p.storm.NAME, cfg, inst_id) for cfg in discretisations]
        candidates = [run for run in candidates if p.is_successful_result(run)]
        best = max(candidates, key=lambda run: p.result_selection_score(
            run, p.expected_bound_relation("discr", benchmark)
        ), default=None)
        mdp = p.get_result(execution, p.storm.NAME, "mdp", inst_id)
        if not p.is_successful_result(mdp):
            mdp = None
        for label, run in [("best-discretisation", best), ("mdp", mdp)]:
            references.append([inst_id, label,
                               run["configuration-id"] if run else "",
                               p.parse_result_value(run["result"])[1] if run else "nan",
                               run["wallclock-time"] if run else "nan"])

        points = []
        failed = []
        for threshold, cfg in configurations:
            run = p.get_result(execution, p.storm.NAME, cfg, inst_id)
            successful = p.is_successful_result(run)
            value = p.parse_result_value(run["result"])[1] if successful else None
            runtime = run.get("wallclock-time") if run else None
            points.append((threshold, value, runtime if successful else None))
            status = p.runtime_status(run) if run is not None else "missing"
            observations.append([inst_id, cfg, threshold,
                                 run.get("belief-mdp", {}).get("states", "") if run else "",
                                 value if value is not None else "nan",
                                 runtime if runtime is not None else "nan", status])
            if not successful:
                failed.append((threshold, status, runtime))
        failure_statuses = {status for _, status, _ in failed if status != "missing"}
        numeric_times = [point[2] for point in points if point[2] is not None and point[2] > 0]
        numeric_times += [run["wallclock-time"] for run in (best, mdp)
                         if run and run["wallclock-time"] > 0]
        lower_power = math.floor(math.log10(min(numeric_times, default=0.01)))
        upper_power = math.ceil(math.log10(max(numeric_times, default=1)))
        upper_power = max(upper_power, lower_power + 1)
        numeric_end = 10 ** upper_power
        failure_y = numeric_end * 10
        ref_values = {}
        for label, run in [("discretisation", best), ("mdp", mdp)]:
            bound = p.parse_result_value(run["result"])[1] if run else math.nan
            runtime = run["wallclock-time"] if run else math.nan
            ref_values[label + "_value"] = bound if math.isfinite(bound) else "nan"
            ref_values[label + "_runtime"] = runtime if math.isfinite(runtime) and runtime > 0 else "nan"
            ref_values["has_" + label] = int(math.isfinite(bound))
        for (threshold, cfg), (_, value, runtime) in zip(configurations, points):
            run = p.get_result(execution, p.storm.NAME, cfg, inst_id)
            status = p.runtime_status(run) if run is not None else "missing"
            row = dict(
                instance=inst_id, configuration=cfg, threshold=threshold,
                states=run.get("belief-mdp", {}).get("states", "nan") if run else "nan",
                value=value if value is not None else "nan",
                runtime=runtime if runtime is not None and runtime > 0 else "nan",
                wallclock_seconds=run.get("wallclock-time", "nan") if run else "nan",
                status=status,
                discretisation_configuration=best["configuration-id"] if best else "unavailable",
                xmin=thresholds[0], xmax=thresholds[-1],
                x_tick_min=powers[0], x_tick_max=powers[-1],
                runtime_ymin=10 ** lower_power,
                runtime_ymax=failure_y * 2 if failure_statuses else numeric_end,
                runtime_tick_min=lower_power, runtime_tick_max=upper_power,
                failure_y=failure_y, has_failures=int(bool(failure_statuses)),
                **ref_values,
            )
            for outcome in ("timeout", "memout", "killed", "failed"):
                row["has_" + outcome] = int(outcome in failure_statuses)
                row[outcome + "_marker"] = failure_y if status == outcome else "nan"
            plot_rows.append(row)

        for metric, command in [("value", "StormPOMDPValuePlot"), ("runtime", "StormPOMDPRuntimePlot")]:
            filename = f"{metric}-{inst_id}.tex"
            with open(os.path.join(root, filename), "w") as output:
                output.write("% Generated by scripts/postprocess.py; data are in cutoff-threshold-plot-data.csv.\n")
                output.write("% Load pomdp-instance-plots.tex and call \\StormPOMDPLoadData once first.\n")
                output.write("\\" + command + "{" + inst_id + "}\n")

        if count and count % 3 == 0:
            preview.append(r"\clearpage" + "\n")
        preview.append(r"\noindent\begin{minipage}{\linewidth}" + "\n")
        preview.append(r"\section*{\small\texttt{\detokenize{" + inst_id + "}}}\n")
        preview.append(f"Objective: {benchmark['property']['type']} {direction}. "
                       + "Discretisation reference: "
                       + (r"\texttt{" + best["configuration-id"] + "}" if best else "unavailable")
                       + ".\n\n")
        for metric in ("value", "runtime"):
            if metric == "runtime":
                preview.append(r"\hfill" + "\n")
            preview.append(r"\begin{minipage}[t]{0.48\linewidth}\centering" + "\n"
                           + r"\input{general-plots/cutoff-threshold/" + metric + "-" + inst_id + ".tex}\n"
                           + r"\end{minipage}" + "\n")
        preview.append(r"\par\medskip" + "\n")
        if failed:
            preview.append("Unavailable bounds: " + ", ".join(
                f"{threshold:,} ({status})" for threshold, status, _ in failed
            ) + (". Failed runs appear on the separate Failure line.\n\n"
                 if failure_statuses else ".\n\n"))
        if best and mdp and p.parse_result_value(best["result"])[1] == p.parse_result_value(mdp["result"])[1]:
            preview.append("The discretisation and MDP value reference lines coincide.\n\n")
        preview.append(r"\end{minipage}\par\bigskip" + "\n")
        count += 1
    preview.append(r"\end{document}" + "\n")
    with open(os.path.join(p.OUT_DIR, "cutoff-threshold-preview.tex"), "w") as output:
        output.writelines(preview)
    with open(os.path.join(p.OUT_DIR, "cutoff-threshold-plot-data.csv"), "w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=plot_columns)
        writer.writeheader()
        writer.writerows(plot_rows)
    p.save_csv(observations, os.path.join(p.OUT_DIR, "cutoff-threshold-observations.csv"))
    p.save_csv(references, os.path.join(p.OUT_DIR, "cutoff-threshold-references.csv"))
    summary.append(["TOTAL", sum(row[1] for row in summary[1:]),
                    sum(row[2] for row in summary[1:]), total_seconds])
    p.save_csv(summary, os.path.join(p.OUT_DIR, "cutoff-threshold-summary.csv"))
    print(f"Generated {count * 2} CSV-backed cut-off plots, shared CSV and TeX commands, "
          + f"and {p.OUT_DIR}/cutoff-threshold-preview.tex.")
