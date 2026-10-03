"""Score the fall detector on a folder of recorded clips and tune its thresholds.

    python -m cv_engine.eval_clips CLIPS_DIR                 # pass/fail table with current thresholds
    python -m cv_engine.eval_clips CLIPS_DIR --sweep         # also search for better thresholds
    python -m cv_engine.eval_clips CLIPS_DIR --device cuda   # run pose extraction on a GPU

A clip is a video file or a folder of image frames. Its label comes from its
name: anything starting with "fall" (fall_03.mp4, fall-01-cam0) should
trigger, everything else (sit_01.mp4, adl-12-cam0) should not.

Pose extraction is the slow GPU step, so its output is cached per clip in
CLIPS_DIR/.pose_cache. Thresholds are then replayed from the cache in
seconds, which is what makes the sweep cheap.
"""

import argparse
import hashlib
import itertools
import pickle
from dataclasses import dataclass, replace
from pathlib import Path

from cv_engine.config import EngineConfig, FallThresholds
from cv_engine.detector.fall_state import FallDetector
from cv_engine.detector.types import PersonPose

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}
CACHE_DIR = ".pose_cache"
CACHE_VERSION = 1

Frames = list[tuple[float, list[PersonPose]]]  # (seconds from clip start, people)

# Grid searched by --sweep. Kept small: 4 * 3 * 3 * 3 = 108 combinations.
SWEEP_GRID = {
    "FALL_DROP_VELOCITY": [0.3, 0.4, 0.5, 0.6],
    "DOWN_TORSO_MIN_DEG": [50.0, 60.0, 70.0],
    "DOWN_ASPECT_MIN": [0.8, 1.0, 1.2],
    "DOWN_CONFIRM_S": [0.5, 1.0, 1.5],
}


@dataclass(frozen=True)
class ClipResult:
    name: str
    expected_fall: bool
    detected: bool
    events: int
    first_event_s: float | None  # seconds into the clip

    @property
    def outcome(self) -> str:
        if self.expected_fall:
            return "OK" if self.detected else "MISSED"
        return "FALSE ALARM" if self.detected else "OK"


def is_fall_clip(path: Path) -> bool:
    return path.name.lower().startswith("fall")


def find_clips(root: Path) -> list[Path]:
    clips = []
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            clips.append(path)
        elif path.is_dir() and any(f.suffix.lower() in IMAGE_EXTS for f in path.iterdir()):
            clips.append(path)
    return clips


def _read_frames(clip: Path, folder_fps: float):
    """Yield (seconds, frame) using the clip's own timeline."""
    import cv2

    if clip.is_dir():
        images = sorted(f for f in clip.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        for i, image in enumerate(images):
            frame = cv2.imread(str(image))
            if frame is not None:
                yield i / folder_fps, frame
        return
    capture = cv2.VideoCapture(str(clip))
    fps = capture.get(cv2.CAP_PROP_FPS) or folder_fps
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        yield index / fps, frame
        index += 1
    capture.release()


def _cache_path(clip: Path, model_path: str) -> Path:
    stat = clip.stat()
    key = f"{CACHE_VERSION}|{clip.name}|{stat.st_mtime_ns}|{stat.st_size}|{Path(model_path).name}"
    return clip.parent / CACHE_DIR / f"{clip.name}.{hashlib.sha1(key.encode()).hexdigest()[:12]}.pkl"


def extract_poses(clip: Path, estimator, model_path: str, folder_fps: float = 30.0) -> Frames:
    """Run pose tracking over a clip once and cache the result."""
    cache = _cache_path(clip, model_path)
    if cache.exists():
        with cache.open("rb") as f:
            return pickle.load(f)
    estimator.reset_tracking()
    frames = [(t, estimator(frame)) for t, frame in _read_frames(clip, folder_fps)]
    cache.parent.mkdir(exist_ok=True)
    with cache.open("wb") as f:
        pickle.dump(frames, f)
    return frames


def score_clip(name: str, expected_fall: bool, frames: Frames, thresholds: FallThresholds) -> ClipResult:
    detector = FallDetector(thresholds)
    event_times = [e.timestamp for t, people in frames for e in detector.update(people, t)]
    return ClipResult(name, expected_fall, bool(event_times), len(event_times),
                      event_times[0] if event_times else None)


def score_all(clips: dict[str, tuple[bool, Frames]], thresholds: FallThresholds) -> list[ClipResult]:
    return [score_clip(name, expected, frames, thresholds) for name, (expected, frames) in clips.items()]


def summarize(results: list[ClipResult]) -> dict[str, int]:
    return {
        "falls": sum(r.expected_fall for r in results),
        "caught": sum(r.expected_fall and r.detected for r in results),
        "missed": sum(r.expected_fall and not r.detected for r in results),
        "non_falls": sum(not r.expected_fall for r in results),
        "false_alarms": sum(not r.expected_fall and r.detected for r in results),
    }


def _distance_from_defaults(th: FallThresholds) -> float:
    default = FallThresholds()
    return sum(abs(getattr(th, k) - getattr(default, k)) / getattr(default, k) for k in SWEEP_GRID)


def sweep(clips: dict[str, tuple[bool, Frames]], base: FallThresholds) -> list[tuple[FallThresholds, dict]]:
    """Every grid combination, best first.

    Ranked by total mistakes, then false alarms (a false alarm on stage is the
    more visible failure), then closeness to the defaults.
    """
    ranked = []
    for values in itertools.product(*SWEEP_GRID.values()):
        th = replace(base, **dict(zip(SWEEP_GRID, values)))
        ranked.append((th, summarize(score_all(clips, th))))
    ranked.sort(key=lambda item: (item[1]["missed"] + item[1]["false_alarms"], item[1]["false_alarms"],
                                  _distance_from_defaults(item[0])))
    return ranked


def format_table(results: list[ClipResult]) -> str:
    width = max([len(r.name) for r in results] + [4])
    lines = [f"{'clip':<{width}}  {'expect':<7} {'result':<12} events  first event"]
    for r in results:
        first = f"{r.first_event_s:.1f}s" if r.first_event_s is not None else "-"
        lines.append(f"{r.name:<{width}}  {'fall' if r.expected_fall else 'no':<7} {r.outcome:<12} {r.events:<7} {first}")
    s = summarize(results)
    lines.append(f"\nfalls caught {s['caught']}/{s['falls']}   false alarms {s['false_alarms']}/{s['non_falls']}")
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clips_dir", type=Path)
    parser.add_argument("--sweep", action="store_true", help="search SWEEP_GRID for better thresholds")
    parser.add_argument("--device", help="cuda, mps or cpu (default: DEVICE from config)")
    parser.add_argument("--fps", type=float, default=30.0, help="frame rate for image-folder clips")
    args = parser.parse_args(argv)

    cfg = EngineConfig()
    clips_paths = find_clips(args.clips_dir)
    if not clips_paths:
        raise SystemExit(f"no clips found in {args.clips_dir}")
    print(f"{len(clips_paths)} clips: {sum(map(is_fall_clip, clips_paths))} falls, "
          f"{sum(not is_fall_clip(p) for p in clips_paths)} non-falls")

    estimator = None
    clips: dict[str, tuple[bool, Frames]] = {}
    for i, path in enumerate(clips_paths, 1):
        if estimator is None and not _cache_path(path, cfg.MODEL_PATH).exists():
            from cv_engine.detector.pose import PoseEstimator

            estimator = PoseEstimator(cfg.MODEL_PATH, device=args.device or cfg.DEVICE)
            estimator.warmup(frames=3)
        print(f"  [{i}/{len(clips_paths)}] {path.name}", flush=True)
        clips[path.name] = (is_fall_clip(path), extract_poses(path, estimator, cfg.MODEL_PATH, args.fps))

    print("\nCurrent thresholds:\n" + format_table(score_all(clips, cfg.thresholds)))

    if args.sweep:
        ranked = sweep(clips, cfg.thresholds)
        print(f"\nTop settings out of {len(ranked)} combinations:")
        for th, s in ranked[:5]:
            knobs = "  ".join(f"{k}={getattr(th, k)}" for k in SWEEP_GRID)
            print(f"  caught {s['caught']}/{s['falls']}  false alarms {s['false_alarms']}/{s['non_falls']}   {knobs}")
        best = ranked[0][0]
        print("\nBest settings on these clips:\n" + format_table(score_all(clips, best)))
        print("\nTo use them, set these defaults in FallThresholds (cv_engine/config.py):")
        for k in SWEEP_GRID:
            print(f"  {k}: float = {getattr(best, k)}")


if __name__ == "__main__":
    main()
