"""가상 손 자세로 제스처 판정 검증. 웹캠 없이 실행 가능."""

from dataclasses import dataclass, replace

import pytest

from hand_mouse.config import Config
from hand_mouse.gestures import GestureEngine, Mode


@dataclass(frozen=True)
class P:
    x: float
    y: float
    z: float = 0.0


# 손 좌표계: 손목 원점, 손가락은 -y 방향, 손목~중지 뿌리 = 1.0
MCP = {5: (0.25, -0.95), 9: (0.0, -1.0), 13: (-0.2, -0.95), 17: (-0.4, -0.85)}


def _finger(mcp: int, extended: bool) -> dict[int, P]:
    x, y = MCP[mcp]
    if extended:
        return {mcp: P(x, y), mcp + 1: P(x, y - 0.45), mcp + 2: P(x, y - 0.75), mcp + 3: P(x, y - 1.0)}
    # 손바닥 쪽으로 말아 쥔 상태
    return {mcp: P(x, y), mcp + 1: P(x, y - 0.1, -0.35), mcp + 2: P(x, y + 0.2, -0.4), mcp + 3: P(x, y + 0.35, -0.2)}


def hand(index=True, middle=True, ring=True, pinky=True, thumb_tip: P | None = None,
         index_tip: P | None = None) -> list[P]:
    pts: dict[int, P] = {0: P(0, 0), 1: P(0.3, -0.2), 2: P(0.5, -0.4), 3: P(0.6, -0.6), 4: P(0.75, -0.8)}
    for mcp, ext in zip(MCP, (index, middle, ring, pinky)):
        pts.update(_finger(mcp, ext))
    if index_tip:
        pts[8] = index_tip
    if thumb_tip:
        pts[4] = thumb_tip
    return [pts[i] for i in range(21)]


OPEN = hand()
PINCH_L = hand(index_tip=P(0.45, -1.3, -0.3), thumb_tip=P(0.47, -1.3, -0.3))
# 손 편 채 엄지만 접기 — 실측 평균(L≈0.55, R≈0.75)이 나오는 위치
THUMB_FOLD = hand(thumb_tip=P(0.45, -1.5, -0.2))
FIST = hand(False, False, False, False, thumb_tip=P(0.2, -0.75, -0.3))
V_POSE = hand(ring=False, pinky=False, thumb_tip=P(0.1, -0.6, -0.2))
V_POSE_THUMB_FOLDED = hand(ring=False, pinky=False, thumb_tip=P(0.45, -1.5, -0.2))


def to_image(world: list[P], dx: float = 0.0, dy: float = 0.0) -> list[P]:
    # 이미지 좌표로 축소·이동 (중지 뿌리가 화면 가운데 근처)
    return [P(0.5 + p.x * 0.15 + dx, 0.6 + p.y * 0.15 + dy, p.z) for p in world]


class Driver:
    def __init__(self, **cfg) -> None:
        self.engine = GestureEngine(Config(**cfg))
        self.t = 0.0

    def step(self, world: list[P] | None, dx: float = 0.0, dy: float = 0.0, dt: float = 1 / 30):
        self.t += dt
        if world is None:
            return self.engine.update(None, None, self.t)
        return self.engine.update(to_image(world, dx, dy), world, self.t)


def test_open_hand_moves_cursor_without_clicks():
    d = Driver()
    act = d.step(OPEN)
    assert act.mode is Mode.MOVE
    assert act.cursor_abs is not None and all(0 <= v <= 1 for v in act.cursor_abs)
    assert not (act.left_down or act.left_up or act.right_click or act.scroll)


def test_pose_metrics_are_well_separated():
    d = Driver()
    open_dbg = d.step(OPEN).debug
    cfg = d.engine.cfg
    assert open_dbg["pinch_l"] > cfg.pinch_release and open_dbg["pinch_r"] > cfg.pinch_release
    assert Driver().step(PINCH_L).debug["pinch_l"] < cfg.pinch_press
    fold = Driver().step(THUMB_FOLD).debug
    assert fold["pinch_r"] < cfg.thumb_fold_press and fold["pinch_l"] > cfg.pinch_press


def test_left_pinch_needs_debounce_then_holds_and_releases():
    d = Driver()
    d.step(OPEN)
    assert not d.step(PINCH_L).left_down  # 1프레임은 무시
    down = d.step(PINCH_L)
    assert down.left_down and down.mode is Mode.DRAG
    held = [d.step(PINCH_L) for _ in range(5)]
    assert all(a.mode is Mode.DRAG and not a.left_down for a in held)
    up = d.step(OPEN)
    assert up.left_up
    assert d.step(OPEN).mode is Mode.MOVE


def test_drag_moves_cursor_after_freeze():
    d = Driver()
    d.step(OPEN)
    d.step(PINCH_L)
    down = d.step(PINCH_L)
    assert down.left_down and down.cursor_abs is None  # 누른 직후 커서 고정
    acts = [d.step(PINCH_L, dx=0.01 * i) for i in range(1, 15)]
    assert acts[-1].cursor_abs is not None
    xs = [a.cursor_abs[0] for a in acts if a.cursor_abs]
    assert xs == sorted(xs) and xs[-1] > xs[0]


def test_thumb_fold_right_clicks_once_after_hold():
    d = Driver()
    d.step(OPEN)
    acts = [d.step(THUMB_FOLD) for _ in range(10)]
    frames = d.engine.cfg.thumb_fold_frames
    assert [a.right_click for a in acts].index(True) == frames - 1  # N프레임 유지 후에야 실행
    assert sum(a.right_click for a in acts) == 1
    assert not any(a.left_down for a in acts)
    d.step(OPEN)
    assert sum(d.step(THUMB_FOLD).right_click for _ in range(10)) == 1


def test_moving_thumb_to_index_does_not_right_click():
    # 좌클릭하려고 엄지를 검지로 가져가는 도중 R이 잠깐 기준 아래로 내려가도 우클릭은 안 나감
    d = Driver()
    d.step(OPEN)
    start_thumb, end_thumb = OPEN[4], PINCH_L[4]
    start_index, end_index = OPEN[8], PINCH_L[8]
    acts = []
    for i in range(1, 5):
        r = i / 4
        lerp = lambda a, b: P(a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r, a.z + (b.z - a.z) * r)
        acts.append(d.step(hand(thumb_tip=lerp(start_thumb, end_thumb), index_tip=lerp(start_index, end_index))))
    acts += [d.step(PINCH_L) for _ in range(3)]
    assert any(a.debug["pinch_r"] < d.engine.cfg.thumb_fold_press for a in acts)  # 실제로 구간을 지나감
    assert not any(a.right_click for a in acts)
    assert sum(a.left_down for a in acts) == 1


def test_left_click_allowed_right_after_right_click():
    d = Driver()
    d.step(OPEN)
    assert sum(d.step(THUMB_FOLD).right_click for _ in range(6)) == 1
    acts = [d.step(PINCH_L) for _ in range(3)]  # 엄지를 펴지 않고 바로 검지로 핀치
    assert sum(a.left_down for a in acts) == 1


def test_fist_pauses_cursor_and_never_clicks():
    d = Driver()
    d.step(OPEN)
    acts = [d.step(FIST, dx=0.01 * i) for i in range(10)]
    assert all(a.mode is Mode.PAUSE for a in acts)
    assert not any(a.cursor_abs or a.left_down or a.right_click for a in acts)


def test_v_pose_scrolls_with_vertical_motion():
    d = Driver()
    step = d.engine.cfg.scroll_step
    d.step(V_POSE)
    # 손을 위로(y 감소) → 양수(위) 스크롤. 필터 지연이 있으므로 충분히 이동 후 합계 확인
    up = sum(d.step(V_POSE, dy=-step * 0.5 * i).scroll for i in range(1, 30))
    assert up > 0
    d2 = Driver()
    d2.step(V_POSE)
    down = sum(d2.step(V_POSE, dy=step * 0.5 * i).scroll for i in range(1, 30))
    assert down < 0
    assert d2.step(V_POSE).cursor_abs is None


def test_v_pose_with_folded_thumb_scrolls_not_right_clicks():
    d = Driver()
    acts = [d.step(V_POSE_THUMB_FOLDED) for _ in range(10)]
    assert all(a.mode is Mode.SCROLL for a in acts)
    assert not any(a.right_click for a in acts)


def test_hand_lost_during_drag_releases_button():
    d = Driver()
    d.step(OPEN)
    d.step(PINCH_L)
    assert d.step(PINCH_L).left_down
    lost = d.step(None)
    assert lost.mode is Mode.NO_HAND and lost.left_up
    assert not d.step(None).left_up  # 중복 해제 없음


def test_relative_mode_emits_delta_and_fist_acts_as_clutch():
    d = Driver(relative=True)
    d.step(OPEN)
    acts = [d.step(OPEN, dx=0.005 * i) for i in range(1, 10)]
    assert all(a.cursor_abs is None for a in acts)
    assert sum(a.cursor_delta[0] for a in acts if a.cursor_delta) > 0
    # 주먹 쥐고 손을 왼쪽으로 크게 옮겨도 커서는 그대로, 다시 펴면 튀지 않음
    for i in range(10):
        d.step(FIST, dx=0.045 - 0.01 * i)
    resumed = d.step(OPEN, dx=-0.055)
    assert resumed.cursor_delta is None or abs(resumed.cursor_delta[0]) < 0.05


@pytest.mark.parametrize("pose", [OPEN, PINCH_L, THUMB_FOLD, FIST, V_POSE, V_POSE_THUMB_FOLDED])
def test_detection_is_invariant_to_hand_scale(pose):
    # 손이 카메라에서 멀어져 작아져도(world 좌표 축소) 같은 판정
    small = [replace(p, x=p.x * 0.6, y=p.y * 0.6, z=p.z * 0.6) for p in pose]
    a, b = Driver(), Driver()
    modes_a = [a.step(pose).mode for _ in range(3)]
    modes_b = [b.step(small).mode for _ in range(3)]
    assert modes_a == modes_b
