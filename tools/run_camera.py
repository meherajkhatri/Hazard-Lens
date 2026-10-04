"""Launch one camera using an ignored private env file, without secrets in arguments."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    args, extra = parser.parse_known_args()
    if not args.env_file.is_file():
        parser.error('Camera env file does not exist; copy a cameras/*.env.example first')
    values = dotenv_values(args.env_file, interpolate=False)
    environment = {**os.environ, **{key: value for key, value in values.items() if value is not None}}
    root = Path(__file__).resolve().parents[1]
    try:
        return subprocess.call([sys.executable, '-m', 'cv_engine.run', *extra], cwd=root, env=environment)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
