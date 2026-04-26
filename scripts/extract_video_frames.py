import argparse
from pathlib import Path

import cv2


def extract_frames(
    input_video: Path,
    output_dir: Path,
    prefix: str,
    target_fps: float,
    max_frames: int,
    start_sec: float,
    end_sec: float,
) -> int:
    if not input_video.exists():
        raise FileNotFoundError(f"Video not found: {input_video}")

    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(input_video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps is None or src_fps <= 0:
        src_fps = 30.0

    frame_interval = max(1, int(round(src_fps / max(0.1, target_fps))))

    start_frame = int(max(0.0, start_sec) * src_fps)
    end_frame = int(end_sec * src_fps) if end_sec > 0 else -1

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    frame_idx = start_frame
    saved = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if end_frame > 0 and frame_idx > end_frame:
            break

        if (frame_idx - start_frame) % frame_interval == 0:
            out_name = f"{prefix}_{saved + 1:04d}.jpg"
            out_path = output_dir / out_name
            cv2.imwrite(str(out_path), frame)
            saved += 1

            if max_frames > 0 and saved >= max_frames:
                break

        frame_idx += 1

    cap.release()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract image frames from a video for liveness attack dataset")
    parser.add_argument("--input-video", required=True, help="Path to input video")
    parser.add_argument("--output-dir", default="dataset/liveness_eval/attack", help="Output folder for extracted frames")
    parser.add_argument("--prefix", default="attack_video", help="Output filename prefix")
    parser.add_argument("--fps", type=float, default=2.0, help="Target extraction FPS")
    parser.add_argument("--max-frames", type=int, default=120, help="Maximum number of frames to save (<=0 means no limit)")
    parser.add_argument("--start-sec", type=float, default=0.0, help="Start extraction from this second")
    parser.add_argument("--end-sec", type=float, default=-1.0, help="End extraction at this second (<=0 means until video ends)")
    args = parser.parse_args()

    input_video = Path(args.input_video)
    output_dir = Path(args.output_dir)

    saved = extract_frames(
        input_video=input_video,
        output_dir=output_dir,
        prefix=args.prefix,
        target_fps=args.fps,
        max_frames=args.max_frames,
        start_sec=args.start_sec,
        end_sec=args.end_sec,
    )

    print(f"Saved {saved} frames to {output_dir}")


if __name__ == "__main__":
    main()
