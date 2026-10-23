"""Portable HTML results and per-run log pages for the configured benchmark suite."""

from collections import Counter
import html
import json
import math
from pathlib import Path
import shutil
from urllib.parse import quote


def escape(value):
    return html.escape(str(value), quote=True)


def page(title, content, asset_prefix="", script=False):
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{asset_prefix}results.css">\n</head>\n'
        f"<body>\n{content}\n"
        + (f'<script src="{asset_prefix}results.js"></script>\n' if script else "")
        + "</body>\n</html>\n"
    )


def number(value):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return f"{value:,}"
    return "—"


def run_page(p, run, destination):
    """Copy escaped log contents, so the export remains usable without source logs."""
    status = "unsupported" if run.get("not-supported") else p.runtime_status(run)
    fields = [
        ("Benchmark", run["benchmark-id"]),
        ("Configuration", f"{run['tool']}.{run['configuration-id']}"),
        ("Status", status),
        ("Result", run.get("result", "unavailable")),
        ("Wall-clock time (s)", run.get("wallclock-time", "unavailable")),
        ("Time limit (s)", run.get("time-limit", "unavailable")),
        ("Return codes", json.dumps(run.get("return-codes", []))),
        ("Source log", run.get("log", "unavailable")),
    ]
    content = [
        '<p><a href="../index.html">← Results</a></p>',
        f'<h1>{escape(run["id"])}</h1>',
        "<dl>",
    ]
    content.extend(
        f"<dt>{escape(key)}</dt><dd>{escape(value)}</dd>" for key, value in fields
    )
    content.extend(
        [
            "</dl>",
            "<h2>Invocation</h2>",
            "<pre>" + escape("\n".join(run.get("commands", []))) + "</pre>",
            "<p>" + escape(run.get("invocation-note", "")) + "</p>",
            "<h2>Log</h2>",
        ]
    )
    source = Path(run["log"]) if run.get("log") else None
    if source is not None and source.is_file():
        content.append(
            "<pre>"
            + escape(source.read_text(encoding="utf-8", errors="replace"))
            + "</pre>"
        )
    else:
        content.append(
            '<p class="sub">Source log unavailable when this export was generated.</p>'
        )
    content.extend(
        [
            "<details><summary>Parsed run metadata</summary><pre>",
            escape(json.dumps(run, ensure_ascii=False, indent=2)),
            "</pre></details>",
        ]
    )
    destination.write_text(page(run["id"], "\n".join(content), "../"), encoding="utf-8")


def save_results(p, execution, instances, logdirs=(), output_dir=None):
    """Export actual configurations only; derived selections are not measured runs."""
    root = Path(output_dir) if output_dir is not None else Path(p.OUT_DIR) / "html"
    (root / "logs").mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).parent / "html_assets"
    for asset in ("results.css", "results.js"):
        shutil.copyfile(assets / asset, root / asset)
    configs = [(tool.NAME, cfg) for tool in p.TOOLS for cfg in tool.CONFIGS]
    selected_instances = [
        inst
        for inst in p.benchmarks.INSTANCES
        if inst["id"] in instances
        or any(
            p.get_result(execution, tool, cfg["id"], inst["id"]) is not None
            for tool, cfg in configs
        )
    ]
    runs = [
        run
        for tool, cfg in configs
        for inst in selected_instances
        if (run := p.get_result(execution, tool, cfg["id"], inst["id"])) is not None
    ]
    statuses = Counter(
        "unsupported" if run.get("not-supported") else p.runtime_status(run)
        for run in runs
    )
    seconds = math.fsum(run.get("wallclock-time", 0) for run in runs)
    content = [
        "<h1>Storm-POMDP benchmark results</h1>",
        '<p class="sub">Each measured run links to its invocation and log. '
        "Click a column header to sort; use the buttons to show or hide configurations.</p>",
        f'<p class="sub">{len(selected_instances)} instances · {len(configs)} configurations · '
        f"{len(runs)} recorded runs · cumulative runtime: {escape(p.runtime_duration(seconds))}. "
        + ", ".join(
            f"{count} {escape(status)}" for status, count in sorted(statuses.items())
        )
        + ".</p>",
    ]
    if logdirs:
        content.append(
            '<p class="sub">Sources: ' + ", ".join(escape(d) for d in logdirs) + ".</p>"
        )
    content.extend(
        [
            '<p class="sub">Green marks the tightest successful bound among visible configurations, '
            "comparing cut-offs separately from discretisation. Bounds are compared at six "
            "decimal places; runtime breaks ties. For maximisation, larger cut-off bounds and smaller "
            "discretisation bounds are better; minimisation reverses these directions. "
            "Marking is the same in every display view. Killed means SIGKILL without a recorded timeout.</p>",
            '<div class="controls"><label>Filter benchmarks <input id="filter" type="search" '
            'placeholder="Name, parameters, or objective"></label> '
            '<label>Cell display <select id="metric"><option value="both">Bound &amp; runtime</option>'
            '<option value="runtime">Runtime (s)</option><option value="bound">Bound</option></select></label> '
            '<span id="row-count" role="status"></span></div>',
            '<div id="columns" class="controls" aria-label="Visible configurations">'
            '<button type="button" data-all="true">Show all</button> '
            '<button type="button" data-all="false">Hide all</button>',
        ]
    )
    for family in dict.fromkeys(cfg.get("family", tool) for tool, cfg in configs):
        content.append(f'<span class="family">{escape(family)}:</span>')
        for tool, cfg in configs:
            if cfg.get("family", tool) != family:
                continue
            key = f"{tool}.{cfg['id']}"
            content.append(
                f'<button type="button" class="toggle on" data-col="{escape(key)}" '
                f'aria-pressed="true" title="{escape("; ".join(cfg.get("notes", [])))}">'
                f'{escape(cfg["id"])}</button>'
            )
    content.extend(
        [
            "</div>",
            '<div class="table-scroll"><table id="results">',
            "<caption>Bounds and recorded wall-clock runtimes in seconds. "
            "Configuration columns sort by runtime, or by value in Bound view; "
            "unsuccessful and missing results stay last.</caption>",
            "<thead><tr>",
        ]
    )
    metadata = [
        ("benchmark", "text"),
        ("objective", "text"),
        ("states", "number"),
        ("choices", "number"),
        ("observations", "number"),
    ]
    for label, kind in metadata:
        content.append(
            f'<th scope="col" data-kind="{kind}"><button type="button" '
            f'class="sort">{label}</button></th>'
        )
    for tool, cfg in configs:
        content.append(
            f'<th scope="col" data-kind="run" data-col="{escape(tool + "." + cfg["id"])}" '
            f'title="{escape("; ".join(cfg.get("notes", [])))}">'
            f'<button type="button" class="sort">{escape(cfg["id"])}</button></th>'
        )
    content.append("</tr></thead>\n<tbody>")
    log_count = 0
    for inst in selected_instances:
        inst_id = inst["id"]
        # Runs can fail before model statistics are printed.
        data = instances.get(
            inst_id,
            {
                "name": inst.get("name", inst_id),
                "par": ",".join(
                    f"{key}={value}"
                    for key, value in inst.get("model", {})
                    .get("open-parameters", {})
                    .items()
                ),
                "property": inst["property"]["type"],
                "property-dir": inst["property"]["dir"],
            },
        )
        name = data.get("name", inst_id)
        if data.get("par"):
            name += "/" + str(data["par"])
        objective = f'{data.get("property", "?")} {data.get("property-dir", "?")}'
        content.append(
            f'<tr data-direction="{escape(inst["property"]["dir"])}" '
            f'data-search="{escape((inst_id + " " + name + " " + objective).lower())}">'
        )
        for label, kind in metadata:
            value = (
                name
                if label == "benchmark"
                else objective if label == "objective" else data.get(label)
            )
            display = number(value) if kind == "number" else value
            sort_value = value if value is not None else ""
            content.append(
                f'<td data-sort="{escape(sort_value)}" title="{escape(inst_id)}">'
                f"{escape(display)}</td>"
            )
        for tool, cfg in configs:
            key = f"{tool}.{cfg['id']}"
            run = p.get_result(execution, tool, cfg["id"], inst_id)
            status = (
                "missing"
                if run is None
                else (
                    "unsupported" if run.get("not-supported") else p.runtime_status(run)
                )
            )
            successful = status == "successful"
            runtime = run.get("wallclock-time") if run else None
            relation, value = (
                p.parse_result_value(run["result"]) if successful else ("", "")
            )
            attributes = (
                f'class="run {status}" data-col="{escape(key)}" '
                f'data-family="{escape(cfg.get("family", tool))}" '
                f'data-status="{status}" data-runtime="{escape(runtime if runtime is not None else "")}" '
                f'data-bound="{escape(value)}" data-relation="{escape(relation)}" '
                f'data-quality="{escape(p.comparison_value(value) if successful else "")}"'
            )
            content.append(f"<td {attributes}>")
            if run is None:
                content.append('<span title="No recorded run">missing</span>')
            else:
                filename = quote(f"{key}.{inst_id}", safe="") + ".html"
                run_page(p, run, root / "logs" / filename)
                log_count += 1
                bound = run["result"] if successful else status
                if (
                    successful
                    and relation == "="
                    and not bound.lstrip().startswith("=")
                ):
                    bound = "= " + bound
                duration = f"{runtime:.2f}" if runtime is not None else "—"
                title = f'{status}; result: {run.get("result", "unavailable")}; wall-clock: {runtime}s'
                content.append(
                    f'<a href="logs/{escape(quote(filename))}" title="{escape(title)}">'
                    f'<span class="bound">{escape(bound)}</span> '
                    f'<span class="runtime">({duration}s)</span></a>'
                )
            content.append("</td>")
        content.append("</tr>")
    content.extend(["</tbody></table></div>"])
    (root / "index.html").write_text(
        page("Storm-POMDP results", "\n".join(content), script=True), encoding="utf-8"
    )
    print(f"Generated {root}/index.html and {log_count} run pages.")
