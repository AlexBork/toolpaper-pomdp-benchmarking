"""Select benchmarks interactively and write invocation files."""

import itertools
import json
import os
from collections import OrderedDict
from datetime import date

import benchmarks
import tools
from executing import execute_command_line, replace_placeholders_in_cmd_string
from input import (
    ask_user_for_info,
    ask_user_overwrite_file,
    ask_user_yn,
    input_selection,
)

CONFIGURATION_FAMILY_DESCRIPTIONS = OrderedDict(
    [
        ("discretisation", "static discretisation references at resolutions 4 and 5"),
        (
            "cutoff",
            "32 explicit cut-offs: 1-9 times each decade from 10,000 through 9,000,000, then 10-50 million",
        ),
    ]
)


def configuration_family_options(configurations):
    """Return selector options that expand a method family to all its configurations."""
    options = OrderedDict()
    for family, description in CONFIGURATION_FAMILY_DESCRIPTIONS.items():
        count = len(
            [
                configuration
                for configuration in configurations
                if family == configuration["family"]
            ]
        )
        options[family] = [description, f"{count} configuration(s)"]
    unclassified = [
        configuration["id"]
        for configuration in configurations
        if configuration.get("family") not in options
    ]
    assert (
        not unclassified
    ), f"Configuration(s) without a known family: {', '.join(unclassified)}"
    return options


def create_invocation_data(
    instances, configurations, tool_binaries, time_limit, log_dir
):
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
        raise FileExistsError(f"Invocation file {filename} already exists.")
    parent = os.path.dirname(filename)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as json_file:
        json.dump(invocations, json_file, ensure_ascii=False, indent="\t")


def check_execution(command):
    command_repl = replace_placeholders_in_cmd_string(command)
    print(f"\tTesting execution of {command_repl} ... ", end="")
    try:
        test_out, _, test_code = execute_command_line(command_repl, 10)
        if test_code == 0:
            print("success!")
            return True
        else:
            print(
                f"WARN: Non-zero return code '{test_code}'. Output:\n{'-'*80}\n{test_out}{'-'*80}"
            )
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"WARN: unable to execute:\n\t\t{e}")
    return ask_user_yn("Continue?")


def is_supported(inst, cfg):
    if inst["model"]["formalism"] not in cfg["supported-model-formalisms"]:
        return False
    if inst["model"]["type"] not in cfg["supported-model-types"]:
        return False
    if inst["property"]["type"] not in cfg["supported-obj-types"]:
        return False
    return True


def get_invocation_id(inst, cfg):
    return f"{cfg['tool']}.{cfg['id']}.{inst['id']}"


def get_command_lines(tool_binaries, cfg, inst=None):
    return [f"{tool_binaries[cfg['tool']]} {tools.get_command_line_args(cfg, inst)}"]


def create_invocations():
    """Create invocations interactively from the benchmark registry."""
    storm = tools.TOOL_NAMES["storm"]
    tool_binaries = {
        storm.NAME: ask_user_for_info(
            f"Enter path to {storm.NAME} binary:",
            storm.default_executable,
            check_execution,
        )
    }
    tool_configs = storm.CONFIGS

    cfg_options = configuration_family_options(tool_configs)
    cfg_selection = input_selection("Configuration Families", cfg_options)
    cfgs = [
        configuration
        for configuration in tool_configs
        if configuration["family"] in cfg_selection
    ]
    print(f"Selected {len(cfgs)} configuration(s) from: {', '.join(cfg_selection)}.")
    for cfg in cfgs:
        for cmd in get_command_lines(tool_binaries, cfg):
            if not check_execution(cmd):
                return

    bset_selection = input_selection("Benchmark Sets", benchmarks.BENCHMARK_SETS)
    instances = [
        inst for inst in benchmarks.INSTANCES if inst["benchmark-set"] in bset_selection
    ]
    invocations = create_invocation_data(
        instances, cfgs, tool_binaries, time_limit=0, log_dir=""
    )
    print(f"Selected {len(invocations)} invocations.")

    time_limit = int(
        ask_user_for_info(
            f"Enter a time limit (in seconds):",
            "600",
            lambda usr_in: usr_in.isdigit() and int(usr_in) > 0,
        )
    )
    log_dir = ask_user_for_info(
        f"Enter a logfile directory ", f"logs-pomdp-{date.today()}"
    )
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    inv_name = ask_user_for_info(
        f"Enter a file for storing the invocation information ",
        f"inv-pomdp-{date.today()}.json",
        ask_user_overwrite_file,
    )
    print(f"Storing information for {len(invocations)} invocations ... ", end="")
    invocations = create_invocation_data(
        instances, cfgs, tool_binaries, time_limit, log_dir
    )
    write_invocations(invocations, inv_name, overwrite=True)
    print("done.")
