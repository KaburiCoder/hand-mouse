# hand-mouse

웹캠으로 손을 인식해 마우스를 제어합니다. GPU 없이 CPU만으로 동작합니다.

- 손 인식: MediaPipe Hand Landmarker (21개 관절, 3D 좌표)
- 떨림 제거: One Euro Filter
- 마우스 제어: pyautogui

## 다른 PC로 옮기기

`.venv` 폴더는 빼고 복사하세요(PC마다 새로 만들어집니다). `hand_landmarker.task`(7.8MB)는
첫 실행 때 자동으로 받지만, 인터넷이 안 되는 PC라면 같이 복사하면 됩니다.

## 설치 및 실행

[uv](https://docs.astral.sh/uv/)를 사용합니다. Python이 없어도 uv가 알아서 받습니다.

```powershell
# uv 설치 (한 번만)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd hand-mouse
uv run bench.py              # 1) CPU 성능 측정 (10초)
uv run main.py --dry-run     # 2) 마우스는 그대로 두고 인식만 확인
uv run main.py               # 3) 실제 마우스 제어
```

uv 없이 pip을 쓰려면 다음과 같이 합니다.

```powershell
python -m venv .venv; .venv\Scripts\activate
pip install mediapipe opencv-python pyautogui
python main.py
```

## 제스처

| 동작 | 제스처 |
|---|---|
| 커서 이동 | 손을 편 채로 움직이기 (손바닥 중심 기준) |
| 좌클릭 | 엄지와 검지 끝을 붙였다 떼기 |
| 드래그 | 엄지와 검지를 붙인 채로 이동 |
| 우클릭 | 손을 편 채 엄지만 손바닥 쪽으로 접기 (약 0.2초 유지) |
| 스크롤 | 검지·중지만 펴고(V자) 위아래로 움직이기 |
| 일시정지 | 주먹 쥐기 (커서 멈춤) |

미리보기 창 단축키: **Space** = 마우스 제어 켜기/끄기, **ESC / q** = 종료

## 옵션

```
uv run main.py --help

--camera N        카메라 번호 (기본 0, 안 열리면 1, 2… 시도)
--relative        트랙패드 방식: 이동량만 반영, 주먹 = 손 떼고 위치 옮기기
--gain 2.5        relative 모드 감도
--press 0.35          좌클릭 누름 기준 (L)
--release 0.50        좌클릭 뗌 기준 (L)
--right-press 0.90    우클릭(엄지 접기) 기준 (R)
--right-release 1.05  우클릭 해제 기준 (R)
--dry-run         마우스를 실제로 움직이지 않음
--no-preview      미리보기 창 없이 실행 (종료: Ctrl+C)
--paused          제어 꺼진 상태로 시작
```

```
uv run bench.py --seconds 30                 # 웹캠 측정 시간 변경
uv run bench.py --image hand.jpg             # 웹캠 없이 이미지로 추론 속도 측정
uv run bench.py --image hand.jpg --fps 30    # 웹캠과 같은 간격으로 측정
uv run bench.py --no-power-fix               # 전원 제한 해제 없이 측정 (비교용)
```

### Windows 전원 제한(EcoQoS)

Windows 11은 포커스 없는 백그라운드 프로세스를 저클럭이나 효율 코어로 돌립니다. 손 마우스는 늘
다른 창을 조작하는 동안 뒤에서 돌기 때문에 여기에 걸려서 추론이 10배 가까이 느려집니다
(i7-12700, 30fps 기준 9ms → 90ms). 그래서 `main.py`와 `bench.py`는 시작할 때 이 프로세스의
전원 제한을 끕니다(`hand_mouse/power.py`).

## 튜닝

미리보기 창 세 번째 줄의 `L`(엄지끝~검지끝), `R`(엄지끝~중지끝) 값을 보면서 조정하세요.
값은 손 크기 대비 비율이라 카메라와의 거리에 상관없이 같은 기준으로 판정합니다.

기본값은 실측값으로 정했습니다.

| 상태 | L | R |
|---|---|---|
| 엄지-검지 붙임 | 0.1~0.3 | |
| 손 편 상태 | 0.7~1.2 | 약 1.25 |
| 엄지만 접음 | 약 0.55 | 약 0.75 |

- **좌클릭이 잘 안 됨**: 붙였을 때 L이 0.35보다 큼 → `--press`를 그 값보다 조금 크게
- **엄지를 접었는데 좌클릭이 됨**: 접었을 때 L이 0.35 아래로 내려감 → `--press`를 낮추기
- **우클릭이 잘 안 됨**: 접었을 때 R이 0.9보다 큼 → `--right-press`를 그 값보다 조금 크게
- **손을 폈는데 우클릭이 됨**: 편 상태 R이 0.9 근처까지 내려감 → `--right-press`를 낮추기
- **커서 떨림 / 반응 지연**, 매핑 영역, 스크롤 속도 등: `hand_mouse/config.py`

## 알려진 제한

- 주 모니터만 지원합니다.
- 관리자 권한으로 실행된 창은 조작되지 않습니다(Windows UIPI). 필요하면 이 프로그램도 관리자 권한으로 실행하세요.
- 역광이나 어두운 조명에서는 인식률이 떨어집니다.
- absolute 모드에서는 스크롤이나 주먹 후 손을 다시 펴면 커서가 손 위치로 이동합니다(의도된 동작). 위치를 유지하려면 `--relative`를 쓰세요.

## 테스트

```powershell
uv run pytest      # 가상 손 자세로 제스처 판정 검증 (웹캠 불필요)
```
