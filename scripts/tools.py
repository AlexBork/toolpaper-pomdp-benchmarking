"""Register the Storm tool and dispatch command construction."""

import storm

TOOLS = [storm]
TOOL_NAMES = {tool.NAME: tool for tool in TOOLS}


def get_command_line_args(cfg, inst=None):
    toolname = cfg["tool"]
    assert toolname in TOOL_NAMES, f"Unknown tool '{toolname}'"
    return TOOL_NAMES[toolname].get_command_line_args(cfg, inst)
