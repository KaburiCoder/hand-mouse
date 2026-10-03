import sys


def disable_power_throttling() -> bool:
    """Windows 11의 전원 제한(EcoQoS)을 이 프로세스에서 끈다.

    Windows는 포커스 없는 백그라운드 프로세스를 효율 코어/저클럭으로 돌리는데, 손 마우스는 항상
    다른 창을 조작하는 동안 뒤에서 돌기 때문에 여기에 걸린다. 측정 결과 추론 시간이 8ms → 90ms대로
    10배 가까이 느려졌고, 끄면 8~9ms로 일정하게 유지됨.
    """
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    class ProcessPowerThrottlingState(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        ]

    process_power_throttling = 4  # PROCESS_INFORMATION_CLASS::ProcessPowerThrottling
    execution_speed = 0x1  # PROCESS_POWER_THROTTLING_EXECUTION_SPEED

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # 핸들은 64비트 — restype/argtypes를 지정하지 않으면 int로 잘려 호출이 실패함
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetProcessInformation.restype = wintypes.BOOL

    # ControlMask에 EXECUTION_SPEED를 지정하고 StateMask를 0으로 → 항상 고성능으로 실행
    state = ProcessPowerThrottlingState(1, execution_speed, 0)
    return bool(
        kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(), process_power_throttling, ctypes.byref(state), ctypes.sizeof(state)
        )
    )
