"""Compare two log sets without changing the logs or the active benchmark registry."""

import argparse
import csv
import json
import math
from pathlib import Path
import re
import shlex
import statistics

import benchmarks
import postprocess as p
import storm


def status(run):
    if run is None:
        return "missing"
    if run.get("timeout"):
        return "timeout"
    if run.get("memout"):
        return "memout"
    return "successful" if p.is_successful_result(run) else "failed"


def bound(run):
    return p.parse_result_value(run["result"])[1] if status(run) == "successful" else None


def load_runs(directory):
    """Read thresholds from recorded commands, including retired configurations."""
    runs = {}
    directory = Path(directory)
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"No JSON execution records in {directory}")
    for filename in files:
        run = json.loads(filename.read_text())
        if run["tool"] != "storm":
            raise ValueError(f"Unsupported tool in {filename}: {run['tool']}")
        benchmark = benchmarks.from_id(run["benchmark-id"])
        if len(run["commands"]) != 1:
            raise ValueError(f"Expected a single Storm command in {filename}")
        args = shlex.split(run["commands"][0])

        def option(name):
            return args[args.index(name) + 1] if name in args else None

        if option("--belief-exploration") == "unfold" and "--use-clipping" not in args:
            family, parameter = "cutoff", int(option("--size-threshold"))
            if parameter <= 0:
                raise ValueError(f"Only explicit cut-offs are supported: {filename}")
        elif option("--belief-exploration") == "discretize":
            family = "discretisation"
            parameter = (int(option("--resolution")), option("--triangulationmode") or "static")
        elif "--check-fully-observable" in args:
            family, parameter = "mdp", None
        else:
            raise ValueError(f"Unrecognised Storm method in {filename}")
        logfile = directory / Path(run["log"]).name
        text = logfile.read_text()
        # Call the parser directly: parse_tool_output also rewrites source logs
        # and resolves IDs against the current experiment configuration.
        storm.parse_logfile(text, run)
        run["benchmark"] = benchmark
        run["family"] = family
        run["parameter"] = parameter
        memory = re.search(r"peak memory usage:\s*([\d.]+)MB", text)
        run["peak-memory-mb"] = float(memory.group(1)) if memory else None
        key = (run["benchmark-id"], family, parameter)
        if key in runs:
            raise ValueError(f"Duplicate benchmark/method/parameter in {directory}: {key}")
        runs[key] = run
    return runs


def write_csv(path, rows):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def describe_key(key):
    if key[1] == "cutoff":
        return str(key[2])
    if key[1] == "discretisation":
        return f"resolution {key[2][0]}, {key[2][1]}"
    return "fully observable"


def compare(old, new):
    rows = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        av, bv = bound(a), bound(b)
        comparable = av is not None and bv is not None
        direction = (a or b)["benchmark"]["property"]["dir"]
        if comparable:
            difference = p.comparison_value(bv) - p.comparison_value(av)
            improvement = difference if ((key[1] == "cutoff") == (direction == "max")) else -difference
            quality = "same" if improvement == 0 else "improved" if improvement > 0 else "worse"
        else:
            quality = "unavailable"
        rows.append({
            "instance": key[0], "method": key[1], "parameter": describe_key(key),
            "old_configuration": a["configuration-id"] if a else "",
            "new_configuration": b["configuration-id"] if b else "",
            "old_status": status(a), "new_status": status(b),
            "old_bound": av, "new_bound": bv,
            "new_minus_old_bound": bv - av if comparable else None,
            "bound_change": quality,
            "old_seconds": a["wallclock-time"] if a else None,
            "new_seconds": b["wallclock-time"] if b else None,
            "old_over_new_time": a["wallclock-time"] / b["wallclock-time"] if comparable and b["wallclock-time"] > 0 else None,
            "old_states": a.get("belief-mdp", {}).get("states") if a else None,
            "new_states": b.get("belief-mdp", {}).get("states") if b else None,
            "old_peak_memory_mb": a.get("peak-memory-mb") if a else None,
            "new_peak_memory_mb": b.get("peak-memory-mb") if b else None,
            "same_commands": a["commands"] == b["commands"] if a and b else None,
            "same_time_limit": a["time-limit"] == b["time-limit"] if a and b else None,
        })
    return rows


def duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m {seconds:02d}s"


def write_memory_comparison(rows, output):
    memory_rows = []
    for row in rows:
        a, b = row["old_peak_memory_mb"], row["new_peak_memory_mb"]
        paired = row["old_status"] == row["new_status"] == "successful" and a is not None and b is not None and a > 0
        memory_rows.append({
            "instance": row["instance"], "method": row["method"], "parameter": row["parameter"],
            "old_status": row["old_status"], "new_status": row["new_status"],
            "old_peak_mib": a, "new_peak_mib": b, "paired_successful": paired,
            "new_minus_old_mib": b - a if paired else None,
            "reduction_percent": 100 * (1 - b / a) if paired else None,
        })
    write_csv(output / "memory.csv", memory_rows)
    paired = [row for row in memory_rows if row["paired_successful"]]
    groups = [
        ("All configurations", paired),
        ("Cut-offs", [row for row in paired if row["method"] == "cutoff"]),
        ("Cut-offs at thresholds ≥ 1,000,000", [row for row in paired if row["method"] == "cutoff" and int(row["parameter"]) >= 1_000_000]),
        ("Discretisation", [row for row in paired if row["method"] == "discretisation"]),
        ("MDP", [row for row in paired if row["method"] == "mdp"]),
    ]
    lines = ["# Peak memory comparison\n",
             "Storm reports peak resident memory. Its log labels these values MB, but the CLI converts "
             "the operating-system measurement to MiB (1,024² bytes). GiB values below divide the reported value by 1,024. "
             "These are per-run peaks; they are not summed into a total memory footprint.\n",
             "| Group | Successful pairs | Lower in new | Equal | Higher in new | Median reduction |",
             "|---|---:|---:|---:|---:|---:|"]
    for label, selected in groups:
        changes = [row["reduction_percent"] for row in selected]
        median = f"{statistics.median(changes):.1f}%" if changes else "n/a"
        lines.append(f"| {label} | {len(selected)} | {sum(change > 0 for change in changes)} | "
                     f"{sum(change == 0 for change in changes)} | {sum(change < 0 for change in changes)} | {median} |")
    cut_rows = [row for row in memory_rows if row["method"] == "cutoff"]
    largest = max((int(row["parameter"]) for row in cut_rows), default=None)
    lines += ["", f"## Largest tested cut-off: {largest:,}\n" if largest else "## Largest tested cut-off\n",
              "| Instance | Old peak (GiB) | New peak (GiB) | Reduction |", "|---|---:|---:|---:|"]
    for row in cut_rows:
        if int(row["parameter"]) != largest:
            continue
        a, b = row["old_peak_mib"], row["new_peak_mib"]
        old_cell = f"{a / 1024:.2f}" if a is not None else f"unavailable ({row['old_status']})"
        new_cell = f"{b / 1024:.2f}" if b is not None else f"unavailable ({row['new_status']})"
        change = f"{row['reduction_percent']:.1f}%" if row["paired_successful"] else "n/a"
        lines.append(f"| {row['instance']} | {old_cell} | {new_cell} | {change} |")
    excluded = [row for row in memory_rows if not row["paired_successful"]]
    if excluded:
        lines += ["", "## Unpaired measurements\n"]
        for row in excluded:
            def measurement(side):
                value = row[f"{side}_peak_mib"]
                return f"{value:,.0f} MiB ({value / 1024:.2f} GiB)" if value is not None else "no reported peak"
            lines.append(f"- {row['instance']}, {row['method']}: {row['parameter']}: "
                         f"old {row['old_status']}, {measurement('old')}; new {row['new_status']}, {measurement('new')}.")
        lines.append("\nThese runs are excluded from paired reductions and the scatter plot. Missing peaks are not treated as zero.\n")
    lines += ["",
              "The large cut-off runs show a clearer reduction than the small runs and reference methods. "
              "Some small-run peaks differ by only a few MiB, and the logs report whole MiB. "
              "The measurements alone do not identify the cause of the memory differences.\n"]
    (output / "memory-report.md").write_text("\n".join(lines))
    if not paired:
        return
    values = [row[field] for row in paired for field in ("old_peak_mib", "new_peak_mib") if row[field] > 0]
    lower = 2 ** math.floor(math.log2(min(values)))
    upper = 2 ** math.ceil(math.log2(max(values)))
    body = [r"\begin{tikzpicture}\begin{axis}[" + "\n",
            r"width=9cm,height=9cm,xmode=log,ymode=log,grid=major,major grid style={black!15}," + "\n",
            f"xmin={lower},xmax={upper},ymin={lower},ymax={upper},\n",
            r"xlabel={Old peak memory (MiB)},ylabel={New peak memory (MiB)}," + "\n",
            r"xticklabel style={font=\footnotesize},yticklabel style={font=\footnotesize}," + "\n",
            r"legend columns=3,legend style={font=\footnotesize}," + "\n",
            "]\n", rf"\addplot[color=black!60,dashed,no marks,forget plot] coordinates {{({lower},{lower}) ({upper},{upper})}};" + "\n"]
    for method, label, color, mark in [("cutoff", "Cut-off", "plotcut", "o"),
                                      ("discretisation", "Discretisation", "plotdiscr", "triangle"),
                                      ("mdp", "MDP", "black!65", "square")]:
        selected = [row for row in paired if row["method"] == method]
        if not selected:
            continue
        table = [["old", "new"]] + [[row["old_peak_mib"], row["new_peak_mib"]] for row in selected]
        body += [rf"\addplot[color={color},only marks,mark={mark},mark size=1.5pt] table[x=old,y=new,col sep=space,row sep=\\]{{" + p.latex_plot_table(table) + "};\n",
                 rf"\addlegendentry{{{label}}}" + "\n"]
    body.append(r"\end{axis}\end{tikzpicture}" + "\n")
    (output / "memory-scatter.tex").write_text("% Paired successful peak-memory measurements; below equality means lower memory in new.\n" + p.style_latex_plot("".join(body)))
    preview = [r"\documentclass[a4paper,10pt]{article}", r"\usepackage[margin=20mm]{geometry}",
               r"\usepackage{pgfplots}\pgfplotsset{compat=1.18}", r"\begin{document}",
               r"\section*{Peak memory: old versus new}",
               f"{len(paired)} pairs successful in both log sets. Points below the dashed equality line use less memory in the new run.\n",
               r"\begin{center}\input{memory-scatter.tex}\end{center}",
               f"Excluded run pairs with incomplete measurements or unsuccessful outcomes: {len(excluded)}. "
               "See memory-report.md for their measured peaks and outcomes.\n",
               r"\end{document}"]
    (output / "memory-preview.tex").write_text("\n".join(preview) + "\n")


def write_report(old, new, rows, output, old_dir, new_dir):
    old_total = sum(run["wallclock-time"] for run in old.values())
    new_total = sum(run["wallclock-time"] for run in new.values())
    paired = [row for row in rows if row["old_status"] == row["new_status"] == "successful"]
    old_paired = sum(row["old_seconds"] for row in paired)
    new_paired = sum(row["new_seconds"] for row in paired)
    changed = [row for row in paired if row["bound_change"] != "same"]
    summaries = []
    for benchmark in benchmarks.INSTANCES:
        selected = [row for row in rows if row["instance"] == benchmark["id"]]
        if not selected:
            continue
        common = [row for row in selected if row["old_status"] == row["new_status"] == "successful"]
        a = sum(row["old_seconds"] for row in common)
        b = sum(row["new_seconds"] for row in common)
        summaries.append({"instance": benchmark["id"], "paired_successes": len(common),
                          "old_paired_seconds": a, "new_paired_seconds": b,
                          "old_over_new_time": a / b if b else None,
                          "improved_bounds": sum(row["bound_change"] == "improved" for row in selected),
                          "worse_bounds": sum(row["bound_change"] == "worse" for row in selected)})
    write_csv(output / "benchmark-summary.csv", summaries)
    lines = ["# Log comparison\n", f"Old: `{old_dir}`. New: `{new_dir}`.\n",
             "| | Old | New |", "|---|---:|---:|",
             f"| Runs | {len(old)} | {len(new)} |",
             f"| Successful | {sum(status(run) == 'successful' for run in old.values())} | {sum(status(run) == 'successful' for run in new.values())} |",
             f"| Total recorded runtime, including failures | {duration(old_total)} | {duration(new_total)} |",
             f"| Runtime of the {len(paired)} pairs successful in both | {duration(old_paired)} | {duration(new_paired)} |", ""]
    if old_paired:
        lines.append(f"The new runtime for paired successful runs is {(1 - new_paired / old_paired) * 100:.1f}% lower.\n")
    lines.append(f"Bound comparison at 10^-{p.RESULT_COMPARISON_DECIMALS} precision: "
                 f"{sum(row['bound_change'] == 'same' for row in paired)} equal, "
                 f"{sum(row['bound_change'] == 'improved' for row in paired)} improved, "
                 f"{sum(row['bound_change'] == 'worse' for row in paired)} worse.\n")
    lines += ["## Changed bounds\n", "| Instance | Method/parameter | Old bound | New bound | New minus old |",
              "|---|---|---:|---:|---:|"]
    for row in changed:
        lines.append(f"| {row['instance']} | {row['method']}: {row['parameter']} | {row['old_bound']:.10g} | {row['new_bound']:.10g} | {row['new_minus_old_bound']:+.6g} |")
    lines += ["", "## Changed outcomes\n"]
    for row in rows:
        if row["old_status"] != row["new_status"]:
            lines.append(f"- {row['instance']}, {row['method']}: {row['parameter']}: {row['old_status']} → {row['new_status']}.")
    lines += ["", "## Runtime by benchmark\n", "Only pairs successful in both are included in this table.\n",
              "| Instance | Pairs | Old seconds | New seconds | Old/new |", "|---|---:|---:|---:|---:|"]
    for row in summaries:
        ratio = f"{row['old_over_new_time']:.2f}" if row["old_over_new_time"] is not None else "n/a"
        lines.append(f"| {row['instance']} | {row['paired_successes']} | {row['old_paired_seconds']:.2f} | {row['new_paired_seconds']:.2f} | {ratio} |")
    lines += ["", "Thresholds and discretisation parameters are read from the actual recorded commands. "
              "Each dataset is plotted at its own thresholds; differing grids are not paired or interpolated. "
              "Bounds use the optimisation direction to determine whether a change improves the approximation. "
              "Failed runtimes contribute to total runtime, but not to successful-runtime ratios.\n",
              f"Changed command lines among matched runs: {sum(row['same_commands'] is False for row in rows)}. "
              f"Changed time limits: {sum(row['same_time_limit'] is False for row in rows)}.\n",
              "These are single-run observations. The records do not establish identical machine load or an exact source revision. "
              "Runtime differences cannot be attributed to a particular implementation change from these records alone.\n"]
    (output / "report.md").write_text("\n".join(lines))
    print(f"Old: {duration(old_total)}; new: {duration(new_total)}; {len(changed)} changed paired bounds.")


def save_plots(old, new, output):
    folder = output / "plots"
    folder.mkdir(exist_ok=True)
    preview = [r"\documentclass[a4paper,10pt]{article}", r"\usepackage[margin=20mm]{geometry}",
               r"\usepackage{pgfplots}\pgfplotsset{compat=1.18}", r"\begin{document}"]
    reference_rows = []
    count = 0
    for benchmark in benchmarks.INSTANCES:
        identity = benchmark["id"]
        sets = [{key: run for key, run in dataset.items() if key[0] == identity} for dataset in (old, new)]
        thresholds = sorted({key[2] for dataset in sets for key in dataset if key[1] == "cutoff"})
        if not thresholds:
            continue
        refs = []
        for label, dataset in zip(("Old", "New"), sets):
            candidates = [run for key, run in dataset.items() if key[1] == "discretisation" and status(run) == "successful"]
            best = max(candidates, key=lambda run: p.result_selection_score(run, p.expected_bound_relation("discr", benchmark)), default=None)
            mdp = dataset.get((identity, "mdp", None))
            if status(mdp) != "successful":
                mdp = None
            refs.append((best, mdp))
            for method, run in zip(("discretisation", "mdp"), (best, mdp)):
                reference_rows.append({"instance": identity, "dataset": label, "method": method,
                                       "configuration": run["configuration-id"] if run else "",
                                       "bound": bound(run), "seconds": run["wallclock-time"] if run else None})
        for metric in ("value", "runtime"):
            powers = range(math.ceil(math.log10(thresholds[0])), math.floor(math.log10(thresholds[-1])) + 1)
            options = [r"width=\dimexpr\linewidth-14mm\relax,height=4.5cm,",
                       r"legend columns=2,legend style={font=\footnotesize},",
                       r"xticklabel style={font=\scriptsize},yticklabel style={font=\scriptsize},",
                       r"x label style={font=\footnotesize},y label style={font=\footnotesize},",
                       f"xmode=log,xmin={thresholds[0]},xmax={thresholds[-1]},",
                       "xtick={" + ",".join(str(10**exponent) for exponent in powers) + "},",
                       "xticklabels={" + ",".join(rf"$10^{{{exponent}}}$" for exponent in powers) + "},",
                       r"xlabel={Cut-off threshold $\tau$},unbounded coords=jump,grid=major,major grid style={black!15},"]
            if metric == "runtime":
                times = [run["wallclock-time"] for dataset in sets for run in dataset.values() if status(run) == "successful" and run["wallclock-time"] > 0]
                low = math.floor(math.log10(min(times, default=0.01)))
                high = math.ceil(math.log10(max(600, *times)))
                failure_y = 10 ** (high + 1)
                options += [rf"ylabel={{Runtime (s)}},ymode=log,ymin={10**low},ymax={failure_y * 2},",
                            "ytick={" + ",".join(str(10**exponent) for exponent in range(low, high + 2)) + "},",
                            "yticklabels={" + ",".join([f"{10**exponent:g}" for exponent in range(low, high + 1)] + ["TO/MO"]) + "},"]
            else:
                options += [r"ylabel={Value bound},scaled y ticks=false,enlarge y limits=0.08,",
                            r"yticklabel style={font=\scriptsize,/pgf/number format/fixed relative,/pgf/number format/precision=5},"]
            body = [r"\begin{tikzpicture}\begin{axis}[" + "\n" + "\n".join(options) + "]\n"]
            for label, dataset, mark, line in zip(("Old", "New"), sets, ("o", "triangle*"), ("dashed", "solid")):
                table = [["threshold", "y"]]
                for key, run in sorted(dataset.items()):
                    if key[1] != "cutoff":
                        continue
                    y = (bound(run) if metric == "value" else run["wallclock-time"]) if status(run) == "successful" else None
                    table.append([key[2], y if y is not None else "nan"])
                body += [rf"\addplot[color=plotcut,mark={mark},{line}] table[x=threshold,y=y,col sep=space,row sep=\\]{{" + p.latex_plot_table(table) + "};\n",
                         rf"\addlegendentry{{{label} cut-off}}" + "\n"]
            for method, index, color in (("discr.", 0, "plotdiscr"), ("MDP", 1, "black!65")):
                for label, reference, line in zip(("Old", "New"), refs, ("dashed", "densely dotted")):
                    run = reference[index]
                    if not run:
                        continue
                    y = bound(run) if metric == "value" else run["wallclock-time"]
                    body += [rf"\addplot[color={color},{line},no marks] coordinates {{({thresholds[0]},{y}) ({thresholds[-1]},{y})}};" + "\n",
                             rf"\addlegendentry{{{label} {method}}}" + "\n"]
            if metric == "runtime":
                body.append(rf"\addplot[color=black!25,dashed,no marks,forget plot] coordinates {{({thresholds[0]},{failure_y}) ({thresholds[-1]},{failure_y})}};" + "\n")
                for dataset, mark in zip(sets, ("x", "+")):
                    failures = [key[2] for key, run in dataset.items() if key[1] == "cutoff" and status(run) in ("timeout", "memout")]
                    if failures:
                        body.append(rf"\addplot[color=red!75!black,only marks,mark={mark},mark size=3pt,forget plot] coordinates {{"
                                    + " ".join(f"({threshold},{failure_y})" for threshold in failures) + "};\n")
            body.append(r"\end{axis}\end{tikzpicture}" + "\n")
            (folder / f"{metric}-{identity}.tex").write_text("% Generated by scripts/compare_logs.py; real thresholds from recorded commands.\n" + p.style_latex_plot("".join(body)))
        if count and count % 3 == 0:
            preview.append(r"\clearpage")
        preview += [r"\noindent\begin{minipage}{\linewidth}", r"\section*{\small\texttt{\detokenize{" + identity + "}}}"]
        for metric in ("value", "runtime"):
            if metric == "runtime":
                preview.append(r"\hfill")
            preview += [r"\begin{minipage}[t]{0.48\linewidth}\centering", r"\input{plots/" + metric + "-" + identity + ".tex}", r"\end{minipage}"]
        failures = [(label, key[2], status(run)) for label, dataset in zip(("Old", "New"), sets)
                    for key, run in dataset.items() if key[1] == "cutoff" and status(run) != "successful"]
        if failures:
            preview.append(r"\par\smallskip\footnotesize " + "; ".join(f"{label}: threshold {threshold:,}, {outcome}" for label, threshold, outcome in failures) + ". TO/MO markers: old $\\times$, new $+$. ")
        preview.append(r"\end{minipage}\par\bigskip")
        count += 1
    preview.append(r"\end{document}")
    (output / "preview.tex").write_text("\n".join(preview) + "\n")
    write_csv(output / "references.csv", reference_rows)
    return count * 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_logs")
    parser.add_argument("new_logs")
    parser.add_argument("--output", default="data/log-comparison")
    args = parser.parse_args()
    old, new = load_runs(args.old_logs), load_runs(args.new_logs)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows = compare(old, new)
    write_csv(output / "runs.csv", rows)
    write_report(old, new, rows, output, args.old_logs, args.new_logs)
    write_memory_comparison(rows, output)
    plot_count = save_plots(old, new, output)
    print(f"Wrote {output}/report.md, CSV comparisons, {plot_count} plots and preview.tex.")


if __name__ == "__main__":
    main()
