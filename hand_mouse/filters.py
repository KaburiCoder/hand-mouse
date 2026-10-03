import math


class _LowPass:
    def __init__(self) -> None:
        self.value: float | None = None

    def apply(self, x: float, alpha: float) -> float:
        self.value = x if self.value is None else self.value + alpha * (x - self.value)
        return self.value


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """속도 적응형 저역통과 필터 (Casiez et al., 2012).

    천천히 움직일 땐 강하게 평활해 떨림을 없애고, 빠르게 움직일 땐 약하게 평활해 지연을 줄인다.
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x = _LowPass()
        self._dx = _LowPass()
        self._last_t: float | None = None
        self._last_raw: float | None = None

    def __call__(self, x: float, t: float) -> float:
        if self._last_t is None or self._last_raw is None or t <= self._last_t:
            self._last_t, self._last_raw = t, x
            self._dx.apply(0.0, 1.0)
            return self._x.apply(x, 1.0)

        dt = t - self._last_t
        dx = self._dx.apply((x - self._last_raw) / dt, _alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(dx)
        self._last_t, self._last_raw = t, x
        return self._x.apply(x, _alpha(cutoff, dt))


class OneEuroFilter2D:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self.fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def reset(self) -> None:
        self.fx.reset()
        self.fy.reset()

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        return self.fx(x, t), self.fy(y, t)
