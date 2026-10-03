"""손 제스처 마우스.

  uv run main.py                 # 실행 (미리보기 창 표시)
  uv run main.py --dry-run       # 마우스는 움직이지 않고 인식만 확인
  uv run main.py --relative      # 트랙패드 방식 (주먹 = 손 떼고 위치 옮기기)

미리보기 창 단축키: Space = 마우스 제어 켜기/끄기, ESC/q = 종료
"""

import argparse
import time

import hand_mouse  # noqa: F401  (mediapipe 로그 억제 설정)
import cv2

from hand_mouse.config import Config
from hand_mouse.gestures import Action, GestureEngine, Mode
from hand_mouse.mouse import Mouse
from hand_mouse.power import disable_power_throttling
from hand_mouse.tracker import HAND_CONNECTIONS, HandTracker, open_camera

MODE_COLORS = {
    Mode.NO_HAND: (128, 128, 128),
    Mode.MOVE: (0, 200, 0),
    Mode.DRAG: (0, 0, 255),
    Mode.SCROLL: (255, 160, 0),
    Mode.PAUSE: (0, 200, 255),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="웹캠 손 제스처로 마우스 제어")
    p.add_argument("--camera", type=int, default=0, help="카메라 번호 (기본 0)")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--relative", action="store_true", help="트랙패드(상대 이동) 방식")
    p.add_argument("--gain", type=float, help="relative 모드 감도 (기본 2.5)")
    p.add_argument("--press", type=float, help="좌클릭 누름 기준 L (기본 0.35, 미리보기 값 참고)")
    p.add_argument("--release", type=float, help="좌클릭 뗌 기준 L (기본 0.50, press보다 커야 함)")
    p.add_argument("--right-press", type=float, help="우클릭(엄지 접기) 기준 R (기본 0.90)")
    p.add_argument("--right-release", type=float, help="우클릭 해제 기준 R (기본 1.05, right-press보다 커야 함)")
    p.add_argument("--dry-run", action="store_true", help="마우스를 실제로 움직이지 않음")
    p.add_argument("--no-preview", action="store_true", help="미리보기 창 숨김 (종료는 Ctrl+C)")
    p.add_argument("--paused", action="store_true", help="마우스 제어 꺼진 상태로 시작 (Space로 켜기)")
    return p.parse_args()


def apply_action(mouse: Mouse, act: Action) -> None:
    if act.cursor_abs:
        mouse.move_abs(*act.cursor_abs)
    elif act.cursor_delta:
        mouse.move_rel(*act.cursor_delta)
    if act.left_down:
        mouse.left_down()
    if act.left_up:
        mouse.left_up()
    if act.right_click:
        mouse.right_click()
    if act.scroll:
        mouse.scroll(act.scroll)


def draw_overlay(frame, result, act: Action, cfg: Config, enabled: bool, fps: float, infer_ms: float) -> None:
    h, w = frame.shape[:2]
    if not cfg.relative:
        x0, y0, x1, y1 = cfg.region
        cv2.rectangle(frame, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), (200, 200, 200), 1)

    color = MODE_COLORS[act.mode]
    if result.hand_landmarks:
        pts = [(int(p.x * w), int(p.y * h)) for p in result.hand_landmarks[0]]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (255, 255, 255), 1)
        for pt in pts:
            cv2.circle(frame, pt, 3, color, -1)
        cv2.circle(frame, pts[cfg.anchor], 7, color, 2)

    status = "ON" if enabled else "OFF (Space)"
    lines = [
        f"{act.mode.value.upper()}  control {status}",
        f"fps {fps:4.1f}  infer {infer_ms:4.1f}ms",
    ]
    # 임계값 튜닝용: L이 기준 아래면 좌클릭, R이 기준 아래면(엄지 접기) 우클릭
    if act.debug:
        lines.append(
            f"L {act.debug['pinch_l']:.2f} (click<{cfg.pinch_press})"
            f"  R {act.debug['pinch_r']:.2f} (right<{cfg.thumb_fold_press})"
        )
    for i, text in enumerate(lines):
        y = 22 + i * 22
        cv2.putText(frame, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def main() -> None:
    args = parse_args()
    cfg = Config(relative=args.relative)
    if args.gain is not None:
        cfg.gain = args.gain
    if args.press is not None:
        cfg.pinch_press = args.press
    if args.release is not None:
        cfg.pinch_release = args.release
    if args.right_press is not None:
        cfg.thumb_fold_press = args.right_press
    if args.right_release is not None:
        cfg.thumb_fold_release = args.right_release
    if cfg.pinch_release <= cfg.pinch_press:
        raise SystemExit("--release는 --press보다 커야 합니다.")
    if cfg.thumb_fold_release <= cfg.thumb_fold_press:
        raise SystemExit("--right-release는 --right-press보다 커야 합니다.")

    disable_power_throttling()

    tracker = HandTracker(cfg)
    cap = open_camera(args.camera, args.width, args.height)
    engine = GestureEngine(cfg)
    mouse = Mouse(dry_run=args.dry_run)
    enabled = not args.paused
    preview = not args.no_preview

    print(f"화면 {mouse.width}x{mouse.height}, 카메라 {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}, 모드 {'relative' if cfg.relative else 'absolute'}"
          f"{' (dry-run)' if args.dry_run else ''}")
    print("종료: 미리보기 창에서 ESC/q, 또는 터미널에서 Ctrl+C")

    fps = 0.0
    last = time.perf_counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("카메라 프레임을 읽지 못했습니다.")
                break
            frame = cv2.flip(frame, 1)  # 거울 모드: 손을 오른쪽으로 → 커서도 오른쪽

            t0 = time.perf_counter()
            result = tracker.detect(frame)
            infer_ms = (time.perf_counter() - t0) * 1000

            if result.hand_landmarks:
                act = engine.update(result.hand_landmarks[0], result.hand_world_landmarks[0], time.monotonic())
            else:
                act = engine.update(None, None, time.monotonic())
            if enabled:
                apply_action(mouse, act)

            now = time.perf_counter()
            fps = fps * 0.9 + 0.1 / max(now - last, 1e-6)
            last = now

            if preview:
                draw_overlay(frame, result, act, cfg, enabled, fps, infer_ms)
                cv2.imshow("hand-mouse", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord(" "):
                    enabled = not enabled
                    # 켜고 끌 때 버튼이 눌린 채 남지 않도록 상태 초기화
                    mouse.release_all()
                    engine.reset()
    except KeyboardInterrupt:
        pass
    finally:
        mouse.release_all()
        cap.release()
        tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
