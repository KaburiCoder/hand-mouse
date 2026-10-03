import sys


class Mouse:
    """OS 마우스 이벤트 주입. dry_run이면 아무것도 하지 않는다 (제스처 인식만 확인할 때)."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        # pyautogui는 import 시점에 SetProcessDPIAware()를 호출 → 125%/150% 배율에서도 실제 픽셀 좌표 사용
        import pyautogui

        pyautogui.FAILSAFE = False  # 손 제어 중 화면 모서리 도달은 정상 동작
        pyautogui.PAUSE = 0
        self._pg = pyautogui
        # 주 모니터만 대상
        self.width, self.height = pyautogui.size()
        self._pos = [float(v) for v in pyautogui.position()]
        self._left_pressed = False
        # Windows는 휠 1칸 = 120 (WHEEL_DELTA). pyautogui가 값을 그대로 넘기므로 직접 곱해야 함
        self._wheel_unit = 120 if sys.platform == "win32" else 1

    def move_abs(self, nx: float, ny: float) -> None:
        self._pos = [nx * (self.width - 1), ny * (self.height - 1)]
        self._move()

    def move_rel(self, dx: float, dy: float) -> None:
        # 정수 반올림으로 작은 이동이 사라지지 않도록 float 위치를 따로 누적
        self._pos[0] = min(max(self._pos[0] + dx * self.width, 0), self.width - 1)
        self._pos[1] = min(max(self._pos[1] + dy * self.height, 0), self.height - 1)
        self._move()

    def _move(self) -> None:
        if not self.dry_run:
            self._pg.moveTo(round(self._pos[0]), round(self._pos[1]))

    def left_down(self) -> None:
        self._left_pressed = True
        if not self.dry_run:
            self._pg.mouseDown(button="left")

    def left_up(self) -> None:
        self._left_pressed = False
        if not self.dry_run:
            self._pg.mouseUp(button="left")

    def right_click(self) -> None:
        if not self.dry_run:
            self._pg.click(button="right")

    def scroll(self, steps: int) -> None:
        if not self.dry_run:
            self._pg.scroll(steps * self._wheel_unit)

    def release_all(self) -> None:
        if self._left_pressed:
            self.left_up()
