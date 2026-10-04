"""Score the fall detector on a folder of recorded clips and tune its thresholds.

    python -m cv_engine.eval_clips CLIPS_DIR                 # pass/fail table with current thresholds
    python -m cv_engine.eval_clips CLIPS_DIR --sweep         # also search for better thresholds
    python -m cv_engine.eval_clips CLIPS_DIR --device cuda   # run pose extraction on a GPU
    python -m cv_engine.eval_clips CLIPS_DIR --export cv_engine/tests/data/real_clips.json.gz
    python -m cv_engine.eval_clips --from-export cv_engine/tests/data/real_clips.json.gz --sweep

--export saves only the skeletons (joint positions over time, no images or faces)
so the clips can be shared, replayed and turned into tests without the videos.

A clip is a video file or a folder of image frames. Its label comes from its
name: anything starting with "fall" (fall_03.mp4, fall-01-cam0) should
trigger, everything else (sit_01.mp4, adl-12-cam0) should not.

Pose extraction is the slow GPU step, so its output is cached per clip in
CLIPS_DIR/.pose_cache. Thresholds are then replayed from the cache in
seconds, which is what makes the sweep cheap.
"""

import argparse
import gzip
import hashlib
import itertools
import json
import pickle
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

from cv_engine.config import EngineConfig, FallThresholds
from cv_engine.detector.fall_state import FallDetector, bbox_height
from cv_engine.detector.features import compute_features, drop_velocity
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


def frame_dir(path: Path) -> Path | None:
    """Folder holding a clip's image frames: `path` itself, or its only
    subfolder (zips often unpack as name/name/*.png). None if neither."""
    def has_images(folder: Path) -> bool:
        return any(f.suffix.lower() in IMAGE_EXTS for f in folder.iterdir())

    if has_images(path):
        return path
    subdirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if len(subdirs) == 1 and has_images(subdirs[0]):
        return subdirs[0]
    return None


def find_clips(root: Path) -> list[Path]:
    clips = []
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            clips.append(path)
        elif path.is_dir() and frame_dir(path) is not None:
            clips.append(path)
    return clips


def _read_frames(clip: Path, folder_fps: float):
    """Yield (seconds, frame) using the clip's own timeline."""
    import cv2

    if clip.is_dir():
        images = sorted(f for f in frame_dir(clip).iterdir() if f.suffix.lower() in IMAGE_EXTS)
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


EXPORT_VERSION = 1


def export_clips(clips: dict[str, tuple[bool, Frames]], path: Path, model_path: str) -> None:
    """Skeletons only: per frame, each person's track id, 17 keypoints and box."""
    data = {"version": EXPORT_VERSION, "model": Path(model_path).name, "clips": {
        name: {"expected_fall": expected, "frames": [
            [round(t, 4), [[p.track_id, [[round(float(x), 1), round(float(y), 1), round(float(c), 3)]
                                         for x, y, c in p.keypoints],
                            [round(float(v), 1) for v in p.bbox]] for p in people]]
            for t, people in frames]}
        for name, (expected, frames) in clips.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))


def load_export(path: Path) -> dict[str, tuple[bool, Frames]]:
    import numpy as np

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("version") != EXPORT_VERSION:
        raise SystemExit(f"{path}: unsupported export version {data.get('version')}")
    return {
        name: (clip["expected_fall"], [
            (t, [PersonPose(track_id=tid, keypoints=np.array(kps, dtype=float), bbox=tuple(bbox))
                 for tid, kps, bbox in people])
            for t, people in clip["frames"]])
        for name, clip in data["clips"].items()}


@dataclass(frozen=True)
class ClipStats:
    """Peak signals in a clip, to see why a fall was missed or a non-fall fired."""

    peak_drop: float  # fastest hip drop, body-heights / s
    max_torso: float  # largest torso angle, degrees
    min_height: float  # smallest box height / standing height


def clip_stats(frames: Frames, thresholds: FallThresholds) -> ClipStats:
    history: dict[int, list] = {}
    heights: dict[int, list[float]] = {}
    peak_drop = max_torso = 0.0
    min_height = 1.0
    for t, people in frames:
        for person in people:
            f = compute_features(person)
            if f is None or f.keypoint_conf < thresholds.MIN_KEYPOINT_CONF:
                continue
            past = [s for s in history.setdefault(person.track_id, []) if t - s[0] <= thresholds.FALL_DROP_WINDOW_S]
            peak_drop = max(peak_drop, drop_velocity(past, t, f, thresholds.FALL_DROP_WINDOW_S))
            history[person.track_id] = past + [(t, f)]
            max_torso = max(max_torso, f.torso_angle_deg)
            hs = heights.setdefault(person.track_id, [])
            hs.append(bbox_height(person))
            if len(hs) > 15:  # standing reference: median of the first half second
                min_height = min(min_height, hs[-1] / statistics.median(hs[:15]))
    return ClipStats(peak_drop, max_torso, min_height)


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


def format_table(results: list[ClipResult], stats: dict[str, ClipStats] | None = None) -> str:
    width = max([len(r.name) for r in results] + [4])
    header = f"{'clip':<{width}}  {'expect':<7} {'result':<12} events  first event"
    if stats:
        header += "   peak drop  max torso  min height"
    lines = [header]
    for r in results:
        first = f"{r.first_event_s:.1f}s" if r.first_event_s is not None else "-"
        line = f"{r.name:<{width}}  {'fall' if r.expected_fall else 'no':<7} {r.outcome:<12} {r.events:<7} {first:<11}"
        if stats and r.name in stats:
            st = stats[r.name]
            line += f"  {st.peak_drop:>7.2f}/s  {st.max_torso:>7.0f}deg  {st.min_height:>9.2f}"
        lines.append(line)
    s = summarize(results)
    lines.append(f"\nfalls caught {s['caught']}/{s['falls']}   false alarms {s['false_alarms']}/{s['non_falls']}")
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clips_dir", type=Path, nargs="?", help="folder of videos / frame folders")
    parser.add_argument("--sweep", action="store_true", help="search SWEEP_GRID for better thresholds")
    parser.add_argument("--device", help="cuda, mps or cpu (default: DEVICE from config)")
    parser.add_argument("--fps", type=float, default=30.0, help="frame rate for image-folder clips")
    parser.add_argument("--export", type=Path, help="save skeletons only (no images) to this .json.gz")
    parser.add_argument("--from-export", type=Path, help="replay a saved export instead of videos")
    args = parser.parse_args(argv)
    if bool(args.clips_dir) == bool(args.from_export):
        parser.error("give either CLIPS_DIR or --from-export")

    cfg = EngineConfig()
    if args.from_export:
        clips = load_export(args.from_export)
    else:
        clips_paths = find_clips(args.clips_dir)
        if not clips_paths:
            raise SystemExit(f"no clips found in {args.clips_dir}")
        estimator = None
        clips = {}
        for i, path in enumerate(clips_paths, 1):
            if estimator is None and not _cache_path(path, cfg.MODEL_PATH).exists():
                from cv_engine.detector.pose import PoseEstimator

                estimator = PoseEstimator(cfg.MODEL_PATH, device=args.device or cfg.DEVICE)
                estimator.warmup(frames=3)
            print(f"  [{i}/{len(clips_paths)}] {path.name}", flush=True)
            clips[path.name] = (is_fall_clip(path), extract_poses(path, estimator, cfg.MODEL_PATH, args.fps))
    falls = sum(expected for expected, _ in clips.values())
    print(f"{len(clips)} clips: {falls} falls, {len(clips) - falls} non-falls")

    if args.export:
        export_clips(clips, args.export, cfg.MODEL_PATH)
        print(f"skeletons saved to {args.export} ({args.export.stat().st_size // 1024} KB, no images)")

    stats = {name: clip_stats(frames, cfg.thresholds) for name, (_, frames) in clips.items()}
    print("\nCurrent thresholds:\n" + format_table(score_all(clips, cfg.thresholds), stats))

    if args.sweep:
        ranked = sweep(clips, cfg.thresholds)
        print(f"\nTop settings out of {len(ranked)} combinations:")
        for th, s in ranked[:5]:
            knobs = "  ".join(f"{k}={getattr(th, k)}" for k in SWEEP_GRID)
            print(f"  caught {s['caught']}/{s['falls']}  false alarms {s['false_alarms']}/{s['non_falls']}   {knobs}")
        best = ranked[0][0]
        print("\nBest settings on these clips:\n" + format_table(score_all(clips, best), stats))
        print("\nTo use them, set these defaults in FallThresholds (cv_engine/config.py):")
        for k in SWEEP_GRID:
            print(f"  {k}: float = {getattr(best, k)}")


if __name__ == "__main__":
    main()
