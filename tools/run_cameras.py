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

from dotenv import dotenv_values


def start_worker(root: Path, env_file: Path) -> subprocess.Popen:
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
    workers = [start_worker(root, path) for path in args.env_file]

    def stop_workers(signum, _frame):
        for worker in workers:
            if worker.poll() is None:
                worker.send_signal(signum)

    signal.signal(signal.SIGINT, stop_workers)
    signal.signal(signal.SIGTERM, stop_workers)
    try:
        while any(worker.poll() is None for worker in workers):
            time.sleep(0.5)
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
        for worker in workers:
            worker.wait()
    return 0 if all(worker.returncode == 0 for worker in workers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
