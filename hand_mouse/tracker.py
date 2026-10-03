import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from .config import Config

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "hand_landmarker.task"


def ensure_model(path: Path = DEFAULT_MODEL) -> Path:
    if not path.exists():
        print(f"모델 다운로드 중: {MODEL_URL}")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
        print(f"저장 완료: {path}")
    return path


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    # Windows 기본 백엔드(MSMF)는 카메라 여는 데 수 초~수십 초 걸리는 경우가 있어 DirectShow 사용
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"카메라 {index}번을 열 수 없습니다. --camera 번호를 바꿔 보세요.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


class HandTracker:
    def __init__(self, cfg: Config, model_path: Path = DEFAULT_MODEL) -> None:
        # model_asset_path는 mediapipe 네이티브 코드가 한글 등 비ASCII 경로를 못 열어서(errno=-1)
        # Python에서 직접 읽어 바이트로 전달
        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_buffer=ensure_model(model_path).read_bytes()),
            # VIDEO 모드: 손을 추적 중일 땐 손바닥 검출 단계를 건너뛰어 CPU 부담이 작음
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=cfg.min_detection_confidence,
            min_hand_presence_confidence=cfg.min_presence_confidence,
            min_tracking_confidence=cfg.min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, bgr_frame) -> vision.HandLandmarkerResult:
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        # VIDEO 모드는 타임스탬프가 엄격히 증가해야 함
        ts = max(int(time.monotonic() * 1000), self._last_ts + 1)
        self._last_ts = ts
        return self._landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

    def close(self) -> None:
        self._landmarker.close()


HAND_CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
