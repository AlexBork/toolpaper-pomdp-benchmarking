"""Execute benchmark commands with process-group timeouts and self-contained logs."""

import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time


def replace_placeholders_in_cmd_string(cmd_string):
    bench_home = Path(__file__).resolve().parent.parent
    return os.path.expanduser(cmd_string).replace("$BENCH_HOME", str(bench_home))


class CommandExecution:
    """Execute one command and kill its process group when the time limit expires."""

    def __init__(self):
        self.timelimit = None
        self.return_code = None
        self.output = None
        self.wall_time = None
        self.proc = None

    def stop(self):
        self.timelimit = True
        sys.stdout.write("sending termination request... ")
        sys.stdout.flush()
        self.kill_process_group()

    def kill_process_group(self):
        try:
            # The new session makes the child's PID its process-group ID. This also
            # kills remaining group members if the original child has exited.
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def run(self, command_line_str, timelimit):
        command_line_list = [
            replace_placeholders_in_cmd_string(c) for c in shlex.split(command_line_str)
        ]
        self.proc = subprocess.Popen(
            command_line_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        start_time = time.monotonic()
        timer = threading.Timer(timelimit, self.stop)
        self.timelimit = False
        self.output = ""
        timer.start()
        try:
            stdout, stderr = self.proc.communicate()
        except BaseException:
            self.kill_process_group()
            self.proc.communicate()
            raise
        finally:
            timer.cancel()
            self.wall_time = time.monotonic() - start_time
            self.return_code = self.proc.returncode
        if stdout is not None:
            self.output = self.output + stdout.decode("utf8")
        if stderr is not None and len(stderr) > 0:
            self.output = (
                self.output
                + "\n"
                + "#" * 30
                + "Output to stderr"
                + "#" * 30
                + "\n"
                + stderr.decode("utf8")
            )


def execute_command_line(command_line_str, timelimit):
    """
    Executes the given command line with the given time limit (in seconds).
    :returns the output of the command (including the output to stderr, if present), the runtime of the command and either the return code or None (in case of a timelimit)
    """
    execution = CommandExecution()
    execution.run(command_line_str, timelimit)
    if execution.timelimit:
        return execution.output, execution.wall_time, None
    else:
        return execution.output, execution.wall_time, execution.return_code


class Execution:
    """Run an invocation and write its metadata and output to a log."""

    def __init__(self, invocation_json):
        self.invocation = invocation_json
        self.wall_time = None
        self.logs = None

    def run(self):
        self.wall_time = 0.0
        self.logs = []
        for command in self.invocation["commands"]:
            log, wall_time, return_code = execute_command_line(
                command, self.invocation["time-limit"] - self.wall_time
            )
            self.wall_time = self.wall_time + wall_time
            self.logs.append(
                f"Command:\t{command}\n"
                f"Benchmark:\t{self.invocation['benchmark-id']}\n"
                f"Configuration:\t{self.invocation['configuration-id']}\n"
                "Repetition:\t1\n"
                f"Time limit:\t{self.invocation['time-limit']}\n"
                f"Tool:\t{self.invocation['tool']}\n"
                f"Invocation:\t{self.invocation['id']}\n"
                f"Invocation note:\t{self.invocation.get('invocation-note', '')}\n"
                f"Wallclock time:\t{wall_time}\n"
                f"Return code:\t{return_code}\n"
                f"Output:\n{log}\n"
            )
            if return_code is None:
                self.logs[-1] = (
                    self.logs[-1]
                    + "\n"
                    + "-" * 10
                    + "\nComputation aborted after {} seconds since the total time limit of {} seconds was exceeded.\n".format(
                        self.wall_time, self.invocation["time-limit"]
                    )
                )
                break
        # save logfile
        with open(
            os.path.join(self.invocation["log-dir"], self.invocation["log"]),
            "w",
            encoding="utf-8",
        ) as logfile:
            hline = "\n" + "#" * 40 + "\n"
            logfile.write(hline.join(self.logs))
