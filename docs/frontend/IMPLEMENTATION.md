# 온보딩 구현 구조

전체 앱 구조와 데이터 연결은 [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_SOURCE.md](./DATA_SOURCE.md)에 정리했다. 이 문서는 온보딩 내부 구현을 보존한다.

## 1. 기술 선택

온보딩은 **React → React Three Fiber → Three.js → WebGL** 계층으로 구현되어 있다.

| 계층 | 사용처 |
| --- | --- |
| React 19.2.8 | 장면 카피, 입력 이벤트, 접근성 DOM, 폴백 |
| React Three Fiber 9.7.0 | `<Canvas>`, `useFrame`, `useThree` 기반 렌더 루프 연결 |
| Three.js 0.185.1 | BufferGeometry, PointsMaterial, LineBasicMaterial, 색상·벡터·카메라 |
| GLSL | 5-octave FBM 우주 구름 배경의 vertex/fragment shader |
| Vite 8.2.2 | 독립 프런트엔드 개발 서버와 프로덕션 빌드 |

낮은 수준의 WebGL API를 직접 사용해 장면을 작성한 것은 아니다. WebGL/WebGL2 사용 가능 여부와 컨텍스트 손실만 브라우저 API로 확인하고, 실제 렌더링은 R3F와 Three.js가 담당한다.

## 2. 파일 구조와 책임

```text
frontend/
├─ index.html                 # 메타데이터, favicon, root
├─ public/
│  └─ wikipulse-icon.png     # 서비스 아이콘
├─ src/
│  ├─ main.jsx               # 폰트·전역 CSS 로드, React mount
│  ├─ app/App.jsx            # 앱 조립과 온보딩 지연 로딩
│  └─ pages/onboarding/
│     ├─ OnboardingPage.jsx  # 장면·입력·DOM 전환·폴백
│     ├─ NodeField.jsx       # WebGL 장면과 모든 노드 상태
│     └─ onboarding.css     # 기본값·온보딩·접근성
└─ DESIGN.md                 # 상세 디자인 규격
```

## 3. 런타임 데이터 흐름

```text
wheel / touch / keyboard
        ↓
window scroll target (0..3)
        ↓ response 2
displayProgress + signedVelocity
        ├─ DOM copy opacity / translate / blur
        ├─ CSS ambient saturation / brightness
        ├─ bottom progress
        └─ NodeField mutable ref
                ├─ scene position/color/scale interpolation
                ├─ edge crossfade and reveal
                ├─ synchronized Track glow
                └─ background star rotation
```

`scrollMotionRef`는 React 상태가 아닌 mutable ref다. 매 프레임 progress와 velocity가 바뀌어도 React 컴포넌트를 다시 렌더하지 않는다. React 상태는 현재 가장 가까운 장면 번호처럼 DOM 갱신에 필요한 값만 보관한다.

## 4. 장면 앵커와 입력 엔진

- `.scene-snap-track` 안에 `100dvh` 높이 앵커 네 개가 있어 전체 스크롤 높이는 최소 `400dvh`다.
- 루트에는 `scroll-snap-type: y mandatory`, 각 앵커에는 `scroll-snap-align: start`가 적용된다.
- 휠 누적 임계값은 `28`, 터치 수직 거리 임계값은 `48px`다.
- 일반 모션에서는 장면 이동 후 약 `1900ms`, reduced motion에서는 `80ms` 동안 추가 이동을 잠근다.
- 휠이 멈춘 뒤 quiet tail을 기다렸다 잠금을 해제해 관성 입력이 다음 장면을 넘기지 않게 한다.
- 사용자가 스크롤바를 직접 움직여도 CSS snap이 가장 가까운 앵커로 정착시킨다.

### Progress와 속도

- 실제 스크롤 위치를 `0..3`의 `targetProgress`로 정규화한다.
- 표시 progress는 지수 응답값 `2`로 목표를 따라간다.
- signed velocity의 상승 응답은 `18`, 하강 응답은 `4.2`다.
- 스크롤과 progress가 안정되면 `3.8`의 추가 지수 감쇠를 적용한다.
- signed velocity의 부호는 배경별의 회전 방향, 절댓값은 회전 속도와 제한적인 의미 노드 drift 강도에 사용한다.

## 5. 노드 소유권과 결정적 생성

의미 노드 수는 화면 크기와 무관하게 350개며, seed `0xc4885e62`로 한 번 결정적으로 생성한다.

| 구분 | 계산 | 현재 개수 | 인덱스 |
| --- | --- | ---: | --- |
| 전체 의미 노드 | 고정 | 350 | `0..349` |
| 클러스터 | `floor(350 × 0.43)` | 150 | `0..149` |
| 이상 신호 | `floor(350 × 0.11)` | 38 | `0..37`, 클러스터의 부분집합 |
| 비클러스터 | `350 - 150` | 200 | `150..349` |
| 가격선 | `floor(200 × 0.7)` | 140 | `150..289` |
| 거래량 | 나머지 | 60 | `290..349` |

장면 네 개에 해당하는 `positions`, `colors`, `scales`, `edges` 배열을 미리 계산한다. 매 프레임 같은 인덱스의 두 인접 장면 값을 보간하므로 점이 교체되거나 순간이동하지 않는다.

## 6. 의미 노드와 간선 렌더링

- 의미 노드는 공유 64px radial canvas texture를 쓰는 하나의 `points` draw로 그린다.
- 화면상 기본 크기는 `6px`, additive blending이며 size attenuation을 끈다.
- Track 글로우는 별도 `points` draw다. 클러스터 인덱스에서 네 개마다 하나를 선택해 38개가 되며, 크기는 `25px`다.
- 간선은 최대 `4200`개를 담는 하나의 동적 line-segment buffer로 관리한다.
- 위치 buffer는 edge 하나당 두 정점, 색 buffer는 정점당 RGBA 네 값이다.
- 전환 중 앞·뒤 장면의 간선을 같은 buffer에 쓰고, RGB는 유지한 채 alpha로만 crossfade한다.

### 장면별 간선

| 장면 | 생성 방식 | 표시 |
| --- | --- | --- |
| 01 | 모든 쌍 중 거리 `< 0.51` | 현재 seed에서 953개, opacity `0.145` |
| 02 | 없음 | 숨김 |
| 03 | 클러스터 노드의 제한된 최근접 연결 | teal, opacity `0.42` |
| 04 | 유지 클러스터 + 가격선 + 매핑 5개 | teal/gold/white, opacity `0.46` |

간선이 너무 많거나 적어 보일 때는 먼저 opacity를 조절한다. 연결 구조 자체가 복잡한 경우에만 거리 threshold나 최근접 제한 수를 변경한다.

## 7. 장면 전환 세부 구현

### 1 → 2

장면 0과 1의 기준 위치는 같다. 중간 progress에서만 각 노드의 seeded phase를 이용해 radial, tangential, depth 방향 burst와 일시적인 zoom/orbit를 더한다. 시작과 끝은 모두 3D 구이므로 수평 이동 없이 퍼졌다 다시 모인다.

### Track 글로우

`GLOW_PULSE_RADIANS_PER_SECOND = 2π / 0.7`을 전 노드가 공유한다. 개별 phase를 주지 않아 38개가 완전히 동기화된다. 글로우 대상은 `sourceIndex = glowIndex × 4`로 고르고, 소유권 배열은 수정하지 않는다.

### 3 → 4

비클러스터 노드의 위치는 장면 시작부터 가격·거래량 목표로 보간한다. 가격 노드의 gold 전환만 별도 `colorProgress`를 사용해 `MATCH_PRICE_COLOR_START = 0.68`까지 지연한다. 가격 간선과 매핑 선도 각각 `revealStart`를 가진다.

## 8. 장면 4 레이아웃

- 데스크톱: 클러스터 중심 x `0`, 그래프 시작 x `2.4`, 그래프 폭 `4.15`.
- 비율상 우측 2/3 안에서 클러스터 약 40%, 여백·브리지 약 10%, 그래프 약 50%를 사용한다.
- 매핑 선은 클러스터 경계 40% 후보를 축 기준으로 정렬하고, 가격선의 8%, 26%, 44%, 62%, 82% 지점을 연결한다.
- 모바일: 클러스터 중심 y `1.55`, 그래프 시작 x `-1.65`, 그래프 폭 `3.3`, 가격 기준 y `-0.95`, 거래량 기준 y `-2.4`.

## 9. 배경 렌더링

### CSS ambient

우측 상단 radial gradient는 `rgb(14 82 108 / 76%)`를 중심으로 한다. 장면별 saturation stop은 `[1, 1.12, 1.16, 0.98]`, brightness stop은 `[1, 0.82, 0.76, 0.68]`다.

### GLSL cloud

전체 캔버스 뒤의 plane에서 5-octave FBM을 계산한다. teal 구름에 제한적인 gold trace를 섞고, 장면 progress에 따라 intensity를 `[0.7, 0.78, 0.88, 0.96]`로 보간한다.

### 별 볼륨

- 700px 이상 950개, 미만 560개.
- 깊이: `z = 5.2 - pow(random, 1.3) × 21`.
- 분산: `spread = 3 + (5.2 - z) × 0.5`.
- gold `#dbb057`, teal `#8acbc1`, white를 거의 같은 비율로 배정한다.
- z가 0보다 작은 그룹과 나머지를 **두 개의 point draw**로 나눠 크기를 각각 `0.06`, `0.054`로 설정한다.
- 기본 y 회전은 데스크톱 `0.04 rad/s`, compact `0.02 rad/s`; scroll velocity가 각각 최대 `0.68`, `0.48 rad/s`를 더한다.
- 꼬리·고스트 copy·comet shader는 사용하지 않는다.

## 10. 카메라와 출력

- perspective camera: position `[0, 0, 5.9]`, FOV `42`, near/far `0.1/100`.
- device pixel ratio: `[1, 2]`.
- renderer: alpha, antialiasing, `high-performance` preference.
- tone mapping: ACES Filmic, exposure `1.15`.
- 카메라는 고정하고 노드 그룹과 배경별을 움직인다.

## 11. 텍스트 정렬

장면 2–4 제목은 첫 장면 워드마크 `W`의 시작 위치에 맞춘다.

- x축: CSS의 아이콘 너비 + 브랜드 gap 변수로 계산한다.
- y축: `heroWordmarkRef`의 실제 `offsetTop`을 stage까지 누적해 `--scene-wordmark-top`에 기록한다.
- `ResizeObserver`, `window.resize`, `document.fonts.ready`에서 다시 계산한다.

폰트 로딩과 반응형 크기 때문에 CSS의 추정값만으로 맞추면 세로축이 어긋난다. 정렬 로직을 단순한 고정 `top` 값으로 되돌리지 않는다.

## 12. 접근성·폴백

- 장면 카피는 DOM이며 현재 설명 영역은 `aria-live="polite"`로 전달한다.
- 장면 레일은 접근 가능한 label과 `aria-current`를 사용한다.
- 키보드 focus에는 2px gold outline과 5px offset을 제공한다.
- WebGL canvas와 ambient는 `aria-hidden="true"`다.
- `canUseWebGL()`이 실패하거나 `webglcontextlost`가 발생하면 `StaticFallback`으로 전환한다.
- reduced motion에서는 가장 가까운 장면 구성을 정적으로 표시한다.

## 13. 성능 원칙과 수정 지점

- 점 하나당 React 컴포넌트를 만들지 않는다.
- typed array와 BufferGeometry를 재사용하고 `needsUpdate`만 설정한다.
- 정적 장면 배열과 텍스처는 `useMemo`, GPU 리소스 해제는 effect cleanup에서 처리한다.
- 장면 수나 노드 소유권을 바꾸면 `SCENES`, 전체 높이, ownership 계산, edge buffer 한도를 함께 검토한다.
- 글로우 주기는 `GLOW_PULSE_RADIANS_PER_SECOND`, 가격 색상 지연은 `MATCH_PRICE_COLOR_START`에서 조절한다.
- 첫 장면 간선의 밀도는 `connectWithinDistance(..., 0.51, ...)`, 가시성은 `edgeOpacity[0]`에서 조절한다.
- 입력 감도는 `WHEEL_STEP_THRESHOLD`, `TOUCH_STEP_THRESHOLD`; 전환 체감 속도는 navigation lock과 progress response를 함께 확인한다.
