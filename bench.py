"""CPU 성능 측정.

  uv run bench.py                       # 웹캠으로 10초 측정
  uv run bench.py --seconds 30
  uv run bench.py --image hand.jpg      # 웹캠 없이 이미지로 추론 속도만 측정
"""

import argparse
import os
import statistics
import time
from pathlib import Path

import hand_mouse  # noqa: F401  (mediapipe 로그 억제 설정)
import cv2
import numpy as np

from hand_mouse.config import Config
from hand_mouse.power import disable_power_throttling
from hand_mouse.tracker import HandTracker, open_camera


def report(label: str, infer_ms: list[float], wall_s: float, cpu_s: float, frames: int, hands: int) -> None:
    infer_sorted = sorted(infer_ms)
    p95 = infer_sorted[int(len(infer_sorted) * 0.95) - 1] if len(infer_sorted) >= 20 else max(infer_sorted)
    cores = os.cpu_count() or 1
    cpu_pct = cpu_s / wall_s * 100
    print(f"\n=== {label} ===")
    print(f"프레임        {frames}  (손 검출 {hands}프레임, {hands / frames * 100:.0f}%)")
    print(f"처리 FPS      {frames / wall_s:.1f}")
    print(f"추론 시간     평균 {statistics.mean(infer_ms):.1f}ms / 중앙값 {statistics.median(infer_ms):.1f}ms / p95 {p95:.1f}ms")
    print(f"추론만의 한계 {1000 / statistics.mean(infer_ms):.0f} FPS")
    print(f"CPU 사용량    {cpu_pct:.0f}% (코어 1개 = 100%) / 전체 {cores}코어 대비 {cpu_pct / cores:.1f}%")


def bench_camera(args: argparse.Namespace, tracker: HandTracker) -> None:
    cap = open_camera(args.camera, args.width, args.height)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"카메라 {w}x{h}, {args.seconds}초 측정. 카메라 앞에서 손을 움직여 주세요...")
    for _ in range(10):  # 워밍업 (카메라 노출 안정화 + 모델 초기화)
        ok, frame = cap.read()
        if ok:
            tracker.detect(frame)

    infer_ms: list[float] = []
    hands = 0
    wall0, cpu0 = time.perf_counter(), time.process_time()
    while time.perf_counter() - wall0 < args.seconds:
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        result = tracker.detect(cv2.flip(frame, 1))
        infer_ms.append((time.perf_counter() - t0) * 1000)
        hands += bool(result.hand_landmarks)
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    cap.release()
    report(f"웹캠 {w}x{h}", infer_ms, wall, cpu, len(infer_ms), hands)
    print("※ 처리 FPS가 카메라 FPS(보통 30)와 비슷하면 병목은 CPU가 아니라 카메라입니다.")


def bench_image(args: argparse.Namespace, tracker: HandTracker) -> None:
    # cv2.imread는 Windows 한글 경로를 못 읽어서 바이트로 읽은 뒤 디코딩
    frame = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR) if args.image.exists() else None
    if frame is None:
        raise SystemExit(f"이미지를 읽을 수 없습니다: {args.image}")
    frame = cv2.resize(frame, (args.width, args.height))
    for _ in range(5):
        tracker.detect(frame)

    infer_ms: list[float] = []
    hands = 0
    wall0, cpu0 = time.perf_counter(), time.process_time()
    for _ in range(args.iterations):
        if args.fps:
            time.sleep(1 / args.fps)  # 웹캠처럼 프레임 사이에 쉬는 시간을 둠
        t0 = time.perf_counter()
        result = tracker.detect(frame)
        infer_ms.append((time.perf_counter() - t0) * 1000)
        hands += bool(result.hand_landmarks)
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    pace = f", {args.fps:g}fps 간격" if args.fps else ", 연속"
    report(f"이미지 {args.image.name} ({args.width}x{args.height}{pace})", infer_ms, wall, cpu, args.iterations, hands)
    if not args.fps:
        print("※ 쉬지 않고 연속 추론하므로 CPU 사용량이 실사용보다 높게 나옵니다. 웹캠과 비슷한 조건은 --fps 30")


def main() -> None:
    p = argparse.ArgumentParser(description="손 인식 CPU 성능 측정")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--image", type=Path, help="웹캠 대신 이미지 파일로 측정")
    p.add_argument("--iterations", type=int, default=200, help="이미지 모드 반복 횟수")
    p.add_argument("--fps", type=float, default=0, help="이미지 모드에서 웹캠처럼 프레임 간격 두기 (예: 30)")
    p.add_argument("--no-power-fix", action="store_true", help="Windows 전원 제한(EcoQoS) 해제 안 함 (비교용)")
    args = p.parse_args()

    if args.no_power_fix:
        print("전원 제한 해제: 사용 안 함 (--no-power-fix)")
    else:
        print(f"전원 제한 해제: {'적용' if disable_power_throttling() else '해당 없음/실패'}")

    tracker = HandTracker(Config())
    try:
        bench_image(args, tracker) if args.image else bench_camera(args, tracker)
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
