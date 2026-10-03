"""랜드마크 → 마우스 동작 변환. 카메라/OS와 무관한 순수 로직이라 단독 테스트 가능."""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Sequence

from .config import Config
from .filters import OneEuroFilter2D

WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

# (MCP, PIP, TIP) — 검지, 중지, 약지, 소지
FINGERS = (
    (INDEX_MCP, INDEX_PIP, INDEX_TIP),
    (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP),
    (RING_MCP, RING_PIP, RING_TIP),
    (PINKY_MCP, PINKY_PIP, PINKY_TIP),
)


class Point(Protocol):
    x: float
    y: float
    z: float


class Mode(Enum):
    NO_HAND = "no hand"
    MOVE = "move"
    DRAG = "drag"
    SCROLL = "scroll"
    PAUSE = "pause"


@dataclass
class Action:
    mode: Mode
    cursor_abs: tuple[float, float] | None = None    # absolute 모드: 화면 정규화 좌표 (0~1)
    cursor_delta: tuple[float, float] | None = None  # relative 모드: 화면 크기 대비 이동량
    left_down: bool = False
    left_up: bool = False
    right_click: bool = False
    scroll: int = 0  # 휠 칸 수, 양수 = 위로
    debug: dict[str, float] = field(default_factory=dict)


def _dist(a: Point, b: Point) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


class GestureEngine:
    """프레임마다 update()를 호출하면 그 프레임에 수행할 마우스 동작을 돌려준다.

    - image_lm: 이미지 정규화 좌표 랜드마크 → 커서 위치
    - world_lm: 3D 실측(m) 랜드마크 → 핀치/손가락 판정 (손 방향·카메라 거리에 덜 민감)
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.filter = OneEuroFilter2D(cfg.min_cutoff, cfg.beta, cfg.d_cutoff)
        self.reset()

    def reset(self) -> None:
        self.filter.reset()
        self.left_held = False
        self.right_latched = False
        self.left_count = 0
        self.right_count = 0
        self.freeze_until = 0.0
        self.prev_pos: tuple[float, float] | None = None
        self.scroll_ref: float | None = None

    def update(
        self,
        image_lm: Sequence[Point] | None,
        world_lm: Sequence[Point] | None,
        t: float,
    ) -> Action:
        cfg = self.cfg

        if image_lm is None or world_lm is None:
            # 손이 사라지면 누르고 있던 버튼을 반드시 뗀다 (드래그가 걸린 채 남지 않도록)
            release = self.left_held
            self.reset()
            return Action(Mode.NO_HAND, left_up=release)

        w = world_lm
        hand = _dist(w[WRIST], w[MIDDLE_MCP]) or 1e-6
        pinch_l = _dist(w[THUMB_TIP], w[INDEX_TIP]) / hand
        pinch_r = _dist(w[THUMB_TIP], w[MIDDLE_TIP]) / hand
        extended = [
            _dist(w[WRIST], w[tip]) > _dist(w[WRIST], w[pip]) * cfg.extended_ratio
            for _, pip, tip in FINGERS
        ]
        folded = [
            _dist(w[WRIST], w[tip]) < _dist(w[WRIST], w[mcp]) * cfg.fist_ratio
            for mcp, _, tip in FINGERS
        ]

        anchor = image_lm[cfg.anchor]
        fx, fy = self.filter(anchor.x, anchor.y, t)
        debug = {"pinch_l": pinch_l, "pinch_r": pinch_r}

        # 1) 드래그(왼쪽 버튼 유지) 중이면 다른 제스처보다 우선 — 뗄 때까지 유지
        if self.left_held:
            act = Action(Mode.DRAG, debug=debug)
            if pinch_l > cfg.pinch_release:
                act.left_up = True
                self.left_held = False
                self.left_count = 0
                self.freeze_until = t + cfg.click_freeze_s
            self._emit_cursor(act, fx, fy, t)
            return act

        # 2) 스크롤: 검지+중지만 펴고 약지·소지는 접은 "V" 자세, 위아래로 움직이면 휠.
        #    V자에서 엄지를 접는 경우가 많아(L≈0.55) 엄지 조건은 좌클릭 핀치만 아니면 됨
        if extended[0] and extended[1] and not extended[2] and not extended[3] and pinch_l > cfg.pinch_press:
            act = Action(Mode.SCROLL, debug=debug)
            if self.scroll_ref is None:
                self.scroll_ref = fy
            steps = int((self.scroll_ref - fy) / cfg.scroll_step)  # 손을 올리면(y 감소) 위로 스크롤
            if steps:
                act.scroll = steps
                self.scroll_ref -= steps * cfg.scroll_step
            self._skip_cursor(fx, fy)
            self.left_count = self.right_count = 0
            return act
        self.scroll_ref = None

        # 3) 주먹: 커서 정지. relative 모드에서는 "마우스 들기"처럼 손 위치를 옮기는 용도
        if all(folded):
            self._skip_cursor(fx, fy)
            self.left_count = self.right_count = 0
            return Action(Mode.PAUSE, debug=debug)

        # 4) 이동 + 클릭. 좌클릭 = 엄지-검지 핀치, 우클릭 = 엄지만 접기 (L은 핀치보다 멀고 R만 가까움)
        act = Action(Mode.MOVE, debug=debug)
        left_candidate = pinch_l < cfg.pinch_press
        right_candidate = pinch_r < cfg.thumb_fold_press and not left_candidate
        self.left_count = self.left_count + 1 if left_candidate else 0
        self.right_count = self.right_count + 1 if right_candidate else 0

        if self.right_latched and pinch_r > cfg.thumb_fold_release:
            self.right_latched = False

        if self.left_count >= cfg.debounce_frames:
            act.mode = Mode.DRAG
            act.left_down = True
            self.left_held = True
            self.freeze_until = t + cfg.click_freeze_s
        elif self.right_count >= cfg.thumb_fold_frames and not self.right_latched:
            act.right_click = True
            self.right_latched = True
            self.freeze_until = t + cfg.click_freeze_s

        self._emit_cursor(act, fx, fy, t)
        return act

    def _emit_cursor(self, act: Action, fx: float, fy: float, t: float) -> None:
        if t < self.freeze_until:
            self._skip_cursor(fx, fy)
            return
        if self.cfg.relative:
            if self.prev_pos is not None:
                g = self.cfg.gain
                act.cursor_delta = ((fx - self.prev_pos[0]) * g, (fy - self.prev_pos[1]) * g)
            self.prev_pos = (fx, fy)
        else:
            x0, y0, x1, y1 = self.cfg.region
            nx = min(max((fx - x0) / (x1 - x0), 0.0), 1.0)
            ny = min(max((fy - y0) / (y1 - y0), 0.0), 1.0)
            act.cursor_abs = (nx, ny)

    def _skip_cursor(self, fx: float, fy: float) -> None:
        # 커서를 움직이지 않는 프레임에도 기준 위치는 갱신 → relative 모드에서 재개 시 튀지 않음
        self.prev_pos = (fx, fy)
