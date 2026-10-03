from dataclasses import dataclass


@dataclass
class Config:
    # --- 커서 ---
    # absolute: 손 위치 = 화면 위치 / relative: 트랙패드처럼 이동량만 반영 (주먹 = 손 떼기)
    relative: bool = False
    # 카메라 프레임 중 화면 전체에 대응시킬 영역 (x0, y0, x1, y1), 0~1 정규화 좌표.
    # 가장자리까지 손을 뻗지 않아도 되도록 중앙 일부만 사용. 아래쪽은 손목이 잘리므로 더 여유를 둠
    region: tuple[float, float, float, float] = (0.2, 0.15, 0.8, 0.7)
    # relative 모드 감도 (카메라 이동량 → 화면 이동량 배율)
    gain: float = 2.5
    # 커서 기준점 랜드마크. 9 = 중지 뿌리(손바닥 중심) — 핀치할 때 거의 안 움직여 클릭 시 커서 튐이 적음
    anchor: int = 9

    # --- One Euro Filter (떨림 제거) ---
    # min_cutoff ↓ = 정지 시 더 안정 / beta ↑ = 빠른 이동 시 지연 감소
    min_cutoff: float = 1.0
    beta: float = 10.0
    d_cutoff: float = 1.0

    # --- 좌클릭: 엄지-검지 핀치 (L = 엄지끝~검지끝 거리 / 손 크기, 3D world 좌표 기준) ---
    # 실측(2026-10-03): 붙임 0.1~0.3, 뗌 0.7~1.2, 엄지 접기(우클릭) 중 0.55
    # → press는 붙임 최대값 바로 위, 엄지 접기 값(0.55)과는 충분히 떨어지게
    pinch_press: float = 0.35    # 이보다 가까우면 누름
    pinch_release: float = 0.50  # 이보다 멀어지면 뗌 (히스테리시스)
    debounce_frames: int = 2     # 연속 N프레임 유지돼야 누름으로 인정 (제스처 전환 중 오클릭 방지)
    click_freeze_s: float = 0.15  # 누름/뗌 직후 커서 고정 시간

    # --- 우클릭: 손 편 채 엄지만 접기 (R = 엄지끝~중지끝 거리 / 손 크기) ---
    # 실측: 접음 평균 0.75, 폄 평균 1.25 → 사이에 기준
    thumb_fold_press: float = 0.90
    thumb_fold_release: float = 1.05
    # 엄지를 검지로 가져가는(좌클릭) 도중에도 R이 잠깐 내려가므로 좌클릭보다 오래 유지돼야 인정
    thumb_fold_frames: int = 5  # 30fps 기준 약 0.17초

    # --- 손가락 펴짐/접힘 판정 ---
    extended_ratio: float = 1.15  # 손목→끝 거리가 손목→PIP 거리의 이 배수보다 크면 "펴짐"
    fist_ratio: float = 1.1       # 손목→끝 거리가 손목→MCP 거리의 이 배수보다 작으면 "완전히 접힘"

    # --- 스크롤 ---
    scroll_step: float = 0.03  # 손을 카메라 높이의 이 비율만큼 움직일 때마다 휠 1칸

    # --- 인식 ---
    min_detection_confidence: float = 0.6
    min_presence_confidence: float = 0.6
    min_tracking_confidence: float = 0.5
