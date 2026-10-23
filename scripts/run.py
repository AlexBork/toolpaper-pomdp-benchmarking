"""Create invocation files interactively or execute a saved experiment."""

import argparse
import json
from pathlib import Path
import sys
import traceback

from commands import create_invocations
from executing import Execution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "filename",
        nargs="?",
        help="Invocation JSON file; omit to create one interactively",
    )
    parser.add_argument(
        "index",
        nargs="?",
        type=int,
        help="Execute only this invocation (zero-based index)",
    )
    parser.add_argument("-help", action="help", help=argparse.SUPPRESS)
    options = parser.parse_args()

    if options.filename is None:
        input("Press Return to create an invocation file or Ctrl+C to abort.")
        create_invocations()
        return 0

    try:
        with open(options.filename, encoding="utf-8-sig") as json_file:
            invocations = json.load(json_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if not isinstance(invocations, list):
        parser.error("Expected an invocation JSON array")

    print(f"Loaded {len(invocations)} invocations.")
    if options.index is None:
        indices = range(len(invocations))
    elif 0 <= options.index < len(invocations):
        indices = [options.index]
    else:
        parser.error(
            f"Index {options.index} is out of range for {len(invocations)} invocations"
        )

    exit_code = 0
    for index in indices:
        invocation = invocations[index]
        print(
            f"Executing invocation #{index}: {invocation['id']}... ", end="", flush=True
        )
        try:
            Path(invocation["log-dir"]).mkdir(parents=True, exist_ok=True)
            execution = Execution(invocation)
            execution.run()
            # A rerun replaces any legacy JSON record for this log as well.
            legacy_json = Path(invocation["log-dir"]) / Path(
                invocation["log"]
            ).with_suffix(".json")
            legacy_json.unlink(missing_ok=True)
        except KeyboardInterrupt:
            print(f"\nInterrupted invocation #{index}: {invocation['id']}")
            return 130
        except Exception:
            print(
                f"\nERROR while processing invocation #{index}: {invocation['id']}",
                flush=True,
            )
            traceback.print_exc()
            exit_code = 1
        else:
            print(f"done ({execution.wall_time:.2f}s).")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
