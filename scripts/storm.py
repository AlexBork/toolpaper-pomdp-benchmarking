"""Define Storm configurations, construct commands, and parse execution output."""

import copy
import json
import re
from collections import OrderedDict

import benchmarks


def const_def_string(inst):
    if "open-parameters" in inst["model"]:
        pars = inst["model"]["open-parameters"]
        values = [f"{p}={pars[p]}" for p in pars if not p.startswith("__lvl")]
        if len(values) != 0:
            return ",".join(values)


def get_command_line_args(cfg, inst=None):
    out = []
    if inst is not None:
        assert (
            inst["model"]["formalism"] == "prism"
        ), f"Unhandled model formalism {inst['model']['formalism']} for storm."
        out.append(f"--prism {benchmarks.get_full_model_filename(inst)}")
        out.append(
            f"--prop {benchmarks.get_full_property_filename(inst)} {inst['property']['id']}"
        )
        c = const_def_string(inst)
        if c is not None:
            out.append(f"-const {c}")
    out += cfg["cmd"]
    return " ".join(out)


NAME = "storm"
DESCRIPTION = ["storm-pomdp"]
default_executable = "$BENCH_HOME/bin/storm-pomdp"

# Configuration data
# IDs shall not have a "_" or "."
CONFIGS = []

base_cfg = OrderedDict()
base_cfg["tool"] = NAME
base_cfg["cmd"] = ["--timemem", "--statistics", "--sound"]
base_cfg["notes"] = ["Storm-pomdp"]
base_cfg["supported-obj-types"] = ["prb", "rew"]
base_cfg["supported-model-types"] = ["pomdp"]
base_cfg["supported-model-formalisms"] = ["prism"]

for resolution in [4, 5]:
    discr_cfg = copy.deepcopy(base_cfg)
    discr_cfg["id"] = f"discr{resolution:03}s"
    discr_cfg["family"] = "discretisation"
    discr_cfg["cmd"] += [
        "--belief-exploration discretize",
        f"--resolution {resolution}",
        "--triangulationmode static",
    ]
    discr_cfg["notes"] += [
        f"Over-approximation with discretization, resolution {resolution}, triangulation mode static"
    ]
    CONFIGS.append(discr_cfg)

CUTOFF_THRESHOLDS = [
    mantissa * 10**exponent for exponent in range(4, 7) for mantissa in range(1, 10)
] + [mantissa * 10**7 for mantissa in range(1, 6)]
for threshold in CUTOFF_THRESHOLDS:
    cutoff_cfg = copy.deepcopy(base_cfg)
    cutoff_cfg["id"] = f"cut{threshold}"
    cutoff_cfg["family"] = "cutoff"
    cutoff_cfg["size-threshold"] = threshold
    cutoff_cfg["cmd"] += [
        "--belief-exploration unfold",
        f"--size-threshold {threshold}",
    ]
    cutoff_cfg["notes"] += [
        f"Under-approximation with cut-offs, size threshold {threshold}"
    ]
    CONFIGS.append(cutoff_cfg)

CONFIGS = sorted(
    CONFIGS, key=lambda x: (x["id"][:3], x.get("size-threshold", 0), x["id"])
)


def config_from_id(identifier):
    for c in CONFIGS:
        if c["id"] == identifier:
            return c
    assert False, f"Configuration identifier {identifier} is not known for {NAME}."


# LOGFILE Parsing
def contains_any_of(log, msg):
    for m in msg:
        if m in log:
            return True
    return False


def try_parse(log, start, before, after, out_dict, out_key, out_type):
    pos1 = log.find(before, start)
    if pos1 >= 0:
        pos1 += len(before)
        pos2 = log.find(after, pos1)
        if pos2 >= 0:
            out_dict[out_key] = out_type(log[pos1:pos2])
            return pos2 + len(after)
    return start


def try_parse_duration(log, start, before, out_dict, out_key):
    pos1 = log.find(before, start)
    if pos1 < 0:
        return start
    pos1 += len(before)
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)(ms|s)\.", log[pos1:])
    if match is None:
        return start
    value = float(match.group(1))
    if match.group(2) == "ms":
        value /= 1000.0
    out_dict[out_key] = value
    return pos1 + match.end()


def try_parse_constructed_belief_mdp(log, start, out_dict):
    prefix = "Constructed belief MDP: "
    pos1 = log.find(prefix, start)
    if pos1 < 0:
        return start
    pos1 += len(prefix)
    match = re.match(
        r"([0-9]+) states, ([0-9]+) choices, ([0-9]+) transitions\.", log[pos1:]
    )
    if match is None:
        return start
    out_dict["states"] = int(match.group(1))
    out_dict["choices"] = int(match.group(2))
    out_dict["transitions"] = int(match.group(3))
    return pos1 + match.end()


def parse_logfile(log, inv):
    unsupported_messages = (
        []
    )  # add messages that indicate that the invocation is not supported
    inv["not-supported"] = contains_any_of(log, unsupported_messages)
    memout_messages = (
        []
    )  # add messages that indicate that the invocation is not supported
    memout_messages.append(
        "An unexpected exception occurred and caused Storm to terminate. The message of this exception is: std::bad_alloc"
    )
    memout_messages.append("Return code:\t-9")
    inv["memout"] = contains_any_of(log, memout_messages)
    known_error_messages = (
        []
    )  # add messages that indicate a "known" error, i.e., something that indicates that no warning should be printed
    inv["expected-error"] = contains_any_of(log, known_error_messages)
    if inv["not-supported"] or inv["expected-error"]:
        return
    exploration = re.search(
        r"Belief exploration (completed|stopped early): (\d+) beliefs discovered, (\d+) beliefs explored\.",
        log,
    )
    if exploration:
        outcome, discovered, explored = exploration.groups()
        discovered, explored = int(discovered), int(explored)
        if not 0 < explored <= discovered:
            raise ValueError(f"Invalid exploration counts in {inv['id']}")
        inv["belief-exploration"] = {
            "discovered": discovered,
            "explored": explored,
            "complete": outcome == "completed",
        }
    if len(inv["return-codes"]) != 1 or inv["return-codes"][0] != 0:
        if not inv["timeout"] and not inv["memout"]:
            print(
                "WARN: Unexpected return code(s): {} in {}".format(
                    inv["return-codes"], inv["id"]
                )
            )

    pos = try_parse_duration(
        log, 0, "Time for model construction: ", inv, "model-building-time"
    )
    if pos == 0:
        assert (
            inv["timeout"] or inv["memout"] or inv.get("execution-error", False)
        ), "WARN: unable to get model construction time for {}".format(inv["id"])
        return
    inv["input-model"] = OrderedDict()
    pos = try_parse(log, pos, "States: \t", "\n", inv["input-model"], "states", int)
    pos = try_parse(
        log, pos, "Transitions: \t", "\n", inv["input-model"], "transitions", int
    )
    pos = try_parse(log, pos, "Choices: \t", "\n", inv["input-model"], "choices", int)
    pos = try_parse(
        log, pos, "Observations: \t", "\n", inv["input-model"], "observations", int
    )

    pos = log.find("Analyzing property ", pos)
    if pos < 0:
        assert (
            inv["memout"] or inv["timeout"] or inv.get("execution-error", False)
        ), "Unable to find query output in {}".format(inv["id"])
        return

    if (
        "Analyzing property 'Pmax=? [F true]'" in log
    ):  # todo this is to catch the trivial case
        inv["result"] = "≥1.0"
        inv["total-chk-time"] = "0.0"

    if (
        "Exploration stopped before all beliefs were explored" in log
        or "Belief exploration stopped early:" in log
    ):
        inv["belief-mdp-incomplete"] = True

    pos_bel = log.find("Constructing the belief MDP...", pos)
    if pos_bel < 0:
        pos_bel = log.find("Constructed belief MDP: ", pos)
    if pos_bel >= 0:
        pos = pos_bel
        inv["belief-mdp"] = OrderedDict()
        pos = try_parse(log, pos, "States: \t", "\n", inv["belief-mdp"], "states", int)
        pos = try_parse(
            log, pos, "Transitions: \t", "\n", inv["belief-mdp"], "transitions", int
        )
        pos = try_parse(
            log, pos, "Choices: \t", "\n", inv["belief-mdp"], "choices", int
        )
        pos = try_parse_constructed_belief_mdp(log, pos, inv["belief-mdp"])
        pos = try_parse_duration(
            log, pos, "Time for exploring beliefs: ", inv["belief-mdp"], "expl-time"
        )
        pos = try_parse_duration(
            log,
            pos,
            "Time for building the belief MDP: ",
            inv["belief-mdp"],
            "build-time",
        )
        pos = try_parse_duration(
            log,
            pos,
            "Time for analyzing the belief MDP: ",
            inv["belief-mdp"],
            "chk-time",
        )

    pos_result = try_parse(log, pos, "\nResult: ", "\n", inv, "result", str)
    if pos_result == pos:
        pos_result = try_parse(
            log, pos, "\nResult till abort: ", "\n", inv, "result", str
        )
    pos = pos_result
    pos = try_parse_duration(
        log, pos, "Time for POMDP analysis: ", inv, "total-chk-time"
    )

    if "total-chk-time" not in inv and "belief-mdp" in inv:
        belief_times = ["expl-time", "build-time", "chk-time"]
        if all(t in inv["belief-mdp"] for t in belief_times):
            inv["total-chk-time"] = sum(inv["belief-mdp"][t] for t in belief_times)

    assert (
        inv["memout"]
        or inv["timeout"]
        or inv.get("execution-error", False)
        or ("result" in inv and "total-chk-time" in inv)
    ), "Unable to find result or total-chk-time in {}".format(inv["id"])


if __name__ == "__main__":
    print(f"{len(CONFIGS)} config(s) for {NAME}")
    print(json.dumps(CONFIGS, indent="\t"))
