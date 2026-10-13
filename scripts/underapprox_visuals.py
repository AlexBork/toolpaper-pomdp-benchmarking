"""Question-specific under-approximation tables and standalone PGFPlots snippets."""
import math
import os


EXAMPLE_IDS = (
    "grid-avoid_grid-avoid_prbmax_sl0.1",
    "crypt4_crypt_prbmin_",
    "network3_network3_rewmin_T8-K20",
    "network-priorities2_network-priorities2_rewmax_T8-K20",
)
THRESHOLDS = (8, 16, 24, 32)
RESOLUTION_THRESHOLDS = (8, 10, 12, 16)
MATCHED_THRESHOLD = 12
SERIES = (
    ("cut", None, "plotcut", "o", r"\config{cut}"),
    ("clip", 2, "plotclip", "triangle", r"\config{clip}, $\eta=2$"),
    ("clip", 3, "plotdiscr", "square", r"\config{clip}, $\eta=3$"),
    ("clip", 4, "orange", "diamond", r"\config{clip}, $\eta=4$"),
)


def save_outputs(p, execution, instances, timelimit=1800):
    """Use existing result formatting and precision from the postprocessor."""
    root = os.path.join(p.GENERAL_PLOT_DIR, "underapprox")
    included = [b for b in p.benchmarks.INSTANCES if b["id"] in instances]
    examples = [b for b in included if b["id"] in EXAMPLE_IDS]

    def config(family, exponent, resolution=None):
        return f"cut{exponent:02}" if family == "cut" else f"clip{exponent:02}res{resolution:02}"

    def result(inst_id, family, exponent, resolution=None):
        return p.get_result(execution, p.storm.NAME, config(family, exponent, resolution), inst_id)

    def successful(run):
        return p.is_successful_result(run, timelimit)

    def status(run):
        return "successful" if successful(run) else "not-run" if run is None else "failed"

    def metric(run, name):
        if not successful(run):
            return None
        if name == "bound":
            return p.parse_result_value(run["result"])[1]
        if name == "time":
            return run["wallclock-time"]
        return run.get("belief-mdp", {}).get("states")

    def write(relative, text, question, placement):
        path = os.path.join(root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as output:
            output.write(f"% {question} | {placement}. Explanations belong in the preview.\n")
            output.write(p.style_latex_plot(text))
        with open(path) as plot_file:
            return plot_file.read()

    def plot_series(table, color, mark, legend=None):
        text = (r"\addplot[only marks," + ("forget plot," if legend else "") + "color=" + color + ",mark=" + mark
                + r",mark options={fill=none},mark size=1.5pt,line width=0.4pt] table[x=x,y=y,col sep=space,row sep=\\]{"
                + p.latex_plot_table(table) + "};\n")
        if not any(row[1] not in (None, "nan") for row in table[1:]):
            text = ""
        if legend:
            text += (r"\addlegendimage{only marks,color=" + color + ",mark=" + mark
                     + r",mark options={fill=none},mark size=1.5pt,line width=0.4pt}" + "\n"
                     + r"\addlegendentry{" + legend + "}\n")
        return text

    def axis_plot(options, body):
        return (r"\begin{tikzpicture}\begin{axis}[" + options + "]\n"
                + body + r"\end{axis}\end{tikzpicture}" + "\n")

    def legend_plot(entries, columns=2):
        body = [r"\begin{tikzpicture}\begin{axis}[hide axis,scale only axis,width=0pt,height=0pt,xmin=0,xmax=1,ymin=0,ymax=1,"
                + f"legend columns={columns},legend style={{draw=black,at={{(0,0)}},anchor=center}}]" + "\n"]
        for image_options, label in entries:
            body.append(r"\addlegendimage{" + image_options + "}\n"
                        + r"\addlegendentry{" + label + "}\n")
        body.append(r"\end{axis}\end{tikzpicture}" + "\n")
        return "".join(body)

    # Export raw observations for auditing; plots embed the relevant data.
    observations = [["instance", "method", "exponent", "resolution", "bound", "time", "states", "status"]]
    for benchmark in included:
        for family, resolution, *_ in SERIES:
            for exponent in (0, *range(8, 33)):
                run = result(benchmark["id"], family, exponent, resolution)
                observations.append([benchmark["id"], family, exponent,
                                     resolution if resolution else "none",
                                     *[metric(run, name) if metric(run, name) is not None else "nan"
                                       for name in ("bound", "time", "states")], status(run)])
    p.save_csv(observations, os.path.join(p.OUT_DIR, "underapprox_observations.csv"))

    # Per-instance parameter plots: raw bounds avoid mixing objective scales.
    appendix = {"threshold": [], "resolution": []}
    for kind in appendix:
        for benchmark in included:
            inst_id = benchmark["id"]
            placement = "MAIN CANDIDATE" if inst_id in EXAMPLE_IDS else "APPENDIX"
            for name in ("bound", "time"):
                options = "ymode=log,ylabel={Runtime (s)}," if name == "time" else "ylabel={Under-approximation bound},scaled y ticks=false,"
                observed = []
                if kind == "threshold":
                    options += r"xmin=7.5,xmax=32.5,xtick={8,12,16,20,24,28,32},xticklabels={$2^{8}$,$2^{12}$,$2^{16}$,$2^{20}$,$2^{24}$,$2^{28}$,$2^{32}$},xlabel={Exploration threshold $\tau$},"
                    axis_series = []
                    for family, resolution, color, mark, legend in SERIES:
                        table = [["x", "y"]]
                        for exponent in range(8, 33):
                            value = metric(result(inst_id, family, exponent, resolution), name)
                            if value is not None:
                                observed.append(value)
                            table.append([exponent, value if value is not None else "nan"])
                        axis_series.append(plot_series(table, color, mark, legend))
                    legends = "legend columns=2,"
                else:
                    options += r"xmin=1.7,xmax=4.3,xtick={2,3,4},xlabel={Clipping resolution $\eta$},"
                    axis_series = []
                    for exponent, color, mark in zip(RESOLUTION_THRESHOLDS, ("plotcut", "plotclip", "plotdiscr", "orange"), ("o", "triangle", "square", "diamond")):
                        table = [["x", "y"]]
                        for resolution in (2, 3, 4):
                            value = metric(result(inst_id, "clip", exponent, resolution), name)
                            if value is not None:
                                observed.append(value)
                            table.append([resolution, value if value is not None else "nan"])
                        axis_series.append(plot_series(table, color, mark, rf"$\tau=2^{{{exponent}}}$"))
                    legends = "legend columns=4,"
                if not observed:
                    options += "axis y line=none,ytick=\\empty,ymin=0.1,ymax=1,"
                    axis_series.append(r"\node[font=\small] at (rel axis cs:0.5,0.5) {No successful runs};" + "\n")
                elif name == "bound" and p.comparison_value(min(observed)) == p.comparison_value(max(observed)):
                    centre = observed[0]
                    span = max(abs(centre) * 0.05, 0.01)
                    options += f"ymin={centre-span},ymax={centre+span},"
                plot = (r"\begin{tikzpicture}\begin{axis}[width=7cm,height=4.5cm,unbounded coords=jump,"
                        + legends + options + r"title={\texttt{\detokenize{" + inst_id
                        + r"}}},title style={font=\tiny,yshift=35pt}]" + "\n"
                        + "".join(axis_series) + r"\end{axis}\end{tikzpicture}" + "\n")
                filename = f"{kind}_{name}-{inst_id}.tex"
                write(f"{kind}/{filename}", plot, "UA1" if kind == "threshold" else "UA2", placement)
                if placement == "APPENDIX":
                    appendix[kind].append(filename)
        # Preview index only; every actual plot remains in its own file.
        with open(os.path.join(root, kind, f"{kind}_appendix_preview.tex"), "w") as output:
            output.write(f"% UA{'1' if kind == 'threshold' else '2'} | APPENDIX preview index.\n")
            for index, filename in enumerate(appendix[kind]):
                if index and index % 2 == 0:
                    output.write("\\clearpage\n")
                output.write(f"\\input{{general-plots/underapprox/{kind}/{filename}}}\\par\\medskip\n")

    # Experimental 3D view of the same threshold trade-off for Drone 4-2.
    drone_id = "drone_drone_prbmax_N4-R2"
    drone = next((benchmark for benchmark in included if benchmark["id"] == drone_id), None)
    if drone is not None:
        series_text, success_counts = [], []
        for family, resolution, color, mark, legend in SERIES:
            table = [["x", "y", "z"]]
            for exponent in range(8, 33):
                run = result(drone_id, family, exponent, resolution)
                bound, runtime = metric(run, "bound"), metric(run, "time")
                if bound is not None and runtime is not None and runtime > 0:
                    table.append([exponent, runtime, bound])
            success_counts.append((legend, len(table) - 1))
            if len(table) > 1:
                series_text.extend([
                    r"\addplot3[only marks,color=" + color + r",mark=" + mark
                    + r",mark options={fill=none},mark size=1.7pt,line width=0.45pt] "
                    + r"table[x=x,y=y,z=z,col sep=space,row sep=\\]{" + p.latex_plot_table(table) + "};\n",
                    r"\addlegendentry{" + legend + "}\n",
                ])
        count_text = ", ".join(f"{label}: {count}" for label, count in success_counts)
        options = (
            r"width=10.2cm,height=7.2cm,view={48}{24},axis lines=box,grid=major,z buffer=sort,"
            r"xmin=7.5,xmax=32.5,xtick={8,12,16,20,24,28,32},"
            r"xticklabels={$2^{8}$,$2^{12}$,$2^{16}$,$2^{20}$,$2^{24}$,$2^{28}$,$2^{32}$},"
            r"ymode=log,ymin=0.1,ymax=2000,ytick={0.1,1,10,100,1000},"
            r"yticklabels={$0.1\vphantom{10^{1}}$,$1\vphantom{10^{1}}$,$10\vphantom{10^{1}}$,$10^{2}$,$10^{3}$},"
            r"xlabel={Exploration threshold $\tau$},ylabel={Runtime (s)},zlabel={Under-approximation bound},"
            r"xticklabel style={font=\scriptsize},yticklabel style={font=\scriptsize},zticklabel style={font=\scriptsize},"
            r"x label style={font=\scriptsize},y label style={font=\scriptsize},z label style={font=\scriptsize},"
            r"legend columns=2,legend style={at={(0.5,1)},anchor=south,nodes={scale=0.75,transform shape}},"
            r"title={Drone 4-2},title style={font=\small},"
        )
        write("threshold-3d/drone-4-2.tex", axis_plot(options, "".join(series_text)), "UA1", "EXPERIMENTAL")
        with open(os.path.join(root, "threshold-3d", "preview.tex"), "w") as output:
            output.write("% UA1 | EXPERIMENTAL: 3D threshold trade-off.\n")
            output.write("\\input{general-plots/underapprox/threshold-3d/drone-4-2.tex}\n")
            output.write("% Successful points per series: " + count_text + ".\n")

    # Shared run-outcome panels; resolution sweeps use subsets of these same runs.
    coverage = [["method", "exponent", "successful", "failed", "not-run"]]
    outcome_preview = ["% Preview index: separate panel and legend files.\n",
                       "\\input{general-plots/underapprox/threshold/run-outcomes/legend.tex}\\par\\medskip\n"]
    outcome_options = (r"width=\linewidth,height=4.3cm,xmin=7.5,xmax=32.5,"
                       + r"xtick={8,16,24,32},xticklabels={$2^{8}$,$2^{16}$,$2^{24}$,$2^{32}$},xlabel={Exploration threshold $\tau$},ylabel={Instances},"
                       + f"ymin=0,ymax={len(included)},ytick={{0,20,{len(included)}}},"
                       + r"title style={font=\small,yshift=20pt},legend columns=2,")
    for series_index, (family, resolution, _, _, legend) in enumerate(SERIES):
        table = [["x", "successful", "failed", "not-run"]]
        for exponent in range(8, 33):
            counts = p.Counter(status(result(b["id"], family, exponent, resolution)) for b in included)
            table.append([exponent, counts["successful"], counts["failed"], counts["not-run"]])
            coverage.append([family + (str(resolution) if resolution else ""), *table[-1]])
        no_legend, with_legend = [], []
        for column, color in [("successful", "plotsuccess!65"), ("failed", "orange!75"), ("not-run", "black!20")]:
            if column == "not-run" and not any(row[3] for row in table[1:]):
                continue
            series_text = (r"\addplot[fill=" + color + r",draw=none] table[x=x,y=" + column
                           + r",col sep=space,row sep=\\]{" + p.latex_plot_table(table) + "};\n")
            no_legend.append(series_text)
            with_legend.extend([series_text, r"\addlegendentry{" + column + "}\n"])
        slug = family if resolution is None else f"{family}-resolution-{resolution}"
        options = outcome_options + r"ybar stacked,bar width=2pt,title={" + legend + "},"
        prefix = r"\definecolor{plotsuccess}{RGB}{87,171,39}" + "\n"
        write(f"threshold/run-outcomes/{slug}.tex", prefix + axis_plot(options, "".join(with_legend)), "UA1/UA2", "MAIN: run outcomes")
        write(f"threshold/run-outcomes/{slug}-no-legend.tex", prefix + axis_plot(options, "".join(no_legend)), "UA1/UA2", "MAIN: run outcomes")
        outcome_preview.append("\\begin{minipage}{0.46\\linewidth}\\centering\n"
                               + f"\\input{{general-plots/underapprox/threshold/run-outcomes/{slug}-no-legend.tex}}\n"
                               + "\\end{minipage}"
                               + ("\\hfill\n" if series_index % 2 == 0 else "\\par\\medskip\n"))
    write("threshold/run-outcomes/legend.tex",
          r"\definecolor{plotsuccess}{RGB}{87,171,39}" + "\n" + legend_plot([
              ("area legend,fill=plotsuccess!65,draw=none", "successful"),
              ("area legend,fill=orange!75,draw=none", "failed"),
          ]), "UA1/UA2", "MAIN: run-outcome legend")
    with open(os.path.join(root, "threshold", "run-outcomes", "preview.tex"), "w") as preview:
        preview.writelines(outcome_preview)
    p.save_csv(coverage, os.path.join(p.OUT_DIR, "underapprox_run_outcomes.csv"))

    # Compact example tables, rather than reinstating full configuration tables.
    def table_model(benchmark):
        return p.dissertation_model(instances[benchmark["id"]])

    def table_objective(benchmark):
        return p.dissertation_property(instances[benchmark["id"]])

    threshold_rows = [[]]
    resolution_rows = [[]]
    for benchmark in examples:
        threshold_rows.append([table_model(benchmark), table_objective(benchmark),
                               *[p.underapproximation_summary_cell(execution, benchmark["id"], config(family, exponent, resolution))
                                 for exponent in THRESHOLDS
                                 for family, resolution in (("cut", None), ("clip", 2))]])
        for exponent in RESOLUTION_THRESHOLDS:
            resolution_rows.append([table_model(benchmark), table_objective(benchmark), rf"$2^{{{exponent}}}$",
                                    *[p.underapproximation_summary_cell(execution, benchmark["id"], config("clip", exponent, resolution)) for resolution in (2, 3, 4)]])
    model_columns = p.fixed_latex_column("center", "14mm") + r"@{\hspace{0.5pt}}" + p.fixed_latex_column("center", "9mm")
    threshold_header = (
        r"\multirow{2}{*}{Model} & \multirow{2}{*}{Obj.} & "
        + " & ".join(rf"\multicolumn{{2}}{{c{'|' if index < len(THRESHOLDS) - 1 else ''}}}{{$\tau=2^{{{k}}}$}}"
                     for index, k in enumerate(THRESHOLDS))
        + r"\\" + "\n"
        + " ".join(rf"\cmidrule(lr){{{3 + 2 * index}-{4 + 2 * index}}}" for index in range(len(THRESHOLDS)))
        + "\n & & " + " & ".join([r"\config{cut}", r"\config{clip}"] * len(THRESHOLDS))
    )
    threshold_columns = model_columns + (
        " | " + p.fixed_latex_column("right", "11mm") + " " + p.fixed_latex_column("right", "11mm")
    ) * len(THRESHOLDS)
    resolution_columns = model_columns + " | " + p.fixed_latex_column("center", "10mm") + (
        " | " + p.fixed_latex_column("right", "26mm")
    ) * 3
    for filename, rows, colspec, header, question in [
        ("tableunderapproxthreshold-examples.tex", threshold_rows, threshold_columns, threshold_header, "UA1"),
        ("tableunderapproxresolution-examples.tex", resolution_rows, resolution_columns, r"Model & Obj. & $\tau$ & " + " & ".join(rf"$\eta={r}$" for r in (2, 3, 4)), "UA2"),
    ]:
        path = os.path.join(p.UNDERAPPROX_TABLE_DIR, filename)
        p.save_latex(rows, colspec, header, path, grid=True, tabcolsep="1pt", alternating_rows=True, arraystretch="0.9")
        with open(path) as table_file:
            table = table_file.read()
        with open(path, "w") as table_file:
            table_file.write("% UA1 | MAIN: threshold examples (CLIP resolution 2).\n" if question == "UA1" else "% UA2 | MAIN: fixed-threshold clipping examples.\n")
            table_file.write(table)

    # Compare both matched explicit settings and separately tuned results.
    comparisons = [["instance", "comparison", "cut-config", "clip-config", "cut-bound", "clip-bound", "cut-time", "clip-time", "cut-states", "clip-states", "status"]]
    for comparison in ("matched", "tightest"):
        pairs = []
        for benchmark in included:
            inst_id = benchmark["id"]
            if comparison == "matched":
                cut, clip = result(inst_id, "cut", MATCHED_THRESHOLD), result(inst_id, "clip", MATCHED_THRESHOLD, 2)
            else:
                cut = p.get_result(execution, p.storm.NAME, f"cut-best-in-{timelimit}s", inst_id)
                clip = p.get_result(execution, p.storm.NAME, f"clip-best-in-{timelimit}s", inst_id)
            pairs.append((benchmark, cut, clip))
            state = "paired" if successful(cut) and successful(clip) else "cut-only" if successful(cut) else "clip-only" if successful(clip) else "neither"
            comparisons.append([inst_id, comparison, cut.get("configuration-id", "none") if cut else "none",
                                clip.get("configuration-id", "none") if clip else "none",
                                *[metric(run, name) if metric(run, name) is not None else "nan"
                                  for name in ("bound", "time", "states") for run in (cut, clip)], state])
        for name in ("bound", "time", "states"):
            if name == "bound":
                groups = [(kind, direction) for kind in ("prb", "rew") for direction in ("min", "max")]
            else:
                groups = [(None, None)]
            preview_inputs = ["% Preview index: every panel is stored separately.\n"]
            for kind, direction in groups:
                group = [(b, cut, clip) for b, cut, clip in pairs if kind is None or (b["property"]["type"] == kind and b["property"]["dir"] == direction)]
                numeric = [metric(run, name) for _, cut, clip in group for run in (cut, clip) if metric(run, name) is not None]
                logarithmic = name != "bound" or kind == "rew"
                if logarithmic:
                    lower = 0.1 if name == "time" else (10 ** math.floor(math.log10(min(v for v in numeric if v > 0))) if numeric else 1)
                    upper = max(lower * 10, 10 ** math.ceil(math.log10(max(numeric)))) if numeric else lower * 10
                    if name == "time":
                        upper = 10000  # First full decade above the 1,800-second limit.
                    failure, xmax = p.scatter_na_limits(lower, upper, logarithmic=True)
                    options = f"xmode=log,ymode=log,xmin={lower},ymin={lower},xmax={xmax},ymax={xmax},"
                    options += p.scatter_log_ticks(lower, upper, failure)
                else:
                    lower, upper = 0, 1
                    failure, xmax = p.scatter_na_limits(lower, upper)
                    ticks, labels = [0, 0.25, 0.5, 0.75, 1, failure], ["0", "0.25", "0.5", "0.75", "1", "n/a"]
                    options = f"xmin=0,ymin=0,xmax={xmax},ymax={xmax},"
                    options += "xtick={" + ",".join(map(str, ticks)) + "},ytick={" + ",".join(map(str, ticks)) + "},xticklabels={" + ",".join(labels) + "},yticklabels={" + ",".join(labels) + "},"
                boundary = upper
                options += r"xticklabel style={font=\footnotesize},yticklabel style={font=\footnotesize},"
                title = ("Probability" if kind == "prb" else "Reward") + (" min." if direction == "min" else " max.") if kind else ("Runtime (s)" if name == "time" else "Constructed MDP states")
                panel = []
                for guide in [f"({boundary},{lower}) ({boundary},{xmax})", f"({lower},{boundary}) ({xmax},{boundary})"]:
                    panel.append(r"\addplot[black!35,thin,no marks,forget plot] coordinates {" + guide + "};\n")
                panel.append(r"\addplot[black,thin,no marks,forget plot] coordinates {" + f"({lower},{lower}) ({boundary},{boundary})" + "};\n")
                if logarithmic:
                    for guide in [f"({lower},{lower*2}) ({boundary/2},{boundary})", f"({lower*2},{lower}) ({boundary},{boundary/2})"]:
                        panel.append(r"\addplot[black,densely dotted,thin,no marks,forget plot] coordinates {" + guide + "};\n")
                series = []
                for property_type, color, mark in [("prb", "plotdiscr", "o"), ("rew", "plotclip", "triangle")]:
                    table = [["x", "y"]]
                    for benchmark, cut, clip in group:
                        if benchmark["property"]["type"] != property_type:
                            continue
                        values = [metric(run, name) for run in (cut, clip)]
                        table.append([failure if value is None else max(lower, value) for value in values])
                    text = plot_series(table, color, mark)
                    if text:
                        series.append((property_type, text))
                no_legend = "".join(panel) + "".join(text for _, text in series)
                with_legend = "".join(panel)
                for property_type, text in series:
                    with_legend += text + r"\addlegendentry{" + ("Probability" if property_type == "prb" else "Reward") + "}\n"
                axis_options = (p.LATEX_SCATTER_OPTIONS + r"xlabel={\config{cut}},ylabel={\config{clip}},title style={font=\small},"
                                + r"title={" + title + "}," + options)
                if name == "bound":
                    slug = f"bound-{'probability' if kind == 'prb' else 'reward'}-{direction}"
                else:
                    slug = name
                placement = "MAIN: matched settings" if comparison == "matched" else "APPENDIX: tuned comparison"
                write(f"comparison/{comparison}/{slug}.tex", axis_plot(axis_options, with_legend), "UA3", placement)
                if len(series) > 1:
                    write(f"comparison/{comparison}/{slug}-no-legend.tex", axis_plot(axis_options, no_legend), "UA3", placement)
                    plot_input = f"\\input{{general-plots/underapprox/comparison/{comparison}/{slug}-no-legend.tex}}\n"
                else:
                    plot_input = f"\\input{{general-plots/underapprox/comparison/{comparison}/{slug}.tex}}\n"
                if name == "bound":
                    preview_inputs.append("\\begin{minipage}{0.46\\linewidth}\\centering\n"
                                          + plot_input + "\\end{minipage}"
                                          + ("\\hfill\n" if len(preview_inputs) % 2 == 1 else "\\par\\medskip\n"))
                else:
                    preview_inputs.append(plot_input)
            with open(os.path.join(root, "comparison", comparison, f"{name}-preview.tex"), "w") as preview:
                preview.writelines(preview_inputs)
        write(f"comparison/{comparison}/legend.tex", legend_plot([
            ("only marks,color=plotdiscr,mark=o,mark options={fill=none},mark size=1.5pt", "Probability"),
            ("only marks,color=plotclip,mark=triangle,mark options={fill=none},mark size=1.5pt", "Reward"),
        ]), "UA3", "shared comparison legend")
    p.save_csv(comparisons, os.path.join(p.OUT_DIR, "underapprox_cut_clip_pairs.csv"))
