#!/usr/bin/env python3
"""Run a command under a memory guard (macOS/Linux).

    python3 memguard.py [--max-gb 3] [--min-free-gb 1.5] [--timeout SECONDS] -- <command> [args...]

The command runs in its own process group. Every second the guard sums the resident memory of every process in that group
(children such as git, docker clients or kernels included). If the group exceeds --max-gb, or the machine's available memory
falls below --min-free-gb, the whole group is killed and the guard exits with code 137 and a message on stderr. Otherwise the
guard exits with the command's own exit code. With --timeout the whole group is also killed after that many seconds (exit 124)."""
import os
import signal
import subprocess
import sys
import time


def group_rss_kb(pgid):
    out = subprocess.run(["ps", "-A", "-o", "pgid=,rss="], capture_output=True, text=True).stdout
    total = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == str(pgid):
            total += int(parts[1])
    return total


def available_gb():
    if sys.platform == "darwin":
        out = subprocess.run(["/usr/bin/vm_stat"], capture_output=True, text=True).stdout
        page = 16384
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip().rstrip(".")
                if v.isdigit():
                    vals[k.strip()] = int(v)
            if "page size of" in line:
                page = int(line.split("page size of")[1].split()[0])
        free = vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0) + vals.get("Pages purgeable", 0)
        return free * page / 2**30
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20
    return float("inf")


def main(argv):
    max_gb, min_free, timeout = 3.0, 1.5, None
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    opts, cmd = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    for i, o in enumerate(opts):
        if o == "--max-gb":
            max_gb = float(opts[i + 1])
        if o == "--min-free-gb":
            min_free = float(opts[i + 1])
        if o == "--timeout":
            timeout = float(opts[i + 1])
    if available_gb() < min_free:
        print(f"memguard: machine memory available below {min_free:g} GB; did not start", file=sys.stderr)
        return 137
    p = subprocess.Popen(cmd, start_new_session=True)
    pgid = p.pid
    started = time.time()
    while True:
        try:
            return p.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        if timeout is not None and time.time() - started > timeout:
            print(f"memguard: killed {os.path.basename(cmd[0])}: timeout of {timeout:g} s", file=sys.stderr, flush=True)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            return 124
        rss_gb = group_rss_kb(pgid) / 2**20
        avail = available_gb()
        if rss_gb > max_gb or avail < min_free:
            why = (f"process group used {rss_gb:.1f} GB (limit {max_gb} GB)" if rss_gb > max_gb
                   else f"machine memory available fell to {avail:.1f} GB (limit {min_free} GB)")
            print(f"memguard: killed {os.path.basename(cmd[0])}: {why}", file=sys.stderr, flush=True)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            return 137


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
