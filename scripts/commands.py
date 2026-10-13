import fnmatch
import itertools
import json
import os
from collections import OrderedDict
from datetime import date

import benchmarks
import tools
from input import *
from executing import *


class SelectionError(ValueError):
    """Raised when a command-line selector does not identify a known item."""


def split_selectors(selectors):
    """Turn repeated, comma-separated command-line selectors into a flat list."""
    if not selectors:
        return []
    return [selector.strip() for value in selectors for selector in value.split(",") if selector.strip()]


def _select_records(records, selectors, key, item_name):
    """Select records by exact name or shell-style glob, preserving their order."""
    selectors = split_selectors(selectors)
    if not selectors:
        return list(records)

    selected = []
    unmatched = []
    for selector in selectors:
        matches = [record for record in records if any(fnmatch.fnmatchcase(value, selector) for value in key(record))]
        if not matches:
            unmatched.append(selector)
            continue
        for record in matches:
            if record not in selected:
                selected.append(record)
    if unmatched:
        raise SelectionError(
            "Unknown {} selector(s): {}. Use 'python3 scripts/run.py list' to see the available choices."
            .format(item_name, ", ".join(unmatched))
        )
    return selected


def select_benchmarks(selectors=None):
    """Select instances by benchmark set, model name, or complete instance id."""
    return _select_records(
        benchmarks.INSTANCES,
        selectors,
        lambda inst: [inst["benchmark-set"], inst["name"], inst["id"]],
        "benchmark",
    )


def all_tool_configs():
    return [config for tool in tools.TOOLS for config in tool.CONFIGS]


def select_configurations(selectors=None):
    """Select configurations by id; selectors can use shell globs such as 'cut*'."""
    return _select_records(all_tool_configs(), selectors, lambda cfg: [cfg["id"]], "configuration")


CONFIGURATION_FAMILY_DESCRIPTIONS = OrderedDict(
    [
        ("discretisation", "static discretisation references at resolutions 4 and 5"),
        ("cutoff", "32 explicit cut-offs: 1-9 times each decade from 10,000 through 9,000,000, then 10-50 million"),
        ("MDP", "the underlying fully observable MDP configuration"),
    ]
)


def configuration_family_options(configurations):
    """Return selector options that expand a method family to all its configurations."""
    options = OrderedDict()
    for family, description in CONFIGURATION_FAMILY_DESCRIPTIONS.items():
        count = len([
            configuration for configuration in configurations
            if family in configuration_selection_groups(configuration)
        ])
        options[family] = [description, f"{count} configuration(s)"]
    unclassified = [configuration["id"] for configuration in configurations if configuration.get("family") not in options]
    assert not unclassified, f"Configuration(s) without a known family: {', '.join(unclassified)}"
    return options


def configuration_selection_groups(configuration):
    """Return the primary family and any additional interactive selection groups."""
    return [configuration["family"], *configuration.get("selection-groups", [])]


def default_tool_binaries():
    return {tool.NAME: tool.default_executable for tool in tools.TOOLS}


def create_invocation_data(instances, configurations, tool_binaries, time_limit, log_dir):
    """Build the established invocation-file payload without writing it to disk."""
    invocations = []
    for inst, cfg in itertools.product(instances, configurations):
        if not is_supported(inst, cfg):
            continue
        invocation_id = get_invocation_id(inst, cfg)
        invocation = OrderedDict()
        invocation["id"] = invocation_id
        invocation["benchmark-id"] = inst["id"]
        invocation["tool"] = cfg["tool"]
        invocation["configuration-id"] = cfg["id"]
        invocation["invocation-note"] = ". ".join(cfg["notes"])
        invocation["commands"] = get_command_lines(tool_binaries, cfg, inst)
        invocation["time-limit"] = time_limit
        invocation["log-dir"] = log_dir
        invocation["log"] = f"{invocation_id}.log"
        invocations.append(invocation)
    return invocations


def write_invocations(invocations, filename, overwrite=False):
    """Write an invocation file, creating only its direct parent directory if needed."""
    if os.path.exists(filename) and not overwrite:
        raise FileExistsError(f"Invocation file {filename} already exists. Pass --force to replace it.")
    parent = os.path.dirname(filename)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as json_file:
        json.dump(invocations, json_file, ensure_ascii=False, indent="\t")


def print_available_items(show_benchmarks=True, show_configurations=True):
    if show_benchmarks:
        print("Benchmarks (select by set, model, or instance id):")
        for inst in benchmarks.INSTANCES:
            parameters = inst["model"].get("open-parameters", {})
            parameter_text = ", ".join(f"{key}={value}" for key, value in parameters.items())
            suffix = f" ({parameter_text})" if parameter_text else ""
            print(f"  {inst['id']}  [set={inst['benchmark-set']}, model={inst['name']}, property={inst['property']['id']}]{suffix}")
        print(f"\n{len(benchmarks.INSTANCES)} benchmark instances.")
    if show_benchmarks and show_configurations:
        print("")
    if show_configurations:
        print("Configurations (exact id or shell glob, e.g. cut*):")
        for cfg in all_tool_configs():
            print(f"  {cfg['id']:<13} {'. '.join(cfg['notes'])}")
        print(f"\n{len(all_tool_configs())} configurations.")

def check_execution(command):
    command_repl = replace_placeholders_in_cmd_string(command)
    print(f"\tTesting execution of {command_repl} ... ", end="")
    try:
        test_out, test_time, test_code = execute_command_line(command_repl, 10)
        if test_code == 0:
            print("success!")
            return True
        else:
            print(f"WARN: Non-zero return code '{test_code}'. Output:\n{'-'*80}\n{test_out}{'-'*80}")
    except KeyboardInterrupt:
        print("Aborted.")
    except Exception as e:
        print(f"WARN: unable to execute:\n\t\t{e}")
    return ask_user_yn("Continue?")

def is_supported(inst, cfg):
    if inst["model"]["formalism"] not in cfg["supported-model-formalisms"]: return False
    if inst["model"]["type"] not in cfg["supported-model-types"]: return False
    if inst["property"]["type"] not in cfg["supported-obj-types"]: return False
    return True

def get_invocation_id(inst, cfg):
    return f"{cfg['tool']}.{cfg['id']}.{inst['id']}"

    
def get_command_lines(tool_binaries, cfg, inst = None):
    return [f"{tool_binaries[cfg['tool']]} {tools.get_command_line_args(cfg, inst)}"]
    
def create_invocations():
    """Create invocations interactively from the reduced registry."""
    storm = tools.TOOL_NAMES["storm"]
    tool_binaries = {
        storm.NAME: ask_user_for_info(
            f"Enter path to {storm.NAME} binary:", storm.default_executable, check_execution
        )
    }
    tool_configs = storm.CONFIGS

    cfg_options = configuration_family_options(tool_configs)
    cfg_selection = input_selection("Configuration Families", cfg_options)
    cfgs = [
        configuration for configuration in tool_configs
        if any(group in cfg_selection for group in configuration_selection_groups(configuration))
    ]
    print(f"Selected {len(cfgs)} configuration(s) from: {', '.join(cfg_selection)}.")
    for cfg in cfgs:
        for cmd in get_command_lines(tool_binaries, cfg):
            if not check_execution(cmd): exit(-1)

    bset_selection = input_selection("Benchmark Sets", benchmarks.BENCHMARK_SETS)
    instances = [inst for inst in benchmarks.INSTANCES if inst["benchmark-set"] in bset_selection]
    invocations = create_invocation_data(instances, cfgs, tool_binaries, time_limit=0, log_dir="")
    print(f"Selected {len(invocations)} invocations.")

    time_limit = int(ask_user_for_info(f"Enter a time limit (in seconds):", "600", lambda usr_in : usr_in.isdigit() and int(usr_in) > 0))
    log_dir = ask_user_for_info(f"Enter a logfile directory ", f"logs-pomdp-{date.today()}")
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    inv_name = ask_user_for_info(f"Enter a file for storing the invocation information ", f"inv-pomdp-{date.today()}.json", ask_user_overwrite_file)
    print(f"Storing information for {len(invocations)} invocations ... ", end="")
    invocations = create_invocation_data(instances, cfgs, tool_binaries, time_limit, log_dir)
    write_invocations(invocations, inv_name, overwrite=True)
    print("done.")
    

    
    
