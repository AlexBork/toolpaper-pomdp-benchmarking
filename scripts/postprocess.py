"""Parse the current POMDP suite and generate its dashboard and plots."""

import argparse
from collections import Counter, OrderedDict
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys

import benchmarks
from tools import TOOLS, TOOL_NAMES

OUT_DIR = "data"
RESULT_COMPARISON_DECIMALS = 6


def load_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as json_file:
        return json.load(json_file, object_pairs_hook=OrderedDict)


def parse_result_value(result):
    """Return (relation, value), where relation is '=', '≤', or '≥'."""
    number_pattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    scalar_match = re.fullmatch(
        rf"\s*([≤≥])?\s*({number_pattern})\s*",
        str(result),
    )
    if scalar_match is not None:
        return scalar_match.group(1) or "=", float(scalar_match.group(2))

    interval_match = re.fullmatch(
        rf"\s*\[\s*({number_pattern})\s*,\s*({number_pattern})\s*\]"
        rf"(?:\s*\(width\s*=\s*({number_pattern})\))?\s*",
        str(result),
    )
    if interval_match is not None:
        lower = float(interval_match.group(1))
        upper = float(interval_match.group(2))
        if math.isclose(lower, upper, rel_tol=1e-12, abs_tol=1e-15):
            return "=", (lower + upper) / 2
        raise ValueError(f"Non-degenerate interval result is not supported: {result}")

    raise ValueError(f"Unexpected result string: {result}")


def is_successful_result(data):
    if data is None or "result" not in data:
        return False
    if any(
        data.get(key, False)
        for key in [
            "timeout",
            "memout",
            "execution-error",
            "expected-error",
            "not-supported",
        ]
    ):
        return False
    return True


def expected_bound_relation(cfgbase, benchmark):
    direction = benchmark["property"]["dir"]
    if cfgbase == "cut":  # under-approximation
        return "≥" if direction == "max" else "≤"
    if cfgbase == "discr":  # over-approximation
        return "≤" if direction == "max" else "≥"
    return None


def comparison_value(value):
    return round(float(value), RESULT_COMPARISON_DECIMALS)


def parse_tool_output(execution_json):
    with open(execution_json["log"], "r") as logfile:
        log = logfile.read()
    execution_json["notes"] = [execution_json["invocation-note"]]
    execution_json["benchmark"] = benchmarks.from_id(execution_json["benchmark-id"])

    assert execution_json["tool"] in TOOL_NAMES, "Error: Unknown tool '{}'".format(
        execution_json["tool"]
    )
    tool = TOOL_NAMES[execution_json["tool"]]
    execution_json["configuration"] = tool.config_from_id(
        execution_json["configuration-id"]
    )
    # IDs alone are not enough: historical sweeps used different thresholds.
    args = shlex.split(execution_json["commands"][0])
    configuration = execution_json["configuration"]
    if configuration.get("family") == "cutoff":
        threshold = int(args[args.index("--size-threshold") + 1])
        if threshold != configuration["size-threshold"]:
            raise ValueError(
                f"Recorded threshold {threshold} disagrees with {configuration['id']}"
            )
        execution_json["size-threshold"] = threshold
    tool.parse_logfile(log, execution_json)


def load_standalone_log(path):
    """Read invocation metadata recorded in a standalone Storm log."""
    log = path.read_text(encoding="utf-8-sig")
    header, separator, _ = log.partition("\nOutput:\n")
    fields = dict(re.findall(r"^([^:\n]+):[ \t]*([^\n]*)$", header, re.MULTILINE))
    required = {"Command", "Benchmark", "Configuration", "Repetition", "Time limit"}
    if not separator or not required <= fields.keys():
        raise ValueError(f"{path}: no run JSON or complete standalone log header")
    if fields["Repetition"] != "1":
        raise ValueError(
            f"{path}: repeated runs are not supported by the aggregate report"
        )
    tool = fields.get("Tool")
    if tool is None:
        executable = Path(shlex.split(fields["Command"])[0]).name
        if executable not in {"storm", "storm-pomdp"}:
            raise ValueError(f"{path}: unsupported standalone executable {executable}")
        tool = "storm"
    runtimes = re.findall(
        r"^Wallclock time:\s*([0-9]+(?:\.[0-9]+)?)\s*$", log, re.MULTILINE
    )
    codes = re.findall(r"^Return code:\s*(-?\d+|None)\s*$", log, re.MULTILINE)
    if len(runtimes) != 1 or len(codes) != 1:
        raise ValueError(
            f"{path}: expected one recorded wall-clock time and return code"
        )
    timeout = bool(
        re.search(r"^Computation aborted .*time limit .*exceeded\.", log, re.MULTILINE)
    )
    code = int(codes[0]) if codes[0] != "None" else (-9 if timeout else None)
    return {
        "id": fields.get(
            "Invocation", f"{tool}.{fields['Configuration']}.{fields['Benchmark']}"
        ),
        "benchmark-id": fields["Benchmark"],
        "tool": tool,
        "configuration-id": fields["Configuration"],
        "invocation-note": fields.get("Invocation note", ""),
        "commands": [fields["Command"]],
        "time-limit": float(fields["Time limit"]),
        "log-dir": str(path.parent),
        "log": path.name,
        "wallclock-time": float(runtimes[0]),
        "timeout": timeout,
        "execution-error": not timeout and code != 0,
        "return-codes": [code],
    }


def process_benchmark_instance_data(benchmark_instances, execution_json):
    # gather data from this execution
    bench_id = execution_json["benchmark"]["id"]
    bench_data = OrderedDict()
    bench_data["id"] = execution_json["benchmark"]["id"]
    bench_data["benchmark-set"] = execution_json["benchmark"]["benchmark-set"]
    bench_data["name"] = execution_json["benchmark"]["name"]
    bench_data["formalism"] = execution_json["benchmark"]["model"]["formalism"]
    bench_data["type"] = execution_json["benchmark"]["model"]["type"]
    bench_data["par"] = "_".join(bench_id.split("_")[3:])
    bench_data["property"] = execution_json["benchmark"]["property"]["type"]
    bench_data["property-dir"] = execution_json["benchmark"]["property"]["dir"]
    bench_data["property-id"] = execution_json["benchmark"]["property"]["id"]
    bench_data["dim"] = execution_json["benchmark"]["property"].get(
        "num-bnd-rew-assignments", 0
    )
    bench_data["states"] = execution_json["input-model"]["states"]
    if execution_json["benchmark"]["model"]["type"] != "dtmc":
        bench_data["choices"] = execution_json["input-model"]["choices"]
    if execution_json["benchmark"]["model"]["type"] == "pomdp":
        bench_data["observations"] = execution_json["input-model"]["observations"]
    bench_data["transitions"] = execution_json["input-model"]["transitions"]
    bench_data["invocations"] = [execution_json["id"]]

    # incorporate into existing data
    if not bench_id in benchmark_instances:
        benchmark_instances[bench_id] = bench_data
    else:
        # ensure consistency
        for key in [
            "id",
            "name",
            "formalism",
            "type",
            "par",
            "property",
            "property-dir",
            "property-id",
            "dim",
            "states",
            "choices",
            "observations",
            "transitions",
        ]:
            if key in bench_data:
                if key in benchmark_instances[bench_id]:
                    if benchmark_instances[bench_id][key] != bench_data[key]:
                        print(
                            "WARN: Inconsistency with field {}: '{}' vs '{}'  between any of \n\t{}\nand\t{}".format(
                                key,
                                benchmark_instances[bench_id][key],
                                bench_data[key],
                                benchmark_instances[bench_id]["invocations"],
                                bench_data["invocations"],
                            )
                        )
                else:
                    benchmark_instances[bench_id][key] = bench_data[key]
        # append data
        for key in ["invocations"]:
            if key in bench_data:
                if key in benchmark_instances[bench_id]:
                    benchmark_instances[bench_id][key] += bench_data[key]
                else:
                    benchmark_instances[bench_id][key] = bench_data[key]


def gather_execution_data(logdirs, silent=False):
    exec_data = OrderedDict()  # Tool -> Config -> Benchmark -> Data
    benchmark_instances = OrderedDict()  # ID -> data
    known_benchmark_ids = {benchmark["id"] for benchmark in benchmarks.INSTANCES}
    known_configuration_ids = {
        tool.NAME: {configuration["id"] for configuration in tool.CONFIGS}
        for tool in TOOLS
    }

    for logdir_input in logdirs:
        logdir = os.path.expanduser(logdir_input)
        if not os.path.isdir(logdir):
            print("Error: Directory '{}' does not exist.".format(logdir))

        print("\nGathering execution data for logfiles in {} ...".format(logdir))
        json_files = sorted(
            f
            for f in os.listdir(logdir)
            if f.endswith(".json") and os.path.isfile(os.path.join(logdir, f))
        )
        executions = [load_json(os.path.join(logdir, f)) for f in json_files]
        recorded_logs = {Path(run["log"]).name for run in executions}
        standalone_logs = sorted(
            path
            for path in Path(logdir).glob("*.log")
            if path.is_file() and path.name not in recorded_logs
        )
        executions.extend(load_standalone_log(path) for path in standalone_logs)
        ignored_benchmarks = Counter()
        ignored_configurations = Counter()
        for execution_json in executions:
            benchmark = execution_json["benchmark-id"]
            if benchmark not in known_benchmark_ids:
                ignored_benchmarks[benchmark] += 1
                continue
            tool = execution_json["tool"]
            config = execution_json["configuration-id"]
            if config not in known_configuration_ids.get(tool, set()):
                ignored_configurations[(tool, config)] += 1
                continue
            if not execution_json.get("invocation-note"):
                execution_json["invocation-note"] = ". ".join(
                    TOOL_NAMES[tool].config_from_id(config)["notes"]
                )
            exec_data.setdefault(tool, OrderedDict())
            exec_data[tool].setdefault(config, OrderedDict())
            assert (
                benchmark not in exec_data[tool][config]
            ), "Error: Multiple result files found for {}.{}.{}".format(
                tool, config, benchmark
            )
            execution_json["log"] = os.path.join(logdir, execution_json["log"])
            try:
                parse_tool_output(execution_json)
            except AssertionError as e:
                print(
                    "Error when parsing logfile {}:\n{}".format(
                        execution_json["log"], e
                    )
                )
                continue
            exec_data[tool][config][benchmark] = execution_json
            if "input-model" in execution_json:
                process_benchmark_instance_data(benchmark_instances, execution_json)
            else:
                print(
                    f"WARN: No input-model statistics in failed execution {execution_json['id']}"
                )

        for benchmark, count in sorted(ignored_benchmarks.items()):
            print(
                f"WARN: Ignoring {count} result file(s) for removed benchmark {benchmark}"
            )
        for (tool, config), count in sorted(ignored_configurations.items()):
            print(
                f"WARN: Ignoring {count} result file(s) for removed configuration {tool}.{config}"
            )

    # warn for missing configs:
    if not silent:
        for t in TOOL_NAMES:
            if t not in exec_data:
                print(f"WARN: no data for tool '{t}'")
            else:
                for cfg in TOOL_NAMES[t].CONFIGS:
                    if cfg["id"] not in exec_data[t]:
                        print(f"WARN: no data for {t} config '{cfg['id']}'")
    return exec_data, benchmark_instances


def get_result(exec_data, tool, config, inst_id):
    return exec_data.get(tool, {}).get(config, {}).get(inst_id)


def runtime_status(run):
    """Distinguish recorded kills from confirmed memory errors in run outcomes."""
    if run.get("timeout"):
        return "timeout"
    if is_successful_result(run):
        return "successful"
    if -9 in run.get("return-codes", []):
        return "killed"
    if run.get("memout"):
        return "memout"
    return "failed"


def runtime_duration(seconds):
    seconds = round(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logdirs",
        nargs="+",
        help="Directories containing self-contained run logs (or legacy JSON/log pairs)",
    )
    options = parser.parse_args()
    for directory in options.logdirs:
        if not Path(directory).expanduser().is_dir():
            parser.error(f"Log directory does not exist: {directory}")

    execution, instances = gather_execution_data(options.logdirs)
    if not any(runs for configs in execution.values() for runs in configs.values()):
        parser.error("No runs match the current benchmark registry")
    instances = OrderedDict(sorted(instances.items()))
    root = Path(OUT_DIR)
    root.mkdir(parents=True, exist_ok=True)

    from html_results import save_results
    from plots import save_plots, compile_plots

    save_results(sys.modules[__name__], execution, instances, options.logdirs)
    plot_dir = save_plots(sys.modules[__name__], execution)
    if plot_dir is not None:
        compile_plots(plot_dir)
    (root / "README.md").write_text(
        "# Generated benchmark results\n\n"
        "Sources: "
        + ", ".join(f"`{directory}`" for directory in options.logdirs)
        + ".\n\n"
        "- `html/index.html`: offline results table with links to individual run pages.\n"
        "- `html/logs/`: one HTML page per measured run, with its invocation, metadata, and source log.\n"
        "  Share the entire `html/` folder, including its CSS and JavaScript assets.\n"
        "- `plots/`: the audit CSV, compact CSV plot tables, reusable TeX commands, and the aggregate comparison.\n\n"
        "To use the plots in a paper, copy `aggregate-plots.tex`, `paper-figure.tex`,\n"
        "`plot-series.csv`, and `plot-curves.csv` from `plots/` into a `pomdp-plots/` folder in the paper project.\n"
        "For CSV-driven figures, load `pomdp-plots/aggregate-plots.tex` in the paper preamble,\n"
        "call `\\StormPOMDPLoadAggregateData{pomdp-plots}`, and insert `\\input{pomdp-plots/paper-figure.tex}` in the body.\n"
        "Compile twice for the shared legend; Python and pre-rendered images are not needed in the paper project.\n\n"
        "Every run builds `plots/runtime-comparison.pdf` and `.png` with all three panels.\n"
        "The panels sit side by side at LNCS text width (12.2 cm), with 6 pt lettering.\n"
        "All plot panels cover the included instances together. Each point is a separate run.\n"
        "All panels use the configured size limit on the x-axis and separate solid TO and MO lines.\n"
        "For plotting, killed runs are treated as MO and use their benchmark's normal colour and marker.\n"
        "Measured runtimes remain in the CSV; other failures get a Failed line when present.\n"
        "The bound panels show gaps to the best successful under- and over-approximation per instance.\n"
        "Gap: 100 * abs(bound-best) / max(abs(bound), abs(best)).\n"
        "The under-reference panel shows deviation from the best observed cut-off bound.\n"
        "The over-reference panel uses only belief discretisation at resolutions 4 and 5.\n"
        "It shows the relative interval width between approximation bounds.\n",
        encoding="utf-8",
    )
    print(f"Generated results for {len(instances)} instances in {root}")


if __name__ == "__main__":
    main()
