import sys, os, json, csv, copy, math, re, itertools, html, argparse, shlex

from collections import Counter, OrderedDict
import benchmarks
from tools import *

OUT_DIR = "data"
TABLE_DIR = os.path.join(OUT_DIR, "tables-general")
GENERAL_PLOT_DIR = os.path.join(OUT_DIR, "general-plots")
RESOLUTION_VALUE_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "resolution-value")
RESOLUTION_TIME_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "resolution-time")
TIME_RESULT_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "time-result")
OVERAPPROX_TABLE_DIR = os.path.join(TABLE_DIR, "overapprox")
UNDERAPPROX_TABLE_DIR = os.path.join(TABLE_DIR, "underapprox")
LATEX_TABLE_FONT_SIZE = "scriptsize"
RESULT_COMPARISON_DECIMALS = 6
LATEX_HIGHLIGHT_COLOR = "RWTHblue25"
LATEX_SHADED_HIGHLIGHT_COLOR = "RWTHblue25!80!gray"

LATEX_MODEL_ABBREVIATIONS = {
    "grid-avoid": "grid-av",
    "grid-large-30-5": "grid-l",
    "samplerocks": "rocks",
    "network-priorities2": "netw-p2",
    "network-priorities3": "netw-p3",
    "lanes-100": "lanes",
    "network2": "netw2",
    "network3": "netw3",
}

def strip_benchmark_set_prefix(inst_id):
    return inst_id.split("_", 1)[1] if "_" in inst_id else inst_id

def load_json(path : str):
    with open(path, 'r', encoding='utf-8-sig') as json_file:
        return json.load(json_file, object_pairs_hook=OrderedDict)

def save_json(json_data, path : str):
    with open(path, 'w') as json_file:
        json.dump(json_data, json_file, ensure_ascii=False, indent='\t')

def load_csv(path : str, delim='\t'):
    with open(path, 'r') as csv_file:
        return list(csv.reader(csv_file, delimiter=delim))

def save_csv(csv_data, path : str, delim='\t'):
    with open(path, 'w') as csv_file:
        writer = csv.writer(csv_file, delimiter=delim)
        writer.writerows(csv_data)

def latex_plot_table(table):
    """Format inline PGFPlots data with explicit row separators."""
    return "\n" + "\n".join(
        " ".join("nan" if value == "" else str(value) for value in row) + r" \\"
        for row in table
    ) + "\n"


def embed_plot_data(plot, tables):
    """Replace CSV table references with the data used to generate them."""
    def replace_table(match):
        options, filename = match.groups()
        options = re.sub(r"col sep=tab", "col sep=space", options)
        return "table[" + options + r",row sep=\\]{" + latex_plot_table(tables[filename]) + "}"

    return style_latex_plot(re.sub(r"table\s*\[([^\]]*)\]\s*\{([^{}]+\.csv)\}", replace_table, plot))


# Match the PGFPlots appearance of storm-rew-bounded-benchmarking.
LATEX_PLOT_BEGIN = r"""% Preamble requires \usepackage{pgfplots} and \pgfplotsset{compat=1.18}.
\begingroup
\providecommand{\config}[1]{\textsc{#1}}
\definecolor{plotcut}{cmyk}{0.35,0,1,0}
\definecolor{plotclip}{cmyk}{0.25,1,0.7,0.2}
\definecolor{plotdiscr}{cmyk}{1,0.5,0,0}
"""
LATEX_PLOT_OPTIONS = r"""axis x line=bottom,axis y line=left,
filter discard warning=false,
x label style={font=\small,yshift=4pt},y label style={font=\small,yshift=-2pt},
yticklabel style={font=\small},xticklabel style={font=\small},
legend columns=-1,legend cell align=left,
legend style={at={(0.5,1)},anchor=south,yshift=4pt,
    nodes={scale=0.75,transform shape},inner sep=1pt},
/pgfplots/legend image code/.code={\draw[mark repeat=2,mark phase=2,#1] plot coordinates {(0cm,0cm) (0.3cm,0cm)};},
every axis plot/.append style={thick},
"""
# Square comparison panels, following Figures 3 and 6 of arXiv:2301.10197.
LATEX_SCATTER_OPTIONS = r"""scale only axis,
width=\linewidth,height=\linewidth,
grid=major,major grid style={draw=black!20,line width=0.25pt},
tick align=outside,tick style={line width=0.3pt},
xticklabel style={font=\footnotesize},yticklabel style={font=\footnotesize},
axis line style={line width=0.4pt},
every axis plot/.append style={thin},
x label style={font=\small,yshift=0pt},y label style={font=\small,yshift=0pt},
legend style={draw=black,fill=white,line width=0.3pt},
/pgfplots/legend image code/.code={\draw[#1] plot coordinates {(0.15cm,0cm)};},
"""
LATEX_INSTANCE_PLOT_OPTIONS = "width=4.5cm,height=4.5cm,\n" + LATEX_PLOT_OPTIONS
LATEX_INSTANCE_PLOT_END = r"""\end{axis}
\end{tikzpicture}
"""


def scatter_log_minor_ticks(lower, numeric_end, major_ticks=()):
    """Keep base-ten subdivisions throughout the numeric region, outside N/A."""
    ticks = []
    for exponent in range(math.floor(math.log10(lower)), math.ceil(math.log10(numeric_end)) + 1):
        for multiplier in range(1, 10):
            value = multiplier * 10 ** exponent
            if lower < value < numeric_end and not any(
                math.isclose(value, major) for major in major_ticks
            ):
                ticks.append(f"{value:g}")
    positions = ",".join(ticks)
    return f"minor xtick={{{positions}}},minor ytick={{{positions}}},"


def scatter_log_ticks(lower, upper, failure=None):
    """Label every decade and reserve an unticked strip for unavailable values."""
    exponents = range(round(math.log10(lower)), round(math.log10(upper)) + 1)
    ticks = [10 ** exponent for exponent in exponents]
    labels = [
        {
            -1: r"$0.1\vphantom{10^{1}}$",
            0: r"$1\vphantom{10^{1}}$",
            1: r"$10\vphantom{10^{1}}$",
        }.get(exponent, rf"$10^{{{exponent}}}$")
        for exponent in exponents
    ]
    options = scatter_log_minor_ticks(lower, upper, ticks)
    if failure is not None:
        ticks.append(failure)
        labels.append("n/a")
    for axis in ("x", "y"):
        options += "".join((axis, "tick={", ",".join(map(str, ticks)), "},",
                            axis, "ticklabels={", ",".join(labels), "},"))
    return options


def scatter_na_limits(lower, upper, logarithmic=False, gap_fraction=0.10):
    """Place N/A beyond the numeric boundary by a configurable panel fraction."""
    padding_fraction = 0.03
    numeric_fraction = 1 - gap_fraction - padding_fraction
    if logarithmic:
        span = math.log10(upper / lower) / numeric_fraction
        return (upper * 10 ** (gap_fraction * span),
                upper * 10 ** ((gap_fraction + padding_fraction) * span))
    span = (upper - lower) / numeric_fraction
    return (upper + gap_fraction * span,
            upper + (gap_fraction + padding_fraction) * span)


def style_latex_plot(plot):
    for old, new in [("RWTHmaygreen", "plotcut"), ("RWTHbordeaux", "plotclip"), ("RWTHblue", "plotdiscr")]:
        plot = plot.replace(old, new)
    for environment in ("axis", "groupplot"):
        plot = re.sub(r"\\begin\{" + environment + r"\}\[\s*", lambda match: r"\begin{" + environment + "}[" + "\n" + LATEX_PLOT_OPTIONS, plot)
    return LATEX_PLOT_BEGIN + plot + r"\endgroup" + "\n"


def save_html(table_data, num_tool_configs, path):
    SHOW_UNSUPPORTED = True # Also add entries for benchmarks that are known to be unsupported
    LOGS_SUBDIR = "logs"
    if not os.path.exists(os.path.join(path, LOGS_SUBDIR)): os.makedirs(os.path.join(path, LOGS_SUBDIR))

    # Aux function for writing in files with proper indention
    def write_line(file, indention, content):
        file.write("\t"*indention + content + "\n")

    # Generates an html log page for the given result within path/LOGS_SUBDIR/
    def create_log_page(result_json):
        with open(result_json["log"], 'r') as logfile:
            log = logfile.read()
        f_path = os.path.join(LOGS_SUBDIR, os.path.basename(result_json["log"])[:-4] + ".html")
        with open(os.path.join(path, f_path), 'w') as f:
            indention = 0
            write_line(f, indention, "<!DOCTYPE html>")
            write_line(f, indention, "<html>")
            write_line(f, indention, "<head>")
            indention += 1
            write_line(f, indention, '<meta charset="UTF-8">')
            write_line(f, indention, "<title>{}.{} - {}</title>".format(result_json["tool"], result_json["configuration-id"], result_json["benchmark-id"]))
            write_line(f, indention, '<link rel="stylesheet" type="text/css" href=../style.css>')
            indention -= 1
            write_line(f, indention, '</head>')
            write_line(f, indention, '<body>')
            write_line(f, indention, '<h1>{}.{}</h1>'.format(result_json["tool"],result_json["configuration-id"]))

            write_line(f, indention, '<div class="box">')
            indention += 1
            write_line(f, indention, '<div class="boxlabelo"><div class="boxlabelc">Benchmark</div></div>')
            write_line(f, indention, '<table style="margin-bottom: 0.75ex;">')
            indention += 1
            write_line(f, indention, '<tr><td>id:</td><td>{} ({})</td></tr>'.format(result_json["benchmark-id"], result_json["benchmark"]["model"]["type"].upper()))
            indention -= 1
            write_line(f, indention, "</table>")
            indention -= 1
            write_line(f, indention, "</div>")

            write_line(f, indention, '<div class="box">')
            indention += 1
            write_line(f, indention, '<div class="boxlabelo"><div class="boxlabelc">Invocation ({})</div></div>'.format(result_json["configuration-id"]))
            f.write('\t' * indention + '<pre style="overflow: auto; padding-bottom: 1.5ex; padding-top: 1ex; font-size: 15px; margin-bottom: 0ex;  margin-top: 0ex;">')
            commands_str = "\n".join(result_json["commands"])
            f.write(commands_str)
            f.write('</pre>\n')
            write_line(f, indention, result_json["invocation-note"])
            indention -= 1
            write_line(f, indention, "</div>")

            write_line(f, indention, '<div class="box">')
            indention += 1
            write_line(f, indention, '<div class="boxlabelo"><div class="boxlabelc">Execution</div></div>')
            write_line(f, indention, '<table style="margin-bottom: 0.75ex;">')
            indention += 1
            if result_json["timeout"]:
                write_line(f, indention, '<tr><td>Walltime:</td><td style="color: red;">&gt {}s (Timeout)</td></tr>'.format(result_json["time-limit"]))
            else:
                write_line(f, indention, '<tr><td>Walltime:</td><td style="tt">{}s</td></tr>'.format(result_json["wallclock-time"]))
                if "model-checking-time" in result_json:
                    write_line(f, indention, '<tr><td>Model Checking Walltime:</td><td style="tt">{}s</td></tr>'.format(result_json["model-checking-time"]))
                return_codes = []
                if "return-codes" in result_json:
                    return_codes = result_json["return-codes"]
                if result_json["execution-error"]:
                    write_line(f, indention, '<tr><td>Return code:</td><td style="tt; color: red;">{}</td></tr>'.format(", ".join([str(rc) for rc in return_codes])))
                else:
                    write_line(f, indention, '<tr><td>Return code:</td><td style="tt">{}</td></tr>'.format(", ".join([str(rc) for rc in return_codes])))
            first = True
            for note in result_json["notes"]:
                write_line(f, indention, '<tr><td>{}</td><td>{}</td></tr>'.format("Note(s):" if first else "", note))
                first = False
            indention -= 1
            write_line(f, indention, "</table>")
            indention -= 1
            write_line(f, indention, "</div>")

            pos1 = log.find("\n", log.find("Output:\n")) + 1
            pos2 = log.find("##############################Output to stderr##############################\n")
            pos_end = pos2 if pos2 >= 0 else len(log)
            log_str = log[pos1:pos_end].strip()
            if len(log_str) != 0:
                write_line(f, indention, '<div class="box">')
                indention += 1
                write_line(f, indention, '<div class="boxlabelo"><div class="boxlabelc">Log</div></div>')
                f.write("\t" * indention + '<pre style="overflow:auto; padding-bottom: 1.5ex">')
                f.write(log_str)
                write_line(f, indention, '</pre>')
                indention -= 1
                write_line(f, indention, "</div>")
            if pos2 >= 0:
                pos2 = log.find("\n", pos2) + 1
                write_line(f, indention, '<div class="box">')
                indention += 1
                write_line(f, indention, '<div class="boxlabelo"><div class="boxlabelc">STDERR</div></div>')
                f.write("\t" * indention + '<pre style="overflow:auto; padding-bottom: 1.5ex">')
                f.write(log[pos2:].strip())
                write_line(f, indention, '</pre>')
                indention -= 1
                write_line(f, indention, "</div>")
            write_line(f, indention, "</body>")
            write_line(f, indention, "</html>")
        return f_path

    num_cols = len(table_data[0])
    first_tool_col = num_cols - num_tool_configs

    with open (os.path.join(path, "table.html"), 'w') as tablefile:
        tablefile.write(r"""<!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>Benchmark results</title>
      <link rel="stylesheet" type="text/css" href="style.css">
      <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.13/css/jquery.dataTables.min.css">
      <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/1.2.4/css/buttons.dataTables.min.css">
      <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedheader/3.1.2/css/fixedHeader.dataTables.min.css">

      <script type="text/javascript" language="javascript" charset="utf8" src="https://code.jquery.com/jquery-1.12.4.js"></script>
      <script type="text/javascript" language="javascript" charset="utf8" src="https://cdn.datatables.net/1.10.13/js/jquery.dataTables.min.js"></script>
      <script type="text/javascript" language="javascript" charset="utf8" src="https://cdn.datatables.net/fixedheader/3.1.2/js/dataTables.fixedHeader.min.js"></script>
      <script type="text/javascript" language="javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.2.4/js/dataTables.buttons.min.js"></script>
      <script type="text/javascript" language="javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.2.4/js/buttons.colVis.min.js"></script>

      <script>
        $(document).ready(function() {
          // Set correct file
          $("#content").load("data.html");
        } );

        function updateBest(table) {
          // Remove old best ones
          table.cells().every( function() {
            $(this.node()).removeClass("best");
          });
          table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
              var bestValue = -1
              var bestIndex = -1
              $.each( this.data(), function( index, value ){
                if (index >= """ + str(first_tool_col) + """ && table.column(index).visible()) {
    			    var text = $(value).text()
    	            if (["TO", "ERR", "INC", "MO", "NS", ""].indexOf(text) < 0) {
    				    var number = parseFloat(text);
    	                if (bestValue == -1 || bestValue > number) {
    	                  // New best value
    	                  bestValue = number;
    	                  bestIndex = index;
    	                }
    				  }
    			  }
              });
              // Set new best
              if (bestIndex >= 0) {
                $(table.cell(rowIdx, bestIndex).node()).addClass("best");
              }
          } );
      }
      </script>
    </head>
    """)
        indention = 0
        write_line(tablefile, indention, "<body>")
        write_line(tablefile, indention, "<div>")
        indention +=1
        write_line(tablefile, indention, '<table id="table" class="display">')
        indention += 1
        write_line(tablefile, indention, '<thead>')
        indention += 1
        write_line(tablefile, indention, '<tr>')
        indention += 1
        for head in table_data[0]:
            write_line(tablefile, indention, '<th>{}</th>'.format(head))
        indention -= 1
        write_line(tablefile, indention, '</tr>')
        indention -= 1
        write_line(tablefile, indention, '</thead>')
        write_line(tablefile, indention, '<tbody>')
        indention += 1

        for row in table_data[1:]:
            for cell_content in row:
                if not SHOW_UNSUPPORTED and (type(cell_content) == list and cell_content[0] == "NS") or (cell_content == "NS"):
                    cell_content = ""
                elif type(cell_content) == list:
                    logpage = create_log_page(cell_content[1])
                    style_classes = dict(TO="timeout", ERR="error", INC ="incorrect", MO="memout", NS="unsupported")
                    link_attributes = "class='{}'".format(style_classes[cell_content[0]]) if cell_content[0] in style_classes else ""
                    cell_content = "<a href='{}' {}>{}</a>".format(logpage, link_attributes, cell_content[0])
                write_line(tablefile, indention, f'<td>{cell_content}</td>')
            indention -= 1
            write_line(tablefile, indention, '</tr>')
        indention -= 1
        write_line(tablefile, indention, '</tbody>')
        indention -= 1
        indention -= 1
        write_line(tablefile, indention, '</table>')
        write_line(tablefile, indention, "<script>")
        indention +=1
        write_line(tablefile, indention, 'var table = $("#table").DataTable( {')
        indention += 1
        write_line(tablefile, indention, '"paging": false,')
        write_line(tablefile, indention, '"autoWidth": false,')
        write_line(tablefile, indention, '"info": false,')
        write_line(tablefile, indention, 'fixedHeader: {')
        indention += 1
        write_line(tablefile, indention, '"header": true,')
        indention -= 1
        write_line(tablefile, indention, '},')
        write_line(tablefile, indention, '"dom": "Bfrtip",')
        write_line(tablefile, indention, 'buttons: [')
        indention += 1
        for columnIndex in range(first_tool_col, num_cols):
            write_line(tablefile, indention, '{')
            indention += 1
            write_line(tablefile, indention, 'extend: "columnsToggle",')
            write_line(tablefile, indention, 'columns: [{}],'.format(columnIndex))
            indention -= 1
            write_line(tablefile, indention, "},")
        tool_columns = [i for i in range(first_tool_col, num_cols)]
        for text, show, hide in zip(["Show all", "Hide all"], [tool_columns, []], [[], tool_columns]):
            write_line(tablefile, indention, '{')
            indention += 1
            write_line(tablefile, indention, 'extend: "colvisGroup",')
            write_line(tablefile, indention, 'text: "{}",'.format(text))
            write_line(tablefile, indention, 'show: {},'.format(show))
            write_line(tablefile, indention, 'hide: {}'.format(hide))
            indention -= 1
            write_line(tablefile, indention, "},")
        indention -= 1
        write_line(tablefile, indention, "],")
        indention -= 1
        write_line(tablefile, indention, "});")
        indention -= 1
        write_line(tablefile, indention, "")
        indention += 1
        write_line(tablefile, indention, 'table.on("column-sizing.dt", function (e, settings) {')
        indention += 1
        write_line(tablefile, indention, "updateBest(table);")
        indention -= 1
        write_line(tablefile, indention, "} );")
        indention -= 1
        write_line(tablefile, indention, "")
        indention += 1
        write_line(tablefile, indention, "updateBest(table);")
        indention -= 1
        write_line(tablefile, indention, "</script>")
        indention -= 1
        write_line(tablefile, indention, "</div>")
        write_line(tablefile, indention, "</body>")
        write_line(tablefile, indention, "</html>")

    with open (os.path.join(path, "style.css"), 'w') as stylefile:
        stylefile.write(r"""

    .best {
        background-color: lightgreen;
    }
    .error {
    	font-weight: bold;
    	background-color: lightcoral;
    }
    .incorrect {
        background-color: orange;
    	font-weight: bold;
    }
    .timeout {
        background-color: lightgray;
    }
    .memout {
        background-color: lightgray;
    }
    .unsupported {
        background-color: yellow;
    }
    .ignored {
        background-color: blue;
    }

    h1 {
    	font-size: 28px; font-weight: bold;
    	color: #000000;
    	padding: 1px; margin-top: 20px; margin-bottom: 1ex;
    }

    tt, .tt {
    	font-family: 'Courier New', monospace; line-height: 1.3;
    }

    .box {
    	margin: 2.5ex 0ex 1ex 0ex; border: 1px solid #D0D0D0; padding: 1.6ex 1.5ex 1ex 1.5ex; position: relative;
    }

    .boxlabelo {
    	position: absolute; pointer-events: none; margin-bottom: 0.5ex;
    }

    .boxlabel {
    	position: relative; top: -3.35ex; left: -0.5ex; padding: 0px 0.5ex; background-color: #FFFFFF; display: inline-block;
    }
    .boxlabelc {
    	position: relative; top: -3.17ex; left: -0.5ex; padding: 0px 0.5ex; background-color: #FFFFFF; display: inline-block;
    }
    """)



def save_latex(
    table_data,
    cols,
    header,
    path,
    grid=False,
    tabcolsep="3pt",
    font_size=LATEX_TABLE_FONT_SIZE,
    alternating_rows=False,
    family_lines=False,
    arraystretch=None,
):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as latex_file:
        latex_file.write("\n")
        if arraystretch is not None:
            latex_file.write(r"\begingroup" + "\n")
            latex_file.write(rf"\renewcommand{{\arraystretch}}{{{arraystretch}}}" + "\n")
        latex_file.write(rf"\renewcommand{{\tabcolsep}}{{{tabcolsep}}}" + "\n")
        latex_file.write(rf"\{font_size}" + "\n")
        latex_file.write(r"\begin{tabular}{@{}")
        latex_file.write(cols)
        latex_file.write("@{}}\n\n")
        latex_file.write(r"\toprule" + "\n")
        latex_file.write(header + "\\\\\\midrule\n")
        previous_family = None
        for row_index, row in enumerate(table_data[1:]):
            model_cell = row[0]
            family = model_cell[0] if isinstance(model_cell, (list, tuple)) else model_cell
            row_span = max(
                (len(cell) if isinstance(cell, (list, tuple)) else 1)
                for cell in row
            )
            if family_lines and previous_family is not None and family != previous_family:
                latex_file.write(r"\midrule" + "\n")
            previous_family = family
            for line_index in range(row_span):
                line = []
                for cell in row:
                    if isinstance(cell, (list, tuple)):
                        if line_index < len(cell):
                            line.append(cell[line_index])
                        else:
                            color = re.match(r"(\\cellcolor\{[^}]+\})", cell[0]) if cell else None
                            line.append(color.group(1) if color is not None else "")
                    elif row_span == 1:
                        line.append(cell)
                    else:
                        if alternating_rows:
                            line.append(
                                rf"\multirow{{-{row_span}}}{{*}}{{{cell}}}"
                                if line_index == row_span - 1 else ""
                            )
                        else:
                            line.append(
                                rf"\multirow{{{row_span}}}{{*}}{{{cell}}}"
                                if line_index == 0 else ""
                            )
                row_color = (
                    r"\rowcolor{gray!20}"
                    if alternating_rows and row_index % 2 == 1 else ""
                )
                if row_color:
                    line = [
                        cell.replace(
                            rf"\cellcolor{{{LATEX_HIGHLIGHT_COLOR}}}",
                            rf"\cellcolor{{{LATEX_SHADED_HIGHLIGHT_COLOR}}}",
                        )
                        for cell in line
                    ]
                latex_file.write(row_color + "\t" + "\t&\t".join(line) + "\\\\\n")
        latex_file.write(r"\bottomrule" + "\n")
        latex_file.write("\\end{tabular}\n")
        if arraystretch is not None:
            latex_file.write(r"\endgroup" + "\n")

def fixed_latex_column(alignment, width):
    declarations = {
        "center": r"\centering",
        "right": r"\raggedleft",
        "left": r"\raggedright",
    }
    return rf">{{{declarations[alignment]}\arraybackslash}}p{{{width}}}"

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

def is_successful_result(data, maxtime=None):
    if data is None or "result" not in data:
        return False
    if any(data.get(key, False) for key in ["timeout", "memout", "execution-error", "expected-error", "not-supported"]):
        return False
    return maxtime is None or data["wallclock-time"] <= maxtime

def expected_bound_relation(cfgbase, benchmark):
    direction = benchmark["property"]["dir"]
    if cfgbase in ["cut", "clip"]: # under-approximation
        return "≥" if direction == "max" else "≤"
    if cfgbase == "discr": # over-approximation
        return "≤" if direction == "max" else "≥"
    return None

def comparison_value(value):
    return round(float(value), RESULT_COMPARISON_DECIMALS)

def result_selection_score(data, expected_relation):
    relation, result = parse_result_value(data["result"])
    if relation == "=":
        # Every exact result is preferable to a bound. Exact results for one
        # benchmark are expected to agree, so use runtime as the tie-breaker.
        return (1, 0, -data["wallclock-time"])
    if expected_relation is not None and relation != expected_relation:
        raise ValueError(f"Expected a '{expected_relation}' bound, got '{data['result']}'")
    quality = comparison_value(result)
    quality = quality if relation == "≥" else -quality
    return (0, quality, -data["wallclock-time"])

def parse_tool_output(execution_json):
    with open(execution_json["log"], 'r') as logfile:
        log = logfile.read()
    execution_json["notes"] = [execution_json["invocation-note"]]
    execution_json["benchmark"] = benchmarks.from_id(execution_json["benchmark-id"])

    assert execution_json["tool"] in TOOL_NAMES, "Error: Unknown tool '{}'".format(execution_json["tool"])
    tool = TOOL_NAMES[execution_json["tool"]]
    execution_json["configuration"] = tool.config_from_id(execution_json["configuration-id"])
    # IDs alone are not enough: historical sweeps used different thresholds.
    args = shlex.split(execution_json["commands"][0])
    configuration = execution_json["configuration"]
    if configuration.get("family") == "cutoff":
        threshold = int(args[args.index("--size-threshold") + 1])
        if threshold != configuration["size-threshold"]:
            raise ValueError(f"Recorded threshold {threshold} disagrees with {configuration['id']}")
        execution_json["size-threshold"] = threshold
    tool.parse_logfile(log, execution_json)

# stores benchmark-instance specific data from the execution. Reports inconsistencies with other executions on the same instance
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
    bench_data["dim"] = execution_json["benchmark"]["property"].get("num-bnd-rew-assignments", 0)
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
        for key in ["id", "name", "formalism", "type", "par", "property", "property-dir", "property-id", "dim", "states", "choices", "observations", "transitions"]:
            if key in bench_data:
                if key in benchmark_instances[bench_id]:
                    if benchmark_instances[bench_id][key] != bench_data[key]:
                        print("WARN: Inconsistency with field {}: '{}' vs '{}'  between any of \n\t{}\nand\t{}".format(key,benchmark_instances[bench_id][key], bench_data[key], benchmark_instances[bench_id]["invocations"], bench_data["invocations"]))
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
    exec_data = OrderedDict() # Tool -> Config -> Benchmark -> Data
    benchmark_instances = OrderedDict() # ID -> data
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
        json_files = [ f for f in os.listdir(logdir) if f.endswith(".json") and os.path.isfile(os.path.join(logdir, f)) ]
        ignored_benchmarks = Counter()
        ignored_configurations = Counter()
        i = 0
        for execution_json in [ load_json(os.path.join(logdir, f)) for f in json_files ]:
            benchmark = execution_json["benchmark-id"]
            if benchmark not in known_benchmark_ids:
                ignored_benchmarks[benchmark] += 1
                continue
            i += 1
            tool = execution_json["tool"]
            config = execution_json["configuration-id"]
            if config not in known_configuration_ids.get(tool, set()):
                ignored_configurations[(tool, config)] += 1
                continue
            exec_data.setdefault(tool, OrderedDict())
            exec_data[tool].setdefault(config, OrderedDict())
            assert benchmark not in exec_data[tool][config], "Error: Multiple result files found for {}.{}.{}".format(tool,config,benchmark)
            execution_json["log"] = os.path.join(logdir, execution_json["log"])
            try:
                parse_tool_output(execution_json)
            except AssertionError as e:
                print("Error when parsing logfile {}:\n{}".format(execution_json["log"], e))
                continue
            exec_data[tool][config][benchmark] = execution_json
            if "input-model" in execution_json:
                process_benchmark_instance_data(benchmark_instances, execution_json)
            else:
                print(f"WARN: No input-model statistics in failed execution {execution_json['id']}")

        for benchmark, count in sorted(ignored_benchmarks.items()):
            print(f"WARN: Ignoring {count} result file(s) for removed benchmark {benchmark}")
        for (tool, config), count in sorted(ignored_configurations.items()):
            print(f"WARN: Ignoring {count} result file(s) for removed configuration {tool}.{config}")

    # warn for missing configs:
    if not silent:
        for t in TOOL_NAMES:
            if t not in list(exec_data.keys()) + []: print(f"WARN: no data for tool '{t}'") # no warning for tools in the given list
            else:
                for cfg in TOOL_NAMES[t].CONFIGS:
                    if cfg["id"] not in list(exec_data[t].keys()) + ["split"]: print(f"WARN: no data for {t} config '{cfg['id']}'") #no warning for configs in the given list
    return exec_data, benchmark_instances

def process_meta_configs(exec_data, benchmark_instances):
    # gather data for meta-configurations
    for tool in exec_data:
        for metacfg in TOOL_NAMES[tool].META_CONFIGS:
            benchmark_data = OrderedDict()
            for benchmark in benchmark_instances:
                best_cfg_id = None
                expected_relation = expected_bound_relation(metacfg["cfgbase"], benchmarks.from_id(benchmark))
                for cfg_id in exec_data[tool]:
                    if cfg_id in [c["id"] for c in TOOL_NAMES[tool].META_CONFIGS]: continue
                    if not cfg_id.startswith(metacfg["cfgbase"]): continue
                    if benchmark not in  exec_data[tool][cfg_id]: continue
                    data = exec_data[tool][cfg_id][benchmark]
                    if not is_successful_result(data, metacfg.get("maxtime")): continue
                    if best_cfg_id is None:
                        try:
                            result_selection_score(data, expected_relation)
                            best_cfg_id = cfg_id
                        except ValueError as e:
                            print(f"WARN: {e} in {data['id']}")
                        continue
                    try:
                        if result_selection_score(data, expected_relation) > result_selection_score(exec_data[tool][best_cfg_id][benchmark], expected_relation):
                            best_cfg_id = cfg_id
                    except ValueError as e:
                        print(f"WARN: {e} in {data['id']}")
                if best_cfg_id is not None: benchmark_data[benchmark] = copy.deepcopy(exec_data[tool][best_cfg_id][benchmark])
            exec_data[tool][metacfg["id"]] = benchmark_data

def get_result(exec_data, tool, config, inst_id):
        if tool in exec_data and config in exec_data[tool] and inst_id in exec_data[tool][config]:
            return exec_data[tool][config][inst_id]

def get_result_if_supported(exec_data, tool, config, inst_id):
        res = get_result(exec_data, tool, config, inst_id)
        if res is not None and not res["not-supported"]:
            return res

def runtime_status(run):
    """Distinguish recorded kills from confirmed memory errors in runtime reports."""
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


def save_runtime_overview(exec_data, logdirs):
    """Summarise each recorded configuration once, including unsuccessful runs."""
    statuses = ["successful", "timeout", "killed", "memout", "failed"]
    runs = []
    instance_runs = {inst["id"]: [] for inst in benchmarks.INSTANCES}
    family_runs = OrderedDict()
    config_runs = OrderedDict()
    family_expected = Counter()
    config_expected = Counter()
    for tool in TOOLS:
        for cfg in tool.CONFIGS:
            family = cfg.get("family", cfg["id"])
            config = f"{tool.NAME}.{cfg['id']}"
            selected = list(exec_data.get(tool.NAME, {}).get(cfg["id"], {}).values())
            family_runs.setdefault(family, []).extend(selected)
            config_runs[config] = selected
            supported = [inst for inst in benchmarks.INSTANCES
                         if inst["model"]["formalism"] in cfg["supported-model-formalisms"]
                         and inst["model"]["type"] in cfg["supported-model-types"]
                         and inst["property"]["type"] in cfg["supported-obj-types"]]
            config_expected[config] = len(supported)
            family_expected[family] += len(supported)
            for run in selected:
                instance_runs[run["benchmark-id"]].append(run)
            runs.extend(selected)

    def summary(label, selected, expected):
        counts = Counter(runtime_status(run) for run in selected)
        seconds = math.fsum(run["wallclock-time"] for run in selected)
        success_seconds = math.fsum(run["wallclock-time"] for run in selected
                                    if runtime_status(run) == "successful")
        return [label, expected, len(selected), *(counts[status] for status in statuses),
                expected - len(selected), seconds, success_seconds, seconds - success_seconds]

    header = ["group", "expected_runs", "recorded_runs", *statuses, "missing",
              "wallclock_seconds", "successful_seconds", "unsuccessful_seconds"]
    total = summary("TOTAL", runs, sum(config_expected.values()))
    family_rows = [summary(family, selected, family_expected[family])
                   for family, selected in family_runs.items()]
    instance_rows = []
    for inst in benchmarks.INSTANCES:
        expected = sum(inst["model"]["formalism"] in cfg["supported-model-formalisms"]
                       and inst["model"]["type"] in cfg["supported-model-types"]
                       and inst["property"]["type"] in cfg["supported-obj-types"]
                       for tool in TOOLS for cfg in tool.CONFIGS)
        instance_rows.append(summary(inst["id"], instance_runs[inst["id"]], expected))
    for filename, rows in [
        ("runtime-by-family.csv", family_rows),
        ("runtime-by-instance.csv", instance_rows),
        ("runtime-by-configuration.csv", [summary(config, selected, config_expected[config])
                                          for config, selected in config_runs.items()]),
    ]:
        save_csv([header, *rows, total], os.path.join(OUT_DIR, filename))
    audit = [["instance", "tool", "configuration", "family", "wallclock_seconds",
              "status", "time_limit_seconds", "return_codes"]]
    for run in sorted(runs, key=lambda run: run["id"]):
        cfg = TOOL_NAMES[run["tool"]].config_from_id(run["configuration-id"])
        audit.append([run["benchmark-id"], run["tool"], run["configuration-id"],
                      cfg.get("family", cfg["id"]), run["wallclock-time"], runtime_status(run),
                      run["time-limit"], json.dumps(run.get("return-codes", []))])
    save_csv(audit, os.path.join(OUT_DIR, "runtime-runs.csv"))

    seconds = total[-3]
    report = ["# Runtime overview\n\n",
              "Sources: " + ", ".join(f"`{directory}`" for directory in logdirs) + ".\n\n",
              f"**Cumulative runtime: {runtime_duration(seconds)}** "
              f"({seconds:,.2f} seconds; {seconds / 3600:.3f} hours).\n\n",
              f"Recorded {len(runs)} of {total[1]} expected runs across "
              f"{len(instance_runs)} instances; {total[8]} runs missing.\n\n",
              "Runtime is the sum of recorded per-run wall-clock times, including failures "
              "and timeout overruns. It is not the elapsed duration of a parallel batch. "
              "Derived best-configuration results are excluded to avoid double-counting.\n\n",
              f"Successful runs: {runtime_duration(total[-2])}; unsuccessful runs: "
              f"{runtime_duration(total[-1])} "
              f"({100 * total[-1] / seconds if seconds else 0:.1f}% of total runtime).\n\n",
              "## Outcomes\n\n",
              "| Outcome | Runs | Runtime | Share |\n| --- | ---: | ---: | ---: |\n"]
    for status in statuses:
        selected = [run for run in runs if runtime_status(run) == status]
        status_seconds = math.fsum(run["wallclock-time"] for run in selected)
        report.append(f"| {status} | {len(selected)} | {runtime_duration(status_seconds)} | "
                      f"{100 * status_seconds / seconds if seconds else 0:.1f}% |\n")
    report.append("\n`killed` means return code -9 (SIGKILL) without a recorded timeout. "
                  "These logs do not establish the cause; a kill alone is not proof of a memory-out. "
                  "`memout` denotes a memory error identified by the parser.\n\n")
    for title, rows in [("Configuration families", family_rows),
                        ("Instances", sorted(instance_rows, key=lambda row: row[-3], reverse=True))]:
        report.extend([f"## {title}\n\n",
                       "| Group | Runs | Success | Timeout | Killed | Memory-out | Other failed | Missing | Runtime | Share |\n",
                       "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"])
        for row in rows:
            label = row[0].split("_", 1)[1].rstrip("_") if title == "Instances" else row[0]
            report.append(f"| `{label}` | " + " | ".join(str(value) for value in row[2:9])
                          + f" | {runtime_duration(row[-3])} | "
                          + f"{100 * row[-3] / seconds if seconds else 0:.1f}% |\n")
        report.append("\n")
    report.append("Exact runtimes and counts are exported as tab-separated "
                  "`runtime-by-family.csv`, `runtime-by-instance.csv`, "
                  "`runtime-by-configuration.csv`, and `runtime-runs.csv`.\n")
    path = os.path.join(OUT_DIR, "runtime-report.md")
    with open(path, "w") as output:
        output.writelines(report)
    print(f"Cumulative runtime: {runtime_duration(seconds)} across {len(runs)} runs "
          f"({total[3]} successful, {total[4]} timeouts, {total[5]} killed); report: {path}")

def latex_number(value, decimal_places=None):
    value = float(value)
    if value != 0 and abs(value) >= 10**5:
        exponent = math.floor(math.log10(abs(value)))
        coefficient = round(value / 10**exponent, decimal_places or 2)
        if abs(coefficient) >= 10:
            coefficient /= 10
            exponent += 1
        coefficient_format = (
            f"{coefficient:.{decimal_places}f}"
            if decimal_places is not None else f"{coefficient:.3g}"
        )
        return rf"{coefficient_format}{{\cdot}}10^{{{exponent}}}"

    if decimal_places is not None:
        return f"{value:.{decimal_places}f}"

    # Keep three significant digits without letting Python switch to
    # scientific notation for values below 10^5.
    if value == 0:
        return "0"
    decimal_places = 2 - math.floor(math.log10(abs(value)))
    rounded = round(value, decimal_places) if decimal_places < 0 else value
    formatted = f"{rounded:.{max(0, decimal_places)}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted

def latex_size(value):
    value = int(value)
    if abs(value) < 1_000_000:
        return str(value)
    exponent = math.floor(math.log10(abs(value)))
    coefficient = round(value / 10**exponent, 2)
    if abs(coefficient) >= 10:
        coefficient /= 10
        exponent += 1
    return rf"{coefficient:.2f}{{\cdot}}10^{{{exponent}}}"

def latex_belief_mdp_size(result):
    if result is None:
        return ""
    states = result.get("belief-mdp", {}).get("states")
    return "" if states is None else rf"${latex_size(states)}$"

def latex_result(result, bold=False, decimal_places=None):
    relation, value = parse_result_value(result)
    relation_latex = {"=": "", "≤": r"\le ", "≥": r"\ge "}[relation]
    value_latex = latex_number(value, decimal_places)
    if bold:
        value_latex = rf"\mathbf{{{value_latex}}}"
    return f"${relation_latex}{value_latex}$"

def latex_mdp_bound(result, direction, bold=False, decimal_places=None):
    _, value = parse_result_value(result)
    relation = "≥" if direction == "min" else "≤"
    return latex_result(f"{relation}{value}", bold, decimal_places)

def latex_time(value):
    if value < 1.0:
        return r"\textless 1"
    if value < 100:
        return f"{value:.1f}"
    return f"{value:.0f}"

def latex_configuration_parameter(cfgbase, cfg_id):
    if cfgbase == "cut":
        configuration = next((cfg for cfg in storm.CONFIGS if cfg["id"] == cfg_id), None)
        if configuration is not None:
            value = configuration["size-threshold"]
            exponent = len(str(value)) - 1
            mantissa = value // 10**exponent
            threshold = f"10^{{{exponent}}}" if mantissa == 1 else rf"{mantissa}\cdot10^{{{exponent}}}"
            return f"$\\sizethreshold{{=}}{threshold}$"
    elif cfgbase == "clip":
        match = re.fullmatch(r"clip(\d{2})res(\d{2})", cfg_id)
        if match is not None:
            threshold = r"\mathrm{def.}" if match.group(1) == "00" else f"2^{{{int(match.group(1))}}}"
            return fr"$\sizethreshold{{=}}{threshold},\resolution{{=}}{int(match.group(2))}$"
    elif cfgbase == "discr":
        match = re.fullmatch(r"discr(\d{3})([sd])", cfg_id)
        if match is not None:
            mode = r"\mathrm{static}" if match.group(2) == "s" else r"\mathrm{dyn.}"
            return fr"$\resolution{{=}}{int(match.group(1))},\ {mode}$"
    return cfg_id.replace("_", r"\_")

def unavailable_result_cell(exec_data, config_ids, inst_id):
    runs = [get_result(exec_data, storm.NAME, cfg_id, inst_id) for cfg_id in config_ids]
    runs = [run for run in runs if run is not None]
    if len(runs) == 0:
        return ""

    statuses = set()
    for run in runs:
        # A killed process is also recorded as an execution error by the runner.
        # Classify each execution by its most specific cause so that a memory-out
        # is not additionally reported as a generic error.
        if run.get("timeout", False):
            statuses.add("TO")
        elif run.get("memout", False):
            statuses.add("MO")
        elif (run.get("execution-error", False) or run.get("expected-error", False)
              or run.get("not-supported", False) or "result" not in run):
            statuses.add("ERR")

    status_order = ["TO", "MO", "ERR"]
    return " / ".join(status for status in status_order if status in statuses) or "ERR"

def is_failure_status(status):
    return len(status.split(" / ")) > 0 and all(
        item in ["TO", "MO", "ERR"] for item in status.split(" / ")
    )

def failure_status_cell(status):
    return status


def highlighted_cell_lines(lines, highlight=False):
    if not highlight:
        return lines
    return [rf"\cellcolor{{{LATEX_HIGHLIGHT_COLOR}}}" + line for line in lines]

def result_time_lines(result, runtime=None):
    if runtime is None:
        return [result]
    return [result, f"{latex_time(runtime)}s"]

def dissertation_cell(result, runtime=None, parameter=None, highlight=False):
    if runtime is None and parameter is None and is_failure_status(result):
        return failure_status_cell(result)
    lines = result_time_lines(result, runtime)
    if parameter is not None:
        lines.append(parameter)
    return highlighted_cell_lines(lines, highlight)

def dissertation_result_cell(exec_data, inst_id, cfgbase, timelimit, highlight=False):
    metacfg_id = f"{cfgbase}-best-in-{timelimit}s"
    result = get_result(exec_data, storm.NAME, metacfg_id, inst_id)
    if result is None:
        config_ids = [cfg["id"] for cfg in storm.CONFIGS if cfg["id"].startswith(cfgbase)]
        return dissertation_cell(unavailable_result_cell(exec_data, config_ids, inst_id))
    parameter = latex_configuration_parameter(cfgbase, result["configuration-id"])
    return dissertation_cell(
        latex_result(
            result["result"], highlight, dissertation_result_decimal_places(inst_id)
        ),
        result["wallclock-time"],
        parameter,
        highlight,
    )

def dissertation_property(instance):
    property_symbol = "P" if instance["property"] == "prb" else "R"
    base_id = instance["property"] + instance["property-dir"]
    qualifier = instance["property-id"][len(base_id):]
    qualifier = {"packets": "pack"}.get(qualifier, qualifier)
    qualifier_latex = "" if qualifier == "" else rf"^{{\mathrm{{{qualifier}}}}}"
    return rf"${property_symbol}_\mathrm{{{instance['property-dir']}}}{qualifier_latex}$"

def dissertation_result_decimal_places(inst_id):
    return None if benchmarks.from_id(inst_id)["property"]["type"] == "prb" else 2

def dissertation_parameters(instance):
    crypt_sizes = {"crypt": "2", "crypt4": "4", "crypt6": "6"}
    if instance["benchmark-set"] in crypt_sizes:
        return crypt_sizes[instance["benchmark-set"]]
    parameters = instance["par"].replace("_", r"\_")
    return "sl0" if re.fullmatch(r"sl0+", parameters) else parameters

def latex_model_name(name):
    return LATEX_MODEL_ABBREVIATIONS.get(name, name)

def dissertation_model(instance, finite_belief_mdp=False):
    model = f"\\model{{{latex_model_name(instance['name'])}}}"
    if finite_belief_mdp:
        model += "$^*$"
    parameters = dissertation_parameters(instance)
    return model if parameters == "" else [model, f"\\model{{{parameters}}}"]

def dissertation_model_identity(benchmark):
    model = benchmark["model"]
    return (
        model["file"],
        tuple(model.get("file-parameters", {}).items()),
        tuple(model.get("open-parameters", {}).items()),
    )

def finite_belief_mdp_models(exec_data, benchmark_instances):
    finite_models = set()
    cutoff_ids = [cfg["id"] for cfg in storm.CONFIGS if cfg["id"].startswith("cut")]
    for benchmark in benchmarks.INSTANCES:
        inst_id = benchmark["id"]
        if inst_id not in benchmark_instances:
            continue
        for config_id in cutoff_ids:
            result = get_result(exec_data, storm.NAME, config_id, inst_id)
            if (is_successful_result(result) and
                    "belief-mdp" in result and
                    "states" in result["belief-mdp"] and
                    not result.get("belief-mdp-incomplete", False) and
                    parse_result_value(result["result"])[0] == "="):
                finite_models.add(dissertation_model_identity(benchmark))
                break
    return finite_models

def save_dissertation_tables(exec_data, benchmark_instances, timelimit=1800):
    model_column = fixed_latex_column("center", "16mm")
    objective_column = fixed_latex_column("center", "10mm")
    result_column = fixed_latex_column("right", "21.5mm")
    benchmark_headers = [
        "Model",
        "Parameters",
        r"States",
        r"Choices",
        r"Observations",
    ]
    result_headers = [
        "Model",
        "Obj.",
        r"\config{cut}",
        r"\config{clip}",
        r"\config{mdp}",
        r"\config{discr}",
    ]

    benchmark_rows = [[]]
    benchmark_families = OrderedDict()
    seen_models = set()
    finite_models = finite_belief_mdp_models(exec_data, benchmark_instances)
    for benchmark in benchmarks.INSTANCES:
        if benchmark["id"] not in benchmark_instances:
            continue
        model_identity = dissertation_model_identity(benchmark)
        if model_identity in seen_models:
            continue
        seen_models.add(model_identity)
        instance = benchmark_instances[benchmark["id"]]
        benchmark_families.setdefault(instance["name"], []).append((instance, model_identity))

    for family_name, parameterisations in benchmark_families.items():
        family_cell = f"\\model{{{latex_model_name(family_name)}}}"
        parameters = []
        states = []
        choices = []
        observations = []
        for instance, model_identity in parameterisations:
            parameter = dissertation_parameters(instance)
            parameter_cell = "" if parameter == "" else f"\\model{{{parameter}}}"
            if model_identity in finite_models:
                if parameter == "":
                    family_cell += "$^*$"
                else:
                    parameter_cell += "$^*$"
            parameters.append(parameter_cell)
            states.append(str(instance["states"]))
            choices.append(str(instance["choices"]))
            observations.append(str(instance["observations"]))
        benchmark_rows.append([
            family_cell,
            parameters,
            states,
            choices,
            observations,
        ])
    save_latex(benchmark_rows, "c c | r r r", "\n& ".join(benchmark_headers), os.path.join(TABLE_DIR, "tablebenchmarks.tex"), grid=True, font_size="small", family_lines=True)

    objective_tables = [
        ("prb", "min", "tableprbmin.tex"),
        ("prb", "max", "tableprbmax.tex"),
        ("rew", "min", "tablerewmin.tex"),
        ("rew", "max", "tablerewmax.tex"),
    ]

    for property_type, direction, filename in objective_tables:
        instance_ids = [
            inst["id"] for inst in benchmarks.INSTANCES
            if inst["id"] in benchmark_instances and
               inst["property"]["type"] == property_type and
               inst["property"]["dir"] == direction
        ]
        rows = [[]]
        for inst_id in instance_ids:
            instance = benchmark_instances[inst_id]
            cut_id = f"cut-best-in-{timelimit}s"
            clip_id = f"clip-best-in-{timelimit}s"
            discr_id = f"discr-best-in-{timelimit}s"
            underapproximation_highlights = best_approximation_configs(
                exec_data, inst_id, [cut_id, clip_id], direction, "under", timelimit
            )
            overapproximation_highlights = best_approximation_configs(
                exec_data, inst_id, [discr_id, "mdp"], direction, "over", timelimit
            )
            mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
            if is_successful_result(mdp, timelimit):
                mdp_highlighted = "mdp" in overapproximation_highlights
                mdp_cell = dissertation_cell(
                    latex_mdp_bound(
                        mdp["result"], direction, mdp_highlighted,
                        dissertation_result_decimal_places(inst_id),
                    ),
                    mdp["wallclock-time"],
                    highlight=mdp_highlighted,
                )
            else:
                mdp_cell = dissertation_cell(unavailable_result_cell(exec_data, ["mdp"], inst_id))
            rows.append([
                dissertation_model(instance),
                dissertation_property(instance),
                dissertation_result_cell(exec_data, inst_id, "cut", timelimit, cut_id in underapproximation_highlights),
                dissertation_result_cell(exec_data, inst_id, "clip", timelimit, clip_id in underapproximation_highlights),
                mdp_cell,
                dissertation_result_cell(exec_data, inst_id, "discr", timelimit, discr_id in overapproximation_highlights),
            ])
        result_column_spec = (
            rf"{model_column}@{{\hspace{{0.5pt}}}}{objective_column} | "
            + " | ".join([result_column] * 4)
        )
        save_latex(
            rows,
            result_column_spec,
            "\n& ".join(result_headers),
            os.path.join(TABLE_DIR, filename),
            grid=True,
            tabcolsep="1pt",
            alternating_rows=True,
        )

def dissertation_value_cell(
    exec_data, inst_id, config_id, bold=False, configuration=None, bound_direction=None
):
    result = get_result(exec_data, storm.NAME, config_id, inst_id)
    belief_states = latex_belief_mdp_size(result)
    if is_successful_result(result):
        formatted_result = (
            latex_mdp_bound(
                result["result"], bound_direction, bold,
                dissertation_result_decimal_places(inst_id),
            )
            if bound_direction is not None else latex_result(
                result["result"], bold, dissertation_result_decimal_places(inst_id)
            )
        )
        lines = result_time_lines(formatted_result, result["wallclock-time"])
        lines.append(belief_states)
        if configuration is not None:
            lines.append(configuration)
        return lines
    status = unavailable_result_cell(exec_data, [config_id], inst_id)
    if is_failure_status(status):
        return failure_status_cell(status)
    lines = [status, belief_states]
    if configuration is not None:
        lines.append(configuration)
    return lines

def best_approximation_configs(exec_data, inst_id, config_ids, direction, approximation="over", maxtime=None):
    candidates = {}
    for config_id in config_ids:
        result = get_result(exec_data, storm.NAME, config_id, inst_id)
        if is_successful_result(result, maxtime):
            _, value = parse_result_value(result["result"])
            candidates[config_id] = (comparison_value(value), result["wallclock-time"])
    if len(candidates) == 0:
        return set()
    select_value = max if (approximation == "over") == (direction == "min") else min
    best_value = select_value(value for value, _ in candidates.values())
    best_value_candidates = {
        config_id: runtime for config_id, (value, runtime) in candidates.items()
        if value == best_value
    }
    best_runtime = min(best_value_candidates.values())
    return {config_id for config_id, runtime in best_value_candidates.items() if runtime == best_runtime}

def fastest_discretisation_matching_mdp(exec_data, inst_id, config_ids, direction):
    """Select by run wall time, comparing bounds at precision 10^-6."""
    mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
    if not is_successful_result(mdp):
        return None
    mdp_value = comparison_value(parse_result_value(mdp["result"])[1])
    candidates = {}
    for config_id in config_ids:
        result = get_result(exec_data, storm.NAME, config_id, inst_id)
        if not is_successful_result(result):
            continue
        value = comparison_value(parse_result_value(result["result"])[1])
        if (value >= mdp_value if direction == "min" else value <= mdp_value):
            candidates[config_id] = result["wallclock-time"]
    return min(candidates, key=candidates.get, default=None)


def save_overapproximation_table(exec_data, benchmark_instances):
    summary_model_column = fixed_latex_column("center", "20mm")
    summary_objective_column = fixed_latex_column("center", "12mm")
    resolution_model_column = fixed_latex_column("center", "14mm")
    resolution_objective_column = fixed_latex_column("center", "9mm")
    summary_result_column = fixed_latex_column("right", "26.9mm")
    resolution_result_column = fixed_latex_column("right", "15mm")
    shown_resolutions = [2, 5, 12]
    all_discretization_ids = [
        f"discr{resolution:03}{mode}"
        for resolution in range(2, 13) for mode in ["s", "d"]
    ]
    summary_header = "\n& ".join([
        "Model", "Obj.", r"\config{mdp}",
        r"\config{discr} -- Fastest Matching",
        r"\config{discr} -- Tightest",
    ])
    resolution_first_header = "\n& ".join(
        [r"\multirow{2}{*}{Model}", r"\multirow{2}{*}{Obj.}"] +
        [rf"\multicolumn{{2}}{{c{'|' if index < len(shown_resolutions) - 1 else ''}}}"
         rf"{{$\resolution={resolution}$}}"
         for index, resolution in enumerate(shown_resolutions)]
    )
    resolution_second_header = "\n& ".join(
        ["", ""] +
        [mode for _ in shown_resolutions for mode in ["static", "dynamic"]]
    )
    resolution_header = (
        resolution_first_header + r"\\" + "\n" + resolution_second_header
    )

    objective_tables = [
        ("prb", "min", "tableoverapproxprbmin.tex"),
        ("prb", "max", "tableoverapproxprbmax.tex"),
        ("rew", "min", "tableoverapproxrewmin.tex"),
        ("rew", "max", "tableoverapproxrewmax.tex"),
    ]
    for property_type, direction, filename in objective_tables:
        summary_rows = [[]]
        resolution_rows = [[]]
        for benchmark in benchmarks.INSTANCES:
            if (benchmark["property"]["type"] != property_type or
                    benchmark["property"]["dir"] != direction):
                continue
            inst_id = benchmark["id"]
            if inst_id not in benchmark_instances:
                continue
            instance = benchmark_instances[inst_id]
            best_discretization_ids = best_approximation_configs(
                exec_data, inst_id, all_discretization_ids, instance["property-dir"]
            )
            best_discretization_id = next(
                (config_id for config_id in all_discretization_ids
                 if config_id in best_discretization_ids), None
            )
            fastest_id = fastest_discretisation_matching_mdp(
                exec_data, inst_id, all_discretization_ids, direction
            )
            highlighted_ids = best_approximation_configs(
                exec_data, inst_id, [best_discretization_id, "mdp"], instance["property-dir"]
            )
            def selected_cell(config_id):
                if config_id is None:
                    return r"\textemdash"
                return dissertation_value_cell(
                    exec_data, inst_id, config_id, config_id in highlighted_ids,
                    latex_configuration_parameter("discr", config_id),
                )

            summary_rows.append([
                dissertation_model(instance),
                dissertation_property(instance),
                dissertation_value_cell(
                    exec_data, inst_id, "mdp", "mdp" in highlighted_ids,
                    bound_direction=direction,
                ),
                selected_cell(fastest_id),
                selected_cell(best_discretization_id),
            ])
            resolution_cells = []
            for resolution in shown_resolutions:
                for mode in ["s", "d"]:
                    cell = dissertation_value_cell(
                        exec_data, inst_id, f"discr{resolution:03}{mode}",
                    )
                    resolution_cells.append(cell)
            resolution_rows.append([
                dissertation_model(instance),
                dissertation_property(instance),
                *resolution_cells,
            ])
        summary_column_spec = (
            rf"{summary_model_column}@{{\hspace{{0.5pt}}}}{summary_objective_column}"
            + f" | {summary_result_column}" * 3
        )
        resolution_column_spec = (
            rf"{resolution_model_column}@{{\hspace{{0.5pt}}}}{resolution_objective_column}"
            + f" | {resolution_result_column} {resolution_result_column}"  * 3
        )
        save_latex(summary_rows, summary_column_spec, summary_header,
                   os.path.join(OVERAPPROX_TABLE_DIR, filename), grid=True,
                   tabcolsep="1pt", alternating_rows=True, arraystretch="0.95")
        save_latex(resolution_rows, resolution_column_spec, resolution_header,
                   os.path.join(OVERAPPROX_TABLE_DIR, filename.replace("tableoverapprox", "tableoverapproxresolution")),
                   grid=True, tabcolsep="1pt", alternating_rows=True)


def underapproximation_summary_cell(exec_data, inst_id, config_id):
    result = get_result(exec_data, storm.NAME, config_id, inst_id)
    if is_successful_result(result):
        lines = result_time_lines(
            latex_result(
                result["result"], decimal_places=dissertation_result_decimal_places(inst_id)
            ),
            result["wallclock-time"],
        )
        lines.append(latex_belief_mdp_size(result))
        return lines
    status = unavailable_result_cell(exec_data, [config_id], inst_id)
    return failure_status_cell(status) if is_failure_status(status) else status


def underapproximation_summary_best_cell(
    exec_data, inst_id, cfgbase, timelimit, highlight=False
):
    metacfg_id = f"{cfgbase}-best-in-{timelimit}s"
    result = get_result(exec_data, storm.NAME, metacfg_id, inst_id)
    if result is None:
        config_ids = [cfg["id"] for cfg in storm.CONFIGS if cfg["id"].startswith(cfgbase)]
        return dissertation_cell(unavailable_result_cell(exec_data, config_ids, inst_id))
    lines = result_time_lines(
        latex_result(
            result["result"], highlight, dissertation_result_decimal_places(inst_id)
        ),
        result["wallclock-time"],
    )
    lines.extend([
        latex_belief_mdp_size(result),
        latex_configuration_parameter(cfgbase, result["configuration-id"]),
    ])
    return highlighted_cell_lines(lines, highlight)


def save_underapproximation_tables(
    exec_data, benchmark_instances, timelimit=storm.META_CONFIG_TIMELIMITS[0]
):
    summary_model_column = fixed_latex_column("center", "14mm")
    summary_objective_column = fixed_latex_column("center", "9mm")
    summary_result_column = fixed_latex_column("right", "15mm")
    objective_tables = [
        ("prb", "min", "prbmin"),
        ("prb", "max", "prbmax"),
        ("rew", "min", "rewmin"),
        ("rew", "max", "rewmax"),
    ]

    summary_clipping_resolutions = [2, 3, 4]
    heuristic_cutoff_id = "cut00"
    heuristic_clipping_ids = [
        f"clip00res{resolution:02}" for resolution in summary_clipping_resolutions
    ]
    summary_first_header = "\n& ".join([
        r"\multirow{2}{*}{Model}",
        r"\multirow{2}{*}{Obj.}",
        r"\multicolumn{2}{c|}{\config{cut}}",
        rf"\multicolumn{{{len(summary_clipping_resolutions) + 1}}}{{c}}{{\config{{clip}}}}",
    ])
    summary_second_header = "\n& ".join(
        ["", "", r"$\sizethreshold_\mathrm{heur.}$", "Tightest"]
        + [rf"$\resolution={resolution}$" for resolution in summary_clipping_resolutions]
        + ["Tightest"]
    )
    summary_header = summary_first_header + r"\\" + "\n" + summary_second_header
    summary_column_spec = (
        rf"{summary_model_column}@{{\hspace{{0.5pt}}}}{summary_objective_column}"
        + f" | {summary_result_column}" * 6
    )

    for property_type, direction, filename_suffix in objective_tables:
        summary_rows = [[]]
        for benchmark in benchmarks.INSTANCES:
            if (benchmark["property"]["type"] != property_type or
                    benchmark["property"]["dir"] != direction):
                continue
            inst_id = benchmark["id"]
            if inst_id not in benchmark_instances:
                continue
            cut_best_id = f"cut-best-in-{timelimit}s"
            clip_best_id = f"clip-best-in-{timelimit}s"
            best_ids = best_approximation_configs(
                exec_data,
                inst_id,
                [cut_best_id, clip_best_id],
                direction,
                approximation="under",
                maxtime=timelimit,
            )
            summary_rows.append([
                dissertation_model(benchmark_instances[inst_id]),
                dissertation_property(benchmark_instances[inst_id]),
                underapproximation_summary_cell(
                    exec_data, inst_id, heuristic_cutoff_id
                ),
                underapproximation_summary_best_cell(
                    exec_data, inst_id, "cut", timelimit, cut_best_id in best_ids
                ),
                *[
                    underapproximation_summary_cell(exec_data, inst_id, config_id)
                    for config_id in heuristic_clipping_ids
                ],
                underapproximation_summary_best_cell(
                    exec_data, inst_id, "clip", timelimit, clip_best_id in best_ids
                ),
            ])
        save_latex(
            summary_rows,
            summary_column_spec,
            summary_header,
            os.path.join(
                UNDERAPPROX_TABLE_DIR, f"tableunderapprox{filename_suffix}.tex"
            ),
            grid=True,
            tabcolsep="1pt",
            alternating_rows=True,
            arraystretch="0.72",
        )


def time_result_plot_series(exec_data, inst_id, cfgbase, start_time=0.01, end_time=3600):
    benchmark = benchmarks.from_id(inst_id)
    expected_relation = expected_bound_relation(cfgbase, benchmark)
    increasing = expected_relation == "≥"
    data = []
    for config in storm.CONFIGS:
        if not config["id"].startswith(cfgbase):
            continue
        result = get_result(exec_data, storm.NAME, config["id"], inst_id)
        if not is_successful_result(result):
            continue
        relation, value = parse_result_value(result["result"])
        if relation not in ["=", expected_relation]:
            raise ValueError(
                f"Expected a '{expected_relation}' bound, got '{result['result']}' in {result['id']}"
            )
        data.append((result["wallclock-time"], value))

    data.sort()
    if len(data) == 0:
        return []

    if benchmark["property"]["type"] == "prb":
        # Probability objectives have a trivial bound that is available before
        # any configuration finishes.
        initial_value = 0.0 if increasing else 1.0
        series = [(start_time, initial_value)]
        remaining_data = data
    else:
        # Do not make the first reward bound appear available before the run
        # that computed it has finished.
        first_runtime, first_value = data[0]
        series = [(first_runtime, first_value)]
        remaining_data = data[1:]

    for runtime, value in remaining_data:
        previous_value = series[-1][1]
        if increasing and previous_value >= value:
            continue
        if not increasing and previous_value <= value:
            continue
        # Keep the incumbent result until the improving run finishes, then
        # change vertically to the newly available result.
        series.append((runtime, previous_value))
        series.append((runtime, value))
    series.append((end_time, series[-1][1]))
    return series


def save_time_result_csv(exec_data, benchmark_instances):
    header = []
    series_contents = []
    for cfgbase in ["cut", "clip", "discr"]:
        for benchmark in benchmarks.INSTANCES:
            inst_id = benchmark["id"]
            if inst_id not in benchmark_instances:
                continue
            series_name = f"{cfgbase}.{inst_id}"
            header.extend([f"{series_name}.time", f"{series_name}.result"])
            series_contents.append(time_result_plot_series(exec_data, inst_id, cfgbase))

    table = [header]
    num_rows = max((len(series) for series in series_contents), default=0)
    for row_index in range(num_rows):
        row = []
        for series in series_contents:
            row.extend(series[row_index] if row_index < len(series) else ["", ""])
        table.append(row)
    save_csv(table, os.path.join(OUT_DIR, "time_result.csv"))

    os.makedirs(TIME_RESULT_PLOT_DIR, exist_ok=True)
    preview_inputs = []
    for benchmark in benchmarks.INSTANCES:
        inst_id = benchmark["id"]
        if inst_id not in benchmark_instances:
            continue
        plot = ["% Generated by scripts/postprocess.py.\n", LATEX_PLOT_BEGIN,
                r"\begin{tikzpicture}" + "\n" + r"\begin{axis}[" + "\n",
                LATEX_INSTANCE_PLOT_OPTIONS,
                r"unbounded coords=discard,xmin=0.01,xmax=3600,xmode=log," + "\n"]
        if benchmark["property"]["type"] == "prb":
            plot.append("ymin=0,ymax=1.04,\n")
        plot.extend([
            r"xlabel=time (seconds),ylabel=value bounds," + "\n",
            r"title={\texttt{\detokenize{" + inst_id + r"}}},title style={font=\tiny,yshift=24pt}," + "\n",
            r"log ticks with fixed point,scaled x ticks=false," + "\n", "]\n",
        ])
        for cfgbase, style in [
            ("cut", "plotcut,mark=o"),
            ("clip", "plotclip,mark=star"),
            ("discr", "plotdiscr,mark=triangle"),
        ]:
            series = time_result_plot_series(exec_data, inst_id, cfgbase)
            coordinates = " ".join(f"({runtime},{value})" for runtime, value in series)
            plot.append(r"\addplot[" + style + r",mark repeat=2,mark phase=2] coordinates {" + coordinates + "};\n")
        plot.extend([r"\legend{\config{cut},\config{clip},\config{discr}}" + "\n",
                     LATEX_INSTANCE_PLOT_END, "\\endgroup\n"])
        filename = f"time_result-{inst_id}.tex"
        with open(os.path.join(TIME_RESULT_PLOT_DIR, filename), "w") as plot_file:
            plot_file.write("".join(plot))
        preview_inputs.append(f"\\input{{general-plots/time-result/{filename}}}\n")
    with open(os.path.join(TIME_RESULT_PLOT_DIR, "time_result_preview.tex"), "w") as preview:
        preview.write("% Preview index: each plot is stored in a separate file.\n")
        preview.writelines(preview_inputs)


def save_time_budget_improvement_csv(
    exec_data,
    benchmark_instances,
    accounting="incremental",
    start_time=0.01,
    end_time=3600,
):
    """Export how many instances match or tighten their MDP bound over time.

    A discretisation result is available after both it and the MDP baseline
    have completed. With sequential accounting their wall-clock times are
    added; ``incremental`` counts only the extra discretisation time, while
    ``parallel`` takes their maximum.

    Values are compared at precision 10^-6, matching the generated
    dissertation tables. Each event is emitted twice (before and after the
    update), so an ordinary PGFPlots line produces an exact step curve.
    """
    if accounting not in ["incremental", "parallel", "sequential"]:
        raise ValueError(f"Unknown time-budget accounting mode: {accounting}")

    def reported_value(result):
        _, value = parse_result_value(result["result"])
        return comparison_value(value)

    def completion_time(discretisation, mdp):
        discretisation_time = discretisation["wallclock-time"]
        mdp_time = mdp["wallclock-time"]
        if accounting == "incremental":
            return discretisation_time
        if accounting == "parallel":
            return max(discretisation_time, mdp_time)
        return discretisation_time + mdp_time

    discretisation_ids = [
        config["id"]
        for config in storm.CONFIGS
        if config.get("family") == "discretisation"
    ]
    runs = OrderedDict()
    event_times = set()

    for benchmark in benchmarks.INSTANCES:
        inst_id = benchmark["id"]
        if inst_id not in benchmark_instances:
            continue
        mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
        if not is_successful_result(mdp):
            continue

        instance_runs = []
        for config_id in discretisation_ids:
            result = get_result(exec_data, storm.NAME, config_id, inst_id)
            if not is_successful_result(result):
                continue
            runtime = completion_time(result, mdp)
            instance_runs.append((runtime, reported_value(result)))
            event_times.add(runtime)
        runs[inst_id] = instance_runs

    def counts_at(budget):
        available = 0
        at_least_as_tight = 0
        strictly_tighter = 0
        for inst_id, instance_runs in runs.items():
            completed_values = [
                value for runtime, value in instance_runs if runtime <= budget
            ]
            if len(completed_values) == 0:
                continue
            available += 1

            benchmark = benchmarks.from_id(inst_id)
            mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
            mdp_value = reported_value(mdp)
            if benchmark["property"]["dir"] == "max":
                at_least_as_tight += min(completed_values) <= mdp_value
                strictly_tighter += min(completed_values) < mdp_value
            else:
                at_least_as_tight += max(completed_values) >= mdp_value
                strictly_tighter += max(completed_values) > mdp_value
        return available, at_least_as_tight, strictly_tighter

    total = len(runs)
    header = [
        "time",
        "available",
        "at-least-as-tight",
        "strictly-tighter",
    ]
    table = [header]

    def append_row(runtime, available, at_least_as_tight, strictly_tighter):
        table.append([
            runtime,
            available,
            at_least_as_tight,
            strictly_tighter,
        ])

    previous_available = 0
    previous_at_least_as_tight = 0
    previous_strictly_tighter = 0
    append_row(start_time, previous_available, previous_at_least_as_tight, previous_strictly_tighter)
    for runtime in sorted(event_times):
        append_row(runtime, previous_available, previous_at_least_as_tight, previous_strictly_tighter)
        previous_available, previous_at_least_as_tight, previous_strictly_tighter = counts_at(runtime)
        append_row(runtime, previous_available, previous_at_least_as_tight, previous_strictly_tighter)
    append_row(
        max(end_time, max(event_times, default=end_time)),
        previous_available,
        previous_at_least_as_tight,
        previous_strictly_tighter,
    )

    save_csv(
        table,
        os.path.join(OUT_DIR, f"time_budget_improvement_{accounting}.csv"),
    )

    accounting_label = {
        "incremental": "Discretisation time budget (seconds)",
        "parallel": "Parallel time budget (seconds)",
        "sequential": "Sequential time budget (seconds)",
    }[accounting]
    plot = r"""% Generated by scripts/postprocess.py.
\begin{tikzpicture}
\begin{axis}[
    width=\dimexpr\linewidth-6mm\relax,
    height=4.5cm,
    xmode=log,
    xmin=0.01,
    xmax=3600,
    ymin=0,
    ymax=@TOTAL@,
    ytick={0,5,10,15,20,25,30,35,@TOTAL@},
    xlabel={@ACCOUNTING_LABEL@},
    ylabel={Benchmark instances},
    log ticks with fixed point,
    scaled x ticks=false,
    every axis plot/.append style={thick,no marks},
]
\addplot[color=RWTHblue]
table[
    x=time,
    y=at-least-as-tight,
    col sep=tab,
] {@CSV_FILE@};
\addlegendentry{At least as tight as MDP}
\addplot[color=RWTHbordeaux,dashed]
table[x=time,y=strictly-tighter,col sep=tab]{@CSV_FILE@};
\addlegendentry{Strictly tighter}
\end{axis}
\end{tikzpicture}
"""
    plot = plot.replace("@ACCOUNTING_LABEL@", accounting_label)
    plot = plot.replace("@CSV_FILE@", f"time_budget_improvement_{accounting}.csv")
    plot = plot.replace("@TOTAL@", str(total))
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    with open(os.path.join(GENERAL_PLOT_DIR, "time_budget_improvement_plot.tex"), "w") as plot_file:
        plot_file.write(embed_plot_data(plot, {f"time_budget_improvement_{accounting}.csv": table}))


def save_resolution_result_csv(exec_data, benchmark_instances):
    """Export discretisation bounds by resolution for static and dynamic mode."""
    modes = [("s", "static"), ("d", "dynamic")]
    included_benchmarks = [
        benchmark for benchmark in benchmarks.INSTANCES
        if benchmark["id"] in benchmark_instances
    ]
    header = ["resolution"]
    for benchmark in included_benchmarks:
        inst_id = benchmark["id"]
        for _, mode_name in modes:
            header.extend([
                f"{mode_name}.{inst_id}.result",
                f"{mode_name}.{inst_id}.time",
                f"{mode_name}.{inst_id}.states",
            ])
        header.extend([f"mdp.{inst_id}.result", f"mdp.{inst_id}.time"])

    table = [header]
    for resolution in range(2, 13):
        row = [resolution]
        for benchmark in included_benchmarks:
            inst_id = benchmark["id"]
            expected_relation = expected_bound_relation("discr", benchmark)
            for mode_id, _ in modes:
                result = get_result(
                    exec_data, storm.NAME, f"discr{resolution:03}{mode_id}", inst_id
                )
                if not is_successful_result(result):
                    row.extend(["nan", "nan", "nan"])
                    continue
                relation, value = parse_result_value(result["result"])
                if relation not in ["=", expected_relation]:
                    raise ValueError(
                        f"Expected a '{expected_relation}' bound, got "
                        f"'{result['result']}' in {result['id']}"
                    )
                states = result.get("belief-mdp", {}).get("states", "nan")
                row.extend([value, result["wallclock-time"], states])
            mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
            row.extend([
                parse_result_value(mdp["result"])[1] if is_successful_result(mdp) else "nan",
                mdp["wallclock-time"] if is_successful_result(mdp) else "nan",
            ])
        table.append(row)
    save_csv(table, os.path.join(OUT_DIR, "resolution_result.csv"))

    save_resolution_instance_plots(table, included_benchmarks)


def save_resolution_instance_plots(table, included_benchmarks):
    """Write one self-contained value and runtime plot per benchmark."""
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    header = table[0]
    for metric, filename_metric, preview_filename in [
        ("result", "value", "resolution_value_preview.tex"),
        ("time", "time", "resolution_time_preview.tex"),
    ]:
        plot_dir = RESOLUTION_TIME_PLOT_DIR if metric == "time" else RESOLUTION_VALUE_PLOT_DIR
        os.makedirs(plot_dir, exist_ok=True)
        preview_inputs = ["% Preview index: each plot is stored in a separate file.\n"]
        for plot_index, benchmark in enumerate(included_benchmarks):
            inst_id = benchmark["id"]
            plot = [
                "% Generated by scripts/postprocess.py. Requires pgfplots (compat=1.18).\n",
                LATEX_PLOT_BEGIN,
                r"\begin{tikzpicture}" + "\n" + r"\begin{axis}[" + "\n",
                "width=7cm,height=4.5cm,\n" + LATEX_PLOT_OPTIONS,
                r"xmin=2,xmax=12,xtick={2,4,6,8,10,12},unbounded coords=jump," + "\n",
                r"xlabel=resolution $\eta$," + "\n",
                r"title={\texttt{\detokenize{" + inst_id + r"}}},title style={font=\tiny,yshift=24pt}," + "\n",
            ]
            if metric == "time":
                plot.append(r"ylabel={time (seconds)},ymode=log,log ticks with fixed point,scaled y ticks=false," + "\n")
            else:
                plot.append(r"ylabel={value bounds},enlarge y limits=0.08,scaled y ticks=false," + "\n")
                plot.append(r"yticklabel style={font=\small,/pgf/number format/fixed relative,/pgf/number format/precision=5}," + "\n")
            plot.append("]\n")
            for mode, style, label in [
                ("static", "plotdiscr,mark=o", "static"),
                ("dynamic", "plotclip,mark=triangle", "dynamic"),
                ("mdp", "black!60,dashed,no marks", r"\config{mdp}"),
            ]:
                value_index = header.index(f"{mode}.{inst_id}.{metric}")
                series_table = [["resolution", metric]] + [[row[0], row[value_index]] for row in table[1:]]
                plot.append(r"\addplot[" + style + r"] table[x=resolution,y=" + metric + r",col sep=space,row sep=\\]{" + latex_plot_table(series_table) + "};\n")
                plot.append(r"\addlegendentry{" + label + "}\n")
            plot.extend([LATEX_INSTANCE_PLOT_END, "\\endgroup\n"])
            contents = "".join(plot)
            filename = f"resolution_{filename_metric}-{inst_id}.tex"
            with open(os.path.join(plot_dir, filename), "w") as plot_file:
                plot_file.write(contents)
            folder = "resolution-time" if metric == "time" else "resolution-value"
            preview_inputs.append(f"\\input{{general-plots/{folder}/{filename}}}\n")
        with open(os.path.join(plot_dir, preview_filename), "w") as preview:
            preview.writelines(preview_inputs)


def save_resolution_overview_csv(exec_data, benchmark_instances):
    """Compare discretisation resolutions using only the MDP as baseline."""
    modes = [("s", "static"), ("d", "dynamic")]

    def reported_value(result):
        value = parse_result_value(result["result"])[1]
        return comparison_value(value)

    def directional_gain(direction, baseline, candidate):
        return baseline - candidate if direction == "max" else candidate - baseline

    def quantile(values, probability):
        values = sorted(values)
        if len(values) == 0:
            return "nan"
        position = probability * (len(values) - 1)
        lower_index, upper_index = math.floor(position), math.ceil(position)
        if lower_index == upper_index:
            return values[lower_index]
        fraction = position - lower_index
        return values[lower_index] * (1 - fraction) + values[upper_index] * fraction

    instances = OrderedDict()
    for benchmark in benchmarks.INSTANCES:
        inst_id = benchmark["id"]
        if inst_id not in benchmark_instances:
            continue
        mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
        if not is_successful_result(mdp):
            continue
        direction = benchmark["property"]["dir"]
        mdp_value = reported_value(mdp)
        observed_values = []
        for resolution in range(2, 13):
            for mode_id, _ in modes:
                result = get_result(
                    exec_data, storm.NAME, f"discr{resolution:03}{mode_id}", inst_id
                )
                if is_successful_result(result):
                    observed_values.append(reported_value(result))
        best_value = (min if direction == "max" else max)(observed_values, default=mdp_value)
        best_gain = directional_gain(direction, mdp_value, best_value)
        instances[inst_id] = (direction, mdp_value, best_gain)

    progress_header = ["resolution"]
    for _, mode_name in modes:
        progress_header.extend([
            f"{mode_name}-q25",
            f"{mode_name}-median",
            f"{mode_name}-q75",
            f"{mode_name}-median-time",
        ])
    progress_table = [progress_header]
    outcomes_table = [[
        "plot-x", "resolution", "mode", "strict", "tie", "unavailable", "worse"
    ]]
    cumulative_table = [["resolution", "static", "dynamic"]]
    interval_header = ["plot-x", "resolution", "minimum", "q25", "median", "q75",
                       "maximum", "successful", "failed", "not-run"]
    interval_tables = {mode_name: [interval_header] for _, mode_name in modes}
    coverage_table = [["plot-x", "resolution", "mode", "successful", "failed", "not-run"]]
    first_improving_resolution = {mode_name: {} for _, mode_name in modes}

    for resolution in range(2, 13):
        progress_row = [resolution]
        for mode_index, (mode_id, mode_name) in enumerate(modes):
            progress = []
            runtimes = []
            counts = Counter()
            iqr_counts = Counter()
            for inst_id, (direction, mdp_value, best_gain) in instances.items():
                result = get_result(
                    exec_data, storm.NAME, f"discr{resolution:03}{mode_id}", inst_id
                )
                if not is_successful_result(result):
                    counts["unavailable"] += 1
                    if best_gain > 0:
                        iqr_counts["not-run" if result is None else "failed"] += 1
                    continue
                runtimes.append(result["wallclock-time"])
                candidate = reported_value(result)
                gain = directional_gain(direction, mdp_value, candidate)
                if gain > 0:
                    counts["strict"] += 1
                    first_improving_resolution[mode_name].setdefault(inst_id, resolution)
                elif gain == 0:
                    counts["tie"] += 1
                else:
                    counts["worse"] += 1
                if best_gain > 0:
                    iqr_counts["successful"] += 1
                    progress.append(max(0, min(100, 100 * gain / best_gain)))

            progress_row.extend([
                quantile(progress, 0.25),
                quantile(progress, 0.5),
                quantile(progress, 0.75),
                quantile(runtimes, 0.5),
            ])
            plot_x = resolution + (-0.18 if mode_index == 0 else 0.18)
            q25, median, q75 = [quantile(progress, fraction) for fraction in (0.25, 0.5, 0.75)]
            interval_tables[mode_name].append([
                plot_x, resolution, min(progress, default="nan"), q25, median, q75,
                max(progress, default="nan"),
                iqr_counts["successful"], iqr_counts["failed"], iqr_counts["not-run"],
            ])
            coverage_table.append([
                plot_x, resolution, mode_name,
                iqr_counts["successful"], iqr_counts["failed"], iqr_counts["not-run"],
            ])
            outcomes_table.append([
                plot_x, resolution, mode_name, counts["strict"], counts["tie"],
                counts["unavailable"], counts["worse"],
            ])
        progress_table.append(progress_row)
        cumulative_table.append([
            resolution,
            sum(value <= resolution for value in first_improving_resolution["static"].values()),
            sum(value <= resolution for value in first_improving_resolution["dynamic"].values()),
        ])

    save_csv(progress_table, os.path.join(OUT_DIR, "resolution_progress.csv"))
    save_csv(outcomes_table, os.path.join(OUT_DIR, "resolution_outcomes.csv"))
    save_csv(cumulative_table, os.path.join(OUT_DIR, "minimum_improving_resolution.csv"))

    for mode_name, table in interval_tables.items():
        save_csv(table, os.path.join(OUT_DIR, f"resolution_iqr_{mode_name}.csv"))
    save_csv(coverage_table, os.path.join(OUT_DIR, "resolution_iqr_coverage.csv"))

    total = len(instances)
    boxplots = []
    for mode_name, color in [("static", "RWTHblue"), ("dynamic", "RWTHbordeaux")]:
        for row in interval_tables[mode_name][1:]:
            x, _, minimum, q25, median, q75, maximum, successful, _, _ = row
            if not successful:
                continue
            boxplots.append(
                r"\addplot[draw=" + color + ",fill=" + color + r"!20,forget plot,"
                + r"boxplot/draw direction=y,boxplot/box extend=0.24,boxplot prepared={"
                + f"draw position={x},lower whisker={minimum},lower quartile={q25},"
                + f"median={median},upper quartile={q75},upper whisker={maximum}"
                + r"}] coordinates {};" + "\n"
            )
        boxplots.append(r"\addlegendimage{area legend,draw=" + color + ",fill=" + color + "!20}\n")
        boxplots.append(r"\addlegendentry{" + mode_name + "}\n")

    overview_plot = r"""% Generated by scripts/postprocess.py.
% Preamble also requires \usepgfplotslibrary{statistics}.
\begin{tikzpicture}
\begin{axis}[width=\dimexpr\linewidth-6mm\relax,height=4.5cm,
xmin=1.5,xmax=12.5,xtick={2,3,4,5,6,7,8,9,10,11,12},
ymin=-3,ymax=105,ytick={0,25,50,75,100},ylabel={Improvement reached (\%)},
xlabel={resolution $\eta$ (left: static; right: dynamic)},legend columns=2]
@BOXPLOTS@
\end{axis}
\end{tikzpicture}
"""
    overview_plot = overview_plot.replace("@BOXPLOTS@", "".join(boxplots))
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    with open(os.path.join(GENERAL_PLOT_DIR, "resolution_overview_plot.tex"), "w") as plot_file:
        plot_file.write(style_latex_plot(overview_plot))

    cumulative_plot = r"""% Generated by scripts/postprocess.py.
\begin{tikzpicture}
\begin{axis}[
width=\dimexpr\linewidth-6mm\relax,height=4.5cm,xmin=2,xmax=12,ymin=0,ymax=@TOTAL@,
xtick={2,3,4,5,6,7,8,9,10,11,12},ytick={0,10,20,30,@TOTAL@},
xlabel={resolution threshold $\eta$},ylabel={Improving benchmarks},
legend columns=2]
\addplot[RWTHblue,thick,mark=o] table[x=resolution,y=static,col sep=tab]{minimum_improving_resolution.csv};
\addlegendentry{static}
\addplot[RWTHbordeaux,thick,mark=triangle] table[x=resolution,y=dynamic,col sep=tab]{minimum_improving_resolution.csv};
\addlegendentry{dynamic}
\end{axis}
\end{tikzpicture}
""".replace("@TOTAL@", str(total))
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    with open(os.path.join(GENERAL_PLOT_DIR, "minimum_improving_resolution_plot.tex"), "w") as plot_file:
        plot_file.write(embed_plot_data(cumulative_plot, {"minimum_improving_resolution.csv": cumulative_table}))


def save_discretisation_mode_comparison_csv(
    exec_data,
    benchmark_instances,
    runtime_tolerance=0.05,
):
    """Classify the static/dynamic quality-runtime tradeoff by resolution."""
    if not 0 <= runtime_tolerance < 1:
        raise ValueError("runtime_tolerance must lie in [0, 1)")

    def reported_value(result):
        value = parse_result_value(result["result"])[1]
        return comparison_value(value)

    included_benchmarks = [
        benchmark for benchmark in benchmarks.INSTANCES
        if benchmark["id"] in benchmark_instances
    ]
    header = [
        "resolution",
        "dynamic-better",
        "static-better",
        "equal-result",
        "dynamic-faster",
        "static-faster",
        "similar-runtime",
        "dynamic-dominates",
        "static-dominates",
        "tradeoff",
        "equivalent",
        "unavailable",
        "dynamic-better-and-faster",
        "static-better-and-faster",
    ]
    table = [header]
    paired_bar_table = [[
        "plot-x", "resolution", "metric",
        "dynamic", "static", "equal-or-similar", "unavailable",
    ]]

    for resolution in range(2, 13):
        counts = Counter()
        for benchmark in included_benchmarks:
            inst_id = benchmark["id"]
            static = get_result(
                exec_data, storm.NAME, f"discr{resolution:03}s", inst_id
            )
            dynamic = get_result(
                exec_data, storm.NAME, f"discr{resolution:03}d", inst_id
            )
            if not is_successful_result(static) or not is_successful_result(dynamic):
                counts["unavailable"] += 1
                continue

            static_value = reported_value(static)
            dynamic_value = reported_value(dynamic)
            direction = benchmark["property"]["dir"]
            if static_value == dynamic_value:
                quality = "equivalent"
            elif ((direction == "max" and dynamic_value < static_value)
                  or (direction == "min" and dynamic_value > static_value)):
                quality = "dynamic"
            else:
                quality = "static"
            counts[f"quality-{quality}"] += 1

            static_time = static["wallclock-time"]
            dynamic_time = dynamic["wallclock-time"]
            if dynamic_time < (1 - runtime_tolerance) * static_time:
                speed = "dynamic"
            elif static_time < (1 - runtime_tolerance) * dynamic_time:
                speed = "static"
            else:
                speed = "equivalent"
            counts[f"speed-{speed}"] += 1

            if quality == "dynamic" and speed == "dynamic":
                counts["dynamic-better-and-faster"] += 1
            elif quality == "static" and speed == "static":
                counts["static-better-and-faster"] += 1

            if (quality in ["dynamic", "equivalent"]
                    and speed in ["dynamic", "equivalent"]
                    and (quality == "dynamic" or speed == "dynamic")):
                counts["dynamic-dominates"] += 1
            elif (quality in ["static", "equivalent"]
                    and speed in ["static", "equivalent"]
                    and (quality == "static" or speed == "static")):
                counts["static-dominates"] += 1
            elif quality == "equivalent" and speed == "equivalent":
                counts["equivalent"] += 1
            else:
                counts["tradeoff"] += 1

        table.append([
            resolution,
            counts["quality-dynamic"],
            counts["quality-static"],
            counts["quality-equivalent"],
            counts["speed-dynamic"],
            counts["speed-static"],
            counts["speed-equivalent"],
            counts["dynamic-dominates"],
            counts["static-dominates"],
            counts["tradeoff"],
            counts["equivalent"],
            counts["unavailable"],
            counts["dynamic-better-and-faster"],
            counts["static-better-and-faster"],
        ])
        paired_bar_table.extend([
            [resolution - 0.19, resolution, "bound",
             counts["quality-dynamic"], counts["quality-static"],
             counts["quality-equivalent"], counts["unavailable"]],
            [resolution + 0.19, resolution, "runtime",
             counts["speed-dynamic"], counts["speed-static"],
             counts["speed-equivalent"], counts["unavailable"]],
        ])

    save_csv(table, os.path.join(OUT_DIR, "discretisation_mode_comparison.csv"))
    save_csv(
        paired_bar_table,
        os.path.join(OUT_DIR, "discretisation_mode_comparison_bars.csv"),
    )

    total = len(included_benchmarks)
    plot = r"""% Generated by scripts/postprocess.py.
\begin{tikzpicture}
\begin{axis}[
    width=\dimexpr\linewidth-6mm\relax,
    height=4.5cm,
    ybar stacked,
    bar width=5.5pt,
    xmin=1.5,
    xmax=12.5,
    ymin=0,
    ymax=@TOTAL@,
    xtick={2,3,4,5,6,7,8,9,10,11,12},
    ytick={0,10,20,30,@TOTAL@},
    xlabel={resolution $\eta$ (left: bound; right: runtime)},
    ylabel={Benchmark instances},
    legend columns=2,
]
\addplot[fill=RWTHbordeaux,draw=none]
table[x=plot-x,y=dynamic,col sep=tab]{discretisation_mode_comparison_bars.csv};
\addlegendentry{dynamic better / faster}
\addplot[fill=RWTHblue,draw=none]
table[x=plot-x,y=static,col sep=tab]{discretisation_mode_comparison_bars.csv};
\addlegendentry{static better / faster}
\addplot[fill=black!12,draw=none]
table[x=plot-x,y=equal-or-similar,col sep=tab]{discretisation_mode_comparison_bars.csv};
\addlegendentry{equal / similar}
\addplot[fill=black!45,draw=none]
table[x=plot-x,y=unavailable,col sep=tab]{discretisation_mode_comparison_bars.csv};
\addlegendentry{no comparison}
\end{axis}
\end{tikzpicture}
"""
    plot = plot.replace("@TOTAL@", str(total))
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    with open(os.path.join(GENERAL_PLOT_DIR, "discretisation_mode_comparison_plot.tex"), "w") as plot_file:
        plot_file.write(embed_plot_data(plot, {"discretisation_mode_comparison_bars.csv": paired_bar_table}))

    tolerance_percent = 100 * runtime_tolerance
    strict_plot = r"""% Generated by scripts/postprocess.py.
\begin{tikzpicture}
\begin{axis}[
    width=\dimexpr\linewidth-6mm\relax,
    height=4.5cm,
    ybar,
    bar width=8pt,
    xmin=1.5,
    xmax=12.5,
    ymin=0,
    ymax=12,
    xtick={2,3,4,5,6,7,8,9,10,11,12},
    ytick={0,2,4,6,8,10,12},
    xlabel={resolution $\eta$},
    ylabel={Benchmark instances},
    legend columns=2,
    title={Strict quality--runtime wins (@TOLERANCE@\% runtime tolerance)},
    title style={font=\small,yshift=30pt},
]
\addplot[fill=RWTHbordeaux,draw=none]
table[x=resolution,y=dynamic-better-and-faster,col sep=tab]{discretisation_mode_comparison.csv};
\addlegendentry{dynamic tighter and faster}
\addplot[fill=RWTHblue,draw=none]
table[x=resolution,y=static-better-and-faster,col sep=tab]{discretisation_mode_comparison.csv};
\addlegendentry{static tighter and faster}
\end{axis}
\end{tikzpicture}
""".replace("@TOLERANCE@", f"{tolerance_percent:g}")
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)
    with open(os.path.join(GENERAL_PLOT_DIR, "discretisation_mode_joint_wins_plot.tex"), "w") as plot_file:
        plot_file.write(embed_plot_data(strict_plot, {"discretisation_mode_comparison.csv": table}))


def plot_quantile(values, probability):
    """Linearly interpolate an empirical quantile, as in the improvement plot."""
    values = sorted(values)
    position = probability * (len(values) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def prepared_boxplot(values, position, color):
    """Use min/max whiskers, retaining all successful observations."""
    if not values:
        return ""
    return (
        r"\addplot[draw=" + color + ",fill=" + color + r"!20,forget plot,"
        + r"boxplot/draw direction=y,boxplot/box extend=0.24,boxplot prepared={"
        + f"draw position={position},lower whisker={min(values)},"
        + f"lower quartile={plot_quantile(values, 0.25)},median={plot_quantile(values, 0.5)},"
        + f"upper quartile={plot_quantile(values, 0.75)},upper whisker={max(values)}"
        + r"}] coordinates {};" + "\n"
    )


def save_discretisation_question_plots(exec_data, benchmark_instances, timelimit=1800):
    """Generate bound, resolution-runtime, and paired mode-runtime comparisons.

    Failed runs are excluded from numeric distributions and reported separately.
    The bound comparison selects the tightest successful run within timelimit,
    across both modes and all resolutions, breaking rounded-value ties by time.
    """
    included = [b for b in benchmarks.INSTANCES if b["id"] in benchmark_instances]
    os.makedirs(GENERAL_PLOT_DIR, exist_ok=True)

    def write_plot(filename, plot):
        path = os.path.join(GENERAL_PLOT_DIR, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as plot_file:
            plot_file.write(style_latex_plot(plot))

    def axis_plot(options, body):
        return ("% Generated by scripts/postprocess.py.\n"
                + r"\begin{tikzpicture}\begin{axis}[" + LATEX_SCATTER_OPTIONS
                + options + "]\n" + body + r"\end{axis}\end{tikzpicture}" + "\n")

    def legend_plot(entries, columns=2):
        body = [r"\begin{tikzpicture}\begin{axis}[hide axis,scale only axis,width=0pt,height=0pt,xmin=0,xmax=1,ymin=0,ymax=1,"
                + f"legend columns={columns},legend style={{draw=black,at={{(0,0)}},anchor=center}}]" + "\n"]
        for image_options, label in entries:
            body.append(r"\addlegendimage{" + image_options + "}\n"
                        + r"\addlegendentry{" + label + "}\n")
        body.append(r"\end{axis}\end{tikzpicture}" + "\n")
        return "".join(body)

    def scatter(table, color, mark="o"):
        return (r"\addplot[only marks,color=" + color + ",mark=" + mark
                + r",mark options={fill=none},mark size=1.5pt,line width=0.4pt] table[x=x,y=y,col sep=space,row sep=\\]{"
                + latex_plot_table(table) + "};\n")

    bound_data = [["instance", "objective", "mdp", "discretisation", "configuration", "time", "status"]]
    bound_preview = ["% Preview index: separate panel and legend files.\n",
                     "\\input{general-plots/mdp-discretisation/legend.tex}\\par\\medskip\n"]
    for property_type, title in [("prb", "Probability"), ("rew", "Reward")]:
        points = {direction: [["x", "y"]] for direction in ("min", "max")}
        for direction in ("min", "max"):
            group = [b for b in included if b["property"]["type"] == property_type
                     and b["property"]["dir"] == direction]
            for benchmark in group:
                inst_id = benchmark["id"]
                mdp = get_result(exec_data, storm.NAME, "mdp", inst_id)
                candidates = []
                for resolution in range(2, 13):
                    for mode in "sd":
                        config_id = f"discr{resolution:03}{mode}"
                        result = get_result(exec_data, storm.NAME, config_id, inst_id)
                        if is_successful_result(result, timelimit):
                            value = comparison_value(parse_result_value(result["result"])[1])
                            candidates.append((value if direction == "max" else -value,
                                               result["wallclock-time"], config_id, result))
                if not is_successful_result(mdp) or not candidates:
                    status = "no-baseline" if not is_successful_result(mdp) else "no-result-within-budget"
                    bound_data.append([inst_id, property_type + direction, "nan", "nan", "none", "nan", status])
                    continue
                _, runtime, config_id, result = min(candidates, key=lambda entry: entry[:3])
                baseline = parse_result_value(mdp["result"])[1]
                candidate = parse_result_value(result["result"])[1]
                points[direction].append([baseline, candidate])
                bound_data.append([inst_id, property_type + direction, baseline, candidate, config_id, runtime, "paired"])
        count = sum(len(table) - 1 for table in points.values())
        if property_type == "prb":
            lower, upper = 0, 1
            failure, axis_end = scatter_na_limits(lower, upper)
            ticks = [0, 0.25, 0.5, 0.75, 1, failure]
            labels = ["0", "0.25", "0.5", "0.75", "1", "n/a"]
            options = f"xmin=0,xmax={axis_end},ymin=0,ymax={axis_end},"
            for axis in ("x", "y"):
                options += axis + "tick={" + ",".join(map(str, ticks)) + "},"
                options += axis + "ticklabels={" + ",".join(labels) + "},"
        else:
            values = [value for table in points.values() for row in table[1:] for value in row]
            lower = 10 ** math.floor(math.log10(min(values))) if values else 1
            upper = 10 ** math.ceil(math.log10(max(values))) if values else 10
            if upper == lower:
                upper *= 10
            failure, axis_end = scatter_na_limits(lower, upper, logarithmic=True)
            options = f"xmode=log,ymode=log,xmin={lower},xmax={axis_end},ymin={lower},ymax={axis_end},"
            options += scatter_log_ticks(lower, upper, failure)
        panel = []
        for separator in [f"({upper},{lower}) ({upper},{axis_end})",
                          f"({lower},{upper}) ({axis_end},{upper})"]:
            panel.append(r"\addplot[black!35,thin,no marks,forget plot] coordinates {" + separator + "};\n")
        panel.append(r"\addplot[black,thin,no marks,forget plot] coordinates {" + f"({lower},{lower}) ({upper},{upper})" + "};\n")
        if property_type == "rew":
            for guide in [f"({lower},{2*lower}) ({upper/2},{upper})",
                          f"({2*lower},{lower}) ({upper},{upper/2})"]:
                panel.append(r"\addplot[black,densely dotted,thin,no marks,forget plot] coordinates {" + guide + "};\n")
        min_series = scatter(points["min"], "RWTHblue", "o")
        max_series = scatter(points["max"], "RWTHbordeaux", "triangle")
        no_legend = "".join(panel) + min_series + max_series
        with_legend = ("".join(panel) + min_series + r"\addlegendentry{Minimisation}" + "\n"
                       + max_series + r"\addlegendentry{Maximisation}" + "\n")
        # Two 58 mm panels fit the 121.45 mm B5 text block with a 5.45 mm gap.
        # Absolute sizes avoid being scaled a second time inside a subfigure.
        axis_options = (r"scale only axis=false,width=58mm,height=58mm,"
                        + r"xlabel={\config{mdp} bound},ylabel={\config{discr} bound},"
                        + r"title style={font=\small},scaled ticks=false,"
                        + f"title={{{title} ($n={count}$)}}," + options)
        slug = "probability" if property_type == "prb" else "reward"
        write_plot(f"mdp-discretisation/{slug}.tex", axis_plot(axis_options, with_legend))
        write_plot(f"mdp-discretisation/{slug}-no-legend.tex", axis_plot(axis_options, no_legend))
        bound_preview.append("\\begin{minipage}{0.48\\linewidth}\\centering\n"
                             + f"\\input{{general-plots/mdp-discretisation/{slug}-no-legend.tex}}\n"
                             + "\\end{minipage}"
                             + ("\\hfill\n" if property_type == "prb" else "\\par\\medskip\n"))
    write_plot("mdp-discretisation/legend.tex", legend_plot([
        ("only marks,color=RWTHblue,mark=o,mark options={fill=none},mark size=1.5pt", "Minimisation"),
        ("only marks,color=RWTHbordeaux,mark=triangle,mark options={fill=none},mark size=1.5pt", "Maximisation"),
    ]))
    with open(os.path.join(GENERAL_PLOT_DIR, "mdp-discretisation", "preview.tex"), "w") as preview:
        preview.writelines(bound_preview)
    save_csv(bound_data, os.path.join(OUT_DIR, "mdp_discretisation_bounds.csv"))

    runtime_plot = [r"""% Generated by scripts/postprocess.py.
% Preamble also requires \usepgfplotslibrary{statistics}.
\begin{tikzpicture}
\begin{axis}[width=\dimexpr\linewidth-6mm\relax,height=4.5cm,
xmin=1.5,xmax=12.5,xtick={2,3,4,5,6,7,8,9,10,11,12},
xlabel={resolution $\eta$ (left: static; right: dynamic)},
ymode=log,ylabel={Runtime (s)}]
"""]
    coverage = [["x", "successful", "failed", "not-run"]]
    runtime_data = [["instance", "resolution", "mode", "time", "status"]]
    for mode_index, (mode, name, color) in enumerate([("s", "static", "RWTHblue"), ("d", "dynamic", "RWTHbordeaux")]):
        for resolution in range(2, 13):
            times, counts = [], Counter()
            for benchmark in included:
                result = get_result(exec_data, storm.NAME, f"discr{resolution:03}{mode}", benchmark["id"])
                status = "successful" if is_successful_result(result) else ("not-run" if result is None else "failed")
                counts[status] += 1
                if status == "successful":
                    times.append(result["wallclock-time"])
                runtime_data.append([benchmark["id"], resolution, name,
                                     result.get("wallclock-time", "nan") if result else "nan", status])
            position = resolution + (-0.18 if mode_index == 0 else 0.18)
            runtime_plot.append(prepared_boxplot(times, position, color))
            coverage.append([position, counts["successful"], counts["failed"], counts["not-run"]])
        runtime_plot.append(r"\addlegendimage{area legend,draw=" + color + ",fill=" + color + "!20}\n"
                            + r"\addlegendentry{" + name + "}\n")
    runtime_plot.append(r"\end{axis}\end{tikzpicture}" + "\n")
    write_plot("resolution_runtime_boxplot.tex", "".join(runtime_plot))
    save_csv(runtime_data, os.path.join(OUT_DIR, "resolution_runtime_distribution.csv"))

    coverage_plot = [r"""% Generated by scripts/postprocess.py.
\begin{tikzpicture}
\begin{axis}[width=\dimexpr\linewidth-6mm\relax,height=4.5cm,
xmin=1.5,xmax=12.5,xtick={2,3,4,5,6,7,8,9,10,11,12},
xlabel={resolution $\eta$ (left: static; right: dynamic)},
ybar stacked,bar width=4pt,ymin=0,ymax=@TOTAL@,
ytick={0,10,20,30,@TOTAL@},ylabel={Instances},legend columns=2]
""".replace("@TOTAL@", str(len(included)))]
    for status, color in [("successful", "RWTHgreen!65"), ("failed", "orange!75"), ("not-run", "black!20")]:
        if status == "not-run" and not any(row[3] for row in coverage[1:]):
            continue
        coverage_plot.append(r"\addplot[fill=" + color + r",draw=none] table[x=x,y=" + status
                            + r",col sep=space,row sep=\\]{" + latex_plot_table(coverage) + "};\n"
                            + r"\addlegendentry{" + status + "}\n")
    coverage_plot.append(r"\end{axis}\end{tikzpicture}" + "\n")
    write_plot("resolution_run_outcomes_plot.tex", "".join(coverage_plot))
    save_csv(coverage, os.path.join(OUT_DIR, "resolution_run_outcomes.csv"))

    mode_numeric_max = 1000
    mode_na, mode_limit = scatter_na_limits(
        0.1, mode_numeric_max, logarithmic=True, gap_fraction=0.18
    )
    mode_data = [["instance", "resolution", "static-time", "dynamic-time", "status"]]
    mode_preview = ["% Preview index: separate panel and legend files.\n",
                    "\\input{general-plots/discretisation-mode-runtime/legend.tex}\\par\\medskip\n"]
    for resolution in (2, 5, 12):
        points = {kind: [["x", "y"]] for kind in ("prb", "rew")}
        for benchmark in included:
            inst_id = benchmark["id"]
            static = get_result(exec_data, storm.NAME, f"discr{resolution:03}s", inst_id)
            dynamic = get_result(exec_data, storm.NAME, f"discr{resolution:03}d", inst_id)
            successes = (is_successful_result(static), is_successful_result(dynamic))
            status = {(True, True): "paired", (True, False): "static-only",
                      (False, True): "dynamic-only", (False, False): "neither"}[successes]
            times = [result["wallclock-time"] if success else "nan"
                     for result, success in zip((static, dynamic), successes)]
            mode_data.append([inst_id, resolution, *times, status])
            # n/a is a display coordinate in a separate edge strip, never a runtime.
            display_times = [max(0.1, time) if success else mode_na
                             for time, success in zip(times, successes)]
            points[benchmark["property"]["type"]].append(display_times)
        panel = []
        for boundary in [
            f"({mode_numeric_max},0.1) ({mode_numeric_max},{mode_limit})",
            f"(0.1,{mode_numeric_max}) ({mode_limit},{mode_numeric_max})",
        ]:
            panel.append(r"\addplot[black!35,thin,no marks,forget plot] coordinates {" + boundary + "};\n")
        for guide, style in [
            (f"(0.1,0.1) ({mode_numeric_max},{mode_numeric_max})", "solid"),
            (f"(0.1,0.2) ({mode_numeric_max / 2:g},{mode_numeric_max})", "densely dotted"),
            (f"(0.2,0.1) ({mode_numeric_max},{mode_numeric_max / 2:g})", "densely dotted"),
        ]:
            panel.append(r"\addplot[black,thin," + style + r",no marks,forget plot] coordinates {" + guide + "};\n")
        probability = scatter(points["prb"], "RWTHblue", "o")
        reward = scatter(points["rew"], "RWTHbordeaux", "triangle")
        no_legend = "".join(panel) + probability + reward
        with_legend = ("".join(panel) + probability + r"\addlegendentry{Probability}" + "\n"
                       + reward + r"\addlegendentry{Reward}" + "\n")
        options = (scatter_log_ticks(0.1, mode_numeric_max, mode_na)
                   + f"xmode=log,ymode=log,xmin=0.1,xmax={mode_limit},ymin=0.1,ymax={mode_limit},"
                   # Three 38 mm panels leave 7.45 mm for two gaps in the B5 text block.
                   + r"scale only axis=false,width=38mm,height=38mm,"
                   + r"xticklabel style={font=\scriptsize},yticklabel style={font=\scriptsize},"
                   + r"x label style={font=\scriptsize,yshift=0pt},"
                   + r"y label style={font=\scriptsize,yshift=0pt},"
                   + r"xlabel={Static (s)},ylabel={Dynamic (s)},title style={font=\small},"
                   + rf"title={{Resolution $\eta={resolution}$}}")
        write_plot(f"discretisation-mode-runtime/resolution-{resolution}.tex", axis_plot(options, with_legend))
        write_plot(f"discretisation-mode-runtime/resolution-{resolution}-no-legend.tex", axis_plot(options, no_legend))
        mode_preview.append("\\begin{minipage}{0.32\\linewidth}\\centering\n"
                            + f"\\input{{general-plots/discretisation-mode-runtime/resolution-{resolution}-no-legend.tex}}\n"
                            + "\\end{minipage}"
                            + ("\\par\\medskip\n" if resolution == 12 else "\\hfill\n"))
    write_plot("discretisation-mode-runtime/legend.tex", legend_plot([
        ("only marks,color=RWTHblue,mark=o,mark options={fill=none},mark size=1.5pt", "Probability"),
        ("only marks,color=RWTHbordeaux,mark=triangle,mark options={fill=none},mark size=1.5pt", "Reward"),
    ]))
    with open(os.path.join(GENERAL_PLOT_DIR, "discretisation-mode-runtime", "preview.tex"), "w") as preview:
        preview.writelines(mode_preview)
    save_csv(mode_data, os.path.join(OUT_DIR, "discretisation_mode_runtime_pairs.csv"))


def save_underapproximation_question_outputs(exec_data, benchmark_instances, timelimit=1800):
    from underapprox_visuals import save_outputs
    save_outputs(sys.modules[__name__], exec_data, benchmark_instances, timelimit)


def export_data(exec_data, benchmark_instances, export_kinds, prefix=""):
    SCATTER_MIN_VALUE, SCATTER_MAX_VALUE = 1, 1000
    QUANTILE_MIN_VALUE = 1

    def scatter_special_value(i): return round(SCATTER_MAX_VALUE * (math.sqrt(2)**i))


    def get_instances_num_supported(cfgs):
        res = Counter()
        for b_id in benchmark_instances:
            res[b_id] = len([c for c in cfgs if get_result_if_supported(exec_data, c[0], c[1], b_id) is not None])
        return res

    def get_instances_supported_by_some(cfgs):
        return [i[0] for i in get_instances_num_supported(cfgs).items() if i[1] > 0]

    def get_instances_supported_by_all(cfgs):
        return [i[0] for i in get_instances_num_supported(cfgs).items() if i[1] == len(cfgs)]

    def to_html(text):
        return html.escape(str(text))

    def to_latex(value, data_kind = None):
        if data_kind == "time":
            if value < 1.0: v = r"\textless 1"
            elif value < 100: v = f"{value:.1f}"
            else: v = f"{value:.0f}"
        elif type(value) == int:
            v = f"{value:.4g}"
            if "e+" in v: v = "{} {{\\cdot}} 10^{{{}}}".format(round(float(v[:v.find("e+")])), int(v[v.find("e+")+2:]))
        elif type(value) == bool:
            v = "yes" if value else "no"
        elif type(value) == list:
            if all(type(e) == int for e in value):
                if min(value) == max(value):
                    v = to_latex(min(value))
                else:
                    v = "{}..{}".format(to_latex(min(value)), to_latex(max(value)))
        elif type(value) == str and value.startswith("(") and value.endswith(")"):
            v = "{}".format(value[1:-1])
        elif type(value) == str and data_kind == "result":
            v = latex_result(value)
            data_kind = None # latex_result already formats the relation
        elif type(value) == str and data_kind == "name":
            value = value.replace("resources", "resrc").replace("obstacle", "obstcl").replace("service", "serv")
            v = f"\\model{{{latex_model_name(value)}}}"
        elif type(value) == str and data_kind == "par":
            v = value.replace("_", r"\_")
        elif type(value) == float:
            v = f"{value:.3g}"
            if "e+" in v: v = "{}{{$\\cdot$}}10$^\\text{{{}}}$".format(round(float(v[:v.find("e+")])), int(v[v.find("e+")+2:]))
            if "e-" in v: v = "{}{{$\\cdot$}}10$^\\text{{-{}}}$".format(round(float(v[:v.find("e-")])), int(v[v.find("e-")+2:]))
        else:
            v = value
        return v if data_kind is None or data_kind == "time" else f"${v}$"

    def get_cell_content(column, inst, kind):
        assert kind in export_kinds, f"Invalid kind for cell content: {kind}"
        value = None
        # first check if the column refers to a tool config
        tool = column[0]
        if tool in TOOL_NAMES: # the column is assumed to be a [tool, config, data_key] list, where data_key is the cell content key
            res = get_result_if_supported(exec_data, tool, column[1], inst)
            if res is None:
                if kind in ["default", "html"]:
                    value = "NS"
                elif kind in ["scatter"]:
                    value = scatter_special_value(2)
                elif kind.startswith("latex"):
                    value = "-"
                elif kind in ["quantile"]:
                    value = math.inf
            elif res["timeout"] == True:
                if kind in ["default", "html"]:
                    value = "TO"
                elif kind.startswith("latex"):
                    value = "TO"
                elif kind in ["scatter"]:
                    value = scatter_special_value(1) # TO
                elif kind in ["quantile"]:
                    value = math.inf
            elif res["memout"]:
                if kind in ["default", "html"]:
                    value = "MO"
                elif kind.startswith("latex"):
                    value = "MO"
                elif kind in ["scatter"]:
                    value = scatter_special_value(1)
                elif kind in ["quantile"]:
                    value = math.inf
            elif res["expected-error"] or res.get("execution-error", False):
                if kind in ["default", "html"]:
                    value = "ERR"
                elif kind.startswith("latex"):
                    value = "ERR"
                elif kind in ["scatter"]:
                    value = scatter_special_value(1)
                elif kind in ["quantile"]:
                    value = math.inf
            elif "result" in res:
                value = res[column[2]]
                if "time" in column[2]:
                    if kind in ["html"]:
                        value = f"{value:.1f}"
                    elif kind.startswith("latex"):
                        value = to_latex(value, "time")
                    elif kind in ["scatter"]:
                        value = max(SCATTER_MIN_VALUE, min(SCATTER_MAX_VALUE, value))
                    elif kind in ["quantile"]:
                        value = max(QUANTILE_MIN_VALUE, value)
                elif column[2] == "result" and kind.startswith("latex"):
                    value = to_latex(value, "result")
            if kind == "html":
                res = get_result(exec_data, tool, column[1], inst)
                if res is not None:
                    value = [value, res]
                    if "result" in res:
                        value[0] = to_html("{} / {}".format(res["result"], value[0]))
            elif kind.startswith("latex"):
                res = get_result(exec_data, tool, column[1], inst)
                if res is None or "result" not in res:
                    value = r"\multicolumn{1}{c}{-}"
                elif not is_successful_result(res):
                    pass # Keep the TO/MO/ERR marker selected above.
                else:
                    relation, result_number = parse_result_value(res["result"])
                    if relation != "=" and result_number == (1.0 if relation == "≤" else 0.0):
                        value = r"\multicolumn{1}{c}{-}"
                        return value
                    asterisk = ""
                    if "--belief-exploration unfold" in res["commands"][0] and "belief-mdp-incomplete" not in res:
                        asterisk = "$^*$"
                    value = "{} ({}s){}".format(latex_result(res["result"]), value, asterisk)
        else: # column[0] is a key in benchmark_instances, column[1] is either not present or a function that applies a transformation
            if column[0] in benchmark_instances[inst]:
                value = benchmark_instances[inst][column[0]]
            else: # info not available
                if kind in ["scatter", "quantile"]:
                    value = "nan"
                else:
                    value = "?"
            if len(column) > 1:
                value = column[1](value)
            elif kind.startswith("latex"):
                value = to_latex(value, column[0])
            elif kind in ["scatter"] and type(value) == list:
                if len(value) == 0: value = "nan"
                else: value = sum(value) / len(value) # average
            if type(value) == Counter:
                value = ", ".join([f"{k}: {v}" for k,v in value.items()])
            value = f"{value}"
        assert value is not None, f"No value found for column {column}, and instance {inst} (kind {kind})"
        return value

    def create_cells(columns, cfgs, kind, latex_highlight_best_col_indices = None):
        if kind == "quantile":
            rows = get_instances_supported_by_all(cfgs)
            header = ["i"] + [f"{c[0]}.{c[1]}" for c in columns[-len(cfgs):]]
            cells = [header] + [[i+1] for i in range(len(rows))]
            for c in columns[-len(cfgs):]:
                c_runtimes = sorted([get_cell_content(c, inst, kind) for inst in rows])
                for j in range(len(c_runtimes)):
                    cells[j+1].append(c_runtimes[j] if c_runtimes[j] != math.inf else "nan")
            return cells
        else:
            header = [c[0] for c in columns[:-len(cfgs)]]
            if len(cfgs) > 0: header += [f"{c[0]}.{c[1]}" for c in columns[-len(cfgs):]]
            rows = [i["id"] for i in benchmarks.INSTANCES if i["id"] in benchmark_instances]
            cells = [header]
            for inst in rows:
                cells.append([])
                for c in columns:
                    cells[-1].append(get_cell_content(c, inst, kind))
                if kind.startswith("latex") and latex_highlight_best_col_indices is not None:
                    # mark the best results
                    best_lower_indices, best_upper_indices = [], []
                    best_lower_result, best_upper_result = None, None
                    # first find the ones with the best bounds
                    for j in latex_highlight_best_col_indices:
                        execdata_j = get_result(exec_data, columns[j][0], columns[j][1], inst)
                        if execdata_j is None or "result" not in execdata_j: continue
                        res_j = execdata_j["result"]
                        if res_j[:2] not in ["≤ ", "≥ "]: continue
                        is_upper = res_j[:2] == "≤ "
                        if float(res_j[2:]) == (1.0 if is_upper else 0.0): continue
                        if is_upper and len(best_upper_indices) == 0:
                            best_upper_indices = [j]
                            best_upper_result = res_j
                        elif not is_upper and len(best_lower_indices) == 0:
                            best_lower_indices = [j]
                            best_lower_result = res_j
                        else:
                            res_best = best_upper_result if is_upper else best_lower_result
                            assert res_best[:2] ==  res_j[:2], f"Unexpected result bound type: {res_best} vs. {res_j}"
                            res_j = float(res_j[2:])
                            res_best = float(res_best[2:])
                            if is_upper and res_j < res_best:
                                best_upper_indices = [j]
                                best_upper_result = res_j
                            elif not is_upper and res_j > res_best:
                                best_lower_indices = [j]
                                best_lower_result = res_j
                            elif res_j == res_best:
                                if is_upper: best_upper_indices.append(j)
                                else: best_lower_indices.append(j)
                    # now filter to find the best runtimes
                    for indices in [best_lower_indices, best_upper_indices]:
                        best_time = None
                        best_indices = []
                        for j in indices:
                            time_j = get_cell_content(columns[j], inst, "default")
                            assert(type(time_j) == float), f"Unexpected content for time cell: {time_j}"
                            if best_time is None:
                                best_time = time_j
                                best_indices = [j]
                            elif to_latex(time_j, "time") == to_latex(best_time, "time"):
                                best_indices.append(j)
                            elif time_j < best_time:
                                best_time = time_j
                                best_indices = [j]
                        for j in best_indices:
                            cells[-1][j] = f"\\textbf{{{cells[-1][j]}}}"

            return cells

    def merge_cells_latex(cells, merge_cols):
        cols_to_remove = [r for l,r in merge_cols]
        new_cells = [cells[0]]
        for row in cells[1:]: # skip header
            row_cpy = copy.deepcopy(row)
            for l,r in merge_cols:
                lower = row_cpy[l]
                upper = row_cpy[r]
                if lower == "-": result = upper
                elif upper == "-": result = lower
                else:
                    assert r"$\ge$" in lower, f"Unexpected content for result cell: {lower}"
                    assert r"$\le$" in upper, f"Unexpected content for result cell: {upper}"
                    result = "[{},~{}]".format(lower.replace(r"$\ge$", ""), upper.replace(r"$\le$", ""))
                row_cpy[l] = result
            new_cells.append([row_cpy[i] for i in range(len(row_cpy)) if i not in cols_to_remove])
        return new_cells

    def export_data_for_kind(kind):
        # get the columns relevant for this kind
        if kind.startswith("latex"):
            if kind.startswith("latext"):
                cols = [["name"], ["num-epochs"], ["unf-states"]]
                timelimit = kind[len("latext"):]
                cfgs = [ [storm.NAME, f"{cfgbase}-best-in-{timelimit}s"] for cfgbase in storm.BASE_CONFIGS[:6] ]
                cols += [[c[0], c[1], "wallclock-time"] for c in cfgs]
                latex_cols = [r"\multicolumn{1}{c}{Model}", r"\multicolumn{1}{c}{$|\epochs|$}", r"\multicolumn{1}{c}{$|S_\mathsf{un}|$}", r"\multicolumn{2}{c}{\config{unfold}: \config{cut} / \config{discr}}", r"\multicolumn{2}{c}{\config{ca-unfold}: \config{cut} / \config{discr}}", r"\multicolumn{2}{c}{\config{ca-bel-seq}: \config{cut} / \config{discr}}"]
                latex_col_aligns = "c@{}" + "r" * (len(cols)-1)
                cells = create_cells(cols, cfgs, kind, None)
                # cells = merge_cells_latex(cells, [[5,6],[7,8],[9,10]])
            else:
                cols = [["name"], ["states"], ["choices"], ["observations"], ["dim"], ["num-epochs"]]
                latex_cols = [r"Model", r"$|S|$", r"$|Act|$", r"$|Z|$", r"$k$", r"$|\epochs|$"]
                latex_col_aligns = "crrrrr"
                cfgs = []
                cells = create_cells(cols, cfgs, kind)
            latex_header = "\n& ".join(latex_cols)
            save_latex(cells, latex_col_aligns, latex_header, os.path.join(TABLE_DIR, "{}table{}.tex".format(prefix, kind[len("latex"):])))
        else:
            cols = [["name"], ["par"], ["states"], ["choices"], ["observations"], ["property"]]
            cfgs = [ [tool.NAME, c["id"]] for tool in TOOLS  for c in tool.CONFIGS + tool.META_CONFIGS ]
            cols += [[c[0], c[1], "wallclock-time"] for c in cfgs]
            # create and export different kinds of data
            cells = create_cells(cols, cfgs, kind)
            if kind in ["default", "scatter", "quantile"]:
                save_csv(cells, os.path.join(OUT_DIR, f"{prefix}{kind}.csv"))
            elif kind == "html":
                save_html(cells, len(cfgs), os.path.join(OUT_DIR, f"{prefix}table"))
            else:
                assert False, f"Unhandled kind: {kind}"

    # invoke generation for all kinds
    if len(benchmark_instances) == 0: return
    for kind in export_kinds: export_data_for_kind(kind)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate visualisations for the current cut-off sweep.")
    parser.add_argument("logdirs", nargs="+", help="Directories containing execution JSON and log files")
    parser.add_argument("--output-dir", default="data", help="Destination for plots, runtime overview, audit data, and preview")
    parser.add_argument("--legacy-outputs", action="store_true", help="Also generate the historical dissertation outputs")
    options = parser.parse_args()
    logdirs = options.logdirs
    OUT_DIR = options.output_dir
    TABLE_DIR = os.path.join(OUT_DIR, "tables-general")
    GENERAL_PLOT_DIR = os.path.join(OUT_DIR, "general-plots")
    RESOLUTION_VALUE_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "resolution-value")
    RESOLUTION_TIME_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "resolution-time")
    TIME_RESULT_PLOT_DIR = os.path.join(GENERAL_PLOT_DIR, "time-result")
    OVERAPPROX_TABLE_DIR = os.path.join(TABLE_DIR, "overapprox")
    UNDERAPPROX_TABLE_DIR = os.path.join(TABLE_DIR, "underapprox")

    print("Selected log dir(s): {}".format(", ".join(logdirs)))
    print("")

    exec_data, benchmark_instances = gather_execution_data(logdirs)
    benchmark_instances = OrderedDict(sorted(benchmark_instances.items(), key=lambda item: item[0]))
    process_meta_configs(exec_data, benchmark_instances)

    if not os.path.exists(OUT_DIR): os.makedirs(OUT_DIR)
    save_json(exec_data, os.path.join(OUT_DIR, "execution-data.json"))
    save_json(benchmark_instances, os.path.join(OUT_DIR, "benchmark-data.json"))
    save_runtime_overview(exec_data, logdirs)

    from html_results import save_results as save_html_results
    save_html_results(sys.modules[__name__], exec_data, benchmark_instances, logdirs)

    from cutoff_plots import save_plots as save_cutoff_plots
    save_cutoff_plots(sys.modules[__name__], exec_data, benchmark_instances)

    print("Found Data for {} benchmarks".format(len(benchmark_instances)))

    if not options.legacy_outputs:
        sys.exit(0)

    for b_id, b_data in benchmark_instances.items():
        if "benchmark-set" not in b_data: print(b_data.keys())
    def get_benchmark_subset(subset):
        return {b_id: b_data for b_id, b_data in benchmark_instances.items() if b_data["benchmark-set"] in subset}


    export_kinds = ["default", "scatter", "quantile", "html", "latexbenchmarks"] + [f"latext{t}" for t in storm.META_CONFIG_TIMELIMITS]
    #export_data(exec_data, get_benchmark_subset(["drone"]), export_kinds, prefix="drone-")
    #export_data(exec_data, get_benchmark_subset(["network2"]), export_kinds, prefix="netw2-")
    #export_data(exec_data, get_benchmark_subset(["network-priorities2"]), export_kinds, prefix="netwp2-")
    save_dissertation_tables(exec_data, benchmark_instances, storm.META_CONFIG_TIMELIMITS[0])
    save_overapproximation_table(exec_data, benchmark_instances)
    save_underapproximation_tables(exec_data, benchmark_instances)
    save_time_result_csv(exec_data, benchmark_instances)
    save_time_budget_improvement_csv(exec_data, benchmark_instances)
    save_resolution_result_csv(exec_data, benchmark_instances)
    save_resolution_overview_csv(exec_data, benchmark_instances)
    save_discretisation_mode_comparison_csv(exec_data, benchmark_instances)
    save_discretisation_question_plots(exec_data, benchmark_instances)
    save_underapproximation_question_outputs(exec_data, benchmark_instances)
