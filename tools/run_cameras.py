"""Run multiple CV workers from private camera env files.

Example:
    python tools/run_cameras.py --env-file cameras/camera-1.env \
        --env-file cameras/camera-2.env
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from collections import deque

from dotenv import dotenv_values


def start_worker(root: Path, env_file: Path) -> subprocess.Popen:
    env_file = env_file.resolve()
    if not env_file.is_file():
        raise SystemExit(f"camera env file does not exist: {env_file}")
    values = dotenv_values(env_file, interpolate=False)
    environment = {**os.environ, **{key: value for key, value in values.items() if value is not None}}
    return subprocess.Popen([sys.executable, "-m", "cv_engine.run"], cwd=root, env=environment)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", type=Path, required=True,
                        help="private camera environment file; repeat for each worker")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    workers = [{"env_file": path.resolve(), "process": start_worker(root, path)}
               for path in args.env_file]
    restart_times = {worker["env_file"]: deque() for worker in workers}
    shutting_down = False
    failed = False

    def stop_workers(signum, _frame):
        nonlocal shutting_down
        shutting_down = True
        for worker in workers:
            process = worker["process"]
            if process.poll() is None:
                process.send_signal(signum)

    signal.signal(signal.SIGINT, stop_workers)
    signal.signal(signal.SIGTERM, stop_workers)
    try:
        while not shutting_down:
            for worker in workers:
                process = worker["process"]
                if process.poll() is None:
                    continue
                env_file = worker["env_file"]
                now = time.monotonic()
                recent = restart_times[env_file]
                while recent and now - recent[0] > 60:
                    recent.popleft()
                if len(recent) >= 5:
                    print(f"{env_file}: exceeded restart limit", file=sys.stderr)
                    failed = True
                    shutting_down = True
                    break
                recent.append(now)
                print(f"{env_file}: worker exited; restarting", file=sys.stderr)
                time.sleep(1)
                worker["process"] = start_worker(root, env_file)
            if not shutting_down:
                time.sleep(0.5)
    finally:
        for worker in workers:
            process = worker["process"]
            if process.poll() is None:
                process.terminate()
        for worker in workers:
            worker["process"].wait()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
