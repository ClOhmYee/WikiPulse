# 펄스맵 시간 탐색과 문서 그래프

2026-09-09 · WP-37, 71, 72, 73

## 구현 범위

프론트·합성 fixture·HTTP 조회 클라이언트와 계약을 구현했다. 서버 조회 구현은 WP-74, 스냅샷 생산·저장은 WP-75다. Spring은 WP-76에서 `/api/v1/issues`와 구조화된 상세 `members`를 제공하도록 변경되었지만, 선택 가능한 스냅샷 목록과 문서 쌍 간선·공통 크기 점수를 포함한 지도 응답은 아직 없다. 실제 백엔드 연동이나 Wikipedia 관계 검증을 완료했다는 뜻이 아니다.

`/pulse`와 `/issues`는 독립 페이지다. 지도/목록 전환은 삭제했다. 이슈 탐색 내부의 카드/리스트 버튼은 검색·필터·정렬·저장을 유지하며 기본은 리스트다. 이슈 주제는 정치·국제·사회·경제·기술·과학·문화·스포츠·환경·기타이며 종목 산업·섹터와 별개다.

## 시간과 선택

- 날짜와 출처를 고르고, 슬라이더로 같은 출처의 전체 기간을 이동한다. 월별 눈금은 실제 시간 차이에 비례한다. 날짜 변경 시 해당 날짜의 마지막 시점, 최초 진입은 최신 LIVE(없으면 최신 replay)를 선택한다. 자동재생·자동 폴링은 없다. 최신 이동은 로드된 시점 목록 기준이다.
- API 시각은 UTC `Z`, 화면 날짜·시각은 KST다. 날짜 목록은 제공된 범위의 빈 날짜를 비활성화한다. 완료된 빈 스냅샷과 아직 저장되지 않은 시점은 다르다.
- HOT은 해당 스냅샷의 서버 급증 판정이다. NEW는 `0 <= snapshotTs - firstDetectedAt < newWindowHours`이며 기본 24시간이다. 두 배지는 함께 표시될 수 있다. 최초 감지 미제공은 NEW로 추정하지 않는다.
- 조회마다 AbortSignal을 전달하고 `useAsyncResource`의 요청 수명 검사로 이전 응답을 버린다. 대기 중 이전 지도·패널을 숨기고 새 응답을 함께 표시한다. 오류 시 재시도하며 mock으로 대체하지 않는다.
- 클러스터 `id`는 상세·저장용, `issueKey`는 시점 간 추적용이다. 같은 issueKey의 선택은 유지한다. 사라진 이슈·문서는 선택을 해제하고 안내한다. 검색·카테고리로 가린 선택은 지표를 다른 이슈로 바꾸지 않는다.

## 그래프와 지표

- 클러스터마다 `nodes`의 문서 하나를 노드 하나로 그린다. 같은 문서가 서로 다른 클러스터에 속하면 각 클러스터 안에 한 번씩 나타난다. 간선은 같은 클러스터의 `sourcePageId`와 `targetPageId`를 연결하며 membership weight에서 만들지 않는다.
- `sizeScore`는 백엔드가 제공할 공통 척도 0~1이다. 반지름은 `6 + 18 * sqrt(sizeScore)`로 고정하고 매 시점 최댓값으로 정규화하지 않는다. 미제공은 작은 점선 노드로 표시한다. 0과 null을 구분한다.
- 원시 `spikeScore`, 이슈 `pulseScore`, 기존 피드의 편집량/기준선 배수는 서로 다르다. 그래프 점수에 배수 기호를 붙이지 않는다. 신규/기존 문서의 원시 점수 산식 차이는 후속 파이프라인에서 보정하고 `scoreVersion`을 제공해야 한다.
- Clickstream은 실선·방향 화살표와 이동량 가중치, Wikidata는 점선 관계로 표시한다. 패널에 근거 명칭과 기준 월/관측 시각을 제공한다. Clickstream 월은 선택 스냅샷 이전 월이어야 하며 순간 이동량으로 설명하지 않는다.
- 클러스터 선택은 확대·요약, 문서 선택은 지표·연결 강조다. 텍스트 이슈 목록과 패널 문서 목록에서도 동일하게 선택할 수 있다. 원문은 별도 링크로 새 탭에서 연다. 확대·축소·드래그·초기화, Enter/Space, 슬라이더 방향키/Home/End를 지원한다.
- React SVG + d3-force 3.0.0을 사용한다. [D3 정적 배치 방식](https://d3js.org/d3-force/simulation#simulation_tick)에 따라 API 객체를 복사해 배치 계산하고 타이머를 정지한 뒤 100 tick만 계산한다. 페이지 수명 동안 issueKey/pageId 위치를 캐시한다. 이미 배치한 노드는 고정하고 새 문서를 추가한다. 클러스터 외곽 크기에 따라 격자 간격을 확보한다. 필터·정렬·점수 변경으로 위치를 재배정하지 않는다.
- 모바일은 클러스터 수에 따라 열 수를 늘려 재배치하고 패널을 아래에 둔다. 36개 클러스터는 5열로 표시한다. 전체 문서·간선은 계속 그리며, 선택·확대·포커스에서 라벨을 자세히 드러낸다. 노드 수를 숨겨 성능을 맞추지 않는다.

## HTTP 계약

기계 판독 정본: [Pulse OpenAPI 3.0.3](../../frontend/docs/pulse-openapi.json). 전체 서비스 명세의 펄스맵 확장이다. 기존 `/events`·`/entities`를 쓰는 다른 프론트 화면의 API를 일괄 변경하지 않는다.

| 요청 | 응답 |
| --- | --- |
| `GET /api/v1/issues/snapshots?from=&to=&source=` | `{data:[{snapshotTs,source,clusterCount}]}`. 출처+시각은 유일. 완료된 0개 스냅샷 포함 |
| `GET /api/v1/issues/map?snapshotTs=&source=` | `{data:{clusters:[...]},meta:{...}}`. 단일 스냅샷 일괄 그래프, 상세 N+1 요청 없음 |

| 객체 | 필드 |
| --- | --- |
| Cluster | `id`, `issueKey`, `label`, nullable `summary`, `category`, nullable `firstDetectedAt`, `hot`, `pulseScore`, `status`, `memberCount`, `nodes`, `edges` |
| Node | `pageId`, `wiki`, `title`, `isSeed`, nullable `editCount/views/editBaseline/viewBaseline/spikeScore/sizeScore`, `completeness`, `windowStart`, `windowEnd` |
| Edge | `id`, `sourcePageId`, `targetPageId`, `kind` (`clickstream/wikidata`), `directed`, `weight`, `evidence` |
| Evidence | `label`, Clickstream의 `month` (`YYYY-MM`) 또는 Wikidata의 `observedAt` (UTC) |
| Meta | 실제 `snapshotTs`, `source` (`live/replay`), 선택적 `dataMode`, `scoreVersion`, `newWindowHours`, 전체 `clusterCount/nodeCount/edgeCount`, `truncated` |

모든 ID는 전송 시 불투명 문자열이다. 숫자 DB 키도 문자열로 직렬화해 BIGINT 정밀도를 지킨다. `nodeCount`는 클러스터별 문서 인스턴스 합계다. `truncated=false`이면 개수는 응답 배열과 정확히 일치한다. true일 때 전체 개수는 반환 개수 이상이며 화면에 일부 반환을 안내한다.

`completeness`는 `complete/pending/unavailable`이다. 수치 null을 0으로 보완하지 않는다. 노드 집계 구간은 시작 < 종료 <= 스냅샷이어야 한다. `DISCARDED`는 반환하지 않는다. 중복 노드·간선, 존재하지 않는 양 끝, 미래 지표·근거, 요청과 다른 시점은 전체 응답 오류로 처리한다. 없는 시점은 404이고 현재 데이터로 대체하지 않는다. 고립 노드는 유효하다.

`issue_cluster`에는 시간 간 추적·최초 감지 정보가, `cluster_member`에는 시점별 문서 지표가 추가로 필요하다. 별도의 문서 쌍 간선과 스냅샷 완성 목록도 생산·저장해야 한다. 이 문서는 필드 요구를 정의하며 DB migration과 점수 보정 알고리즘은 75의 산출물이다. 기존 51은 클러스터링 기준, 61은 탐지 회귀 검증으로 역할을 유지한다.

## Fixture와 검증

2026-09-10에 시연 데이터를 2025-09-01~2026-09-10의 375개 일별 스냅샷으로 확장했다. 슬라이더는 출처가 같은 전체 기간을 탐색한다. 실제 Wikipedia 문서의 합성 지표로 월별 에피소드를 구성하고 `~YYYY-MM-DD`로 과거 일별 리포트를 고정한다. 과거 상세의 종목 연결도 현재 Nasdaq-100 고정 목록 안에서 제공하며 그 시점에 오늘의 주가는 넣지 않는다. 출처·생성 규칙·합성 범위·운영 파이프라인과의 차이는 [MOCK_HISTORY.md](./MOCK_HISTORY.md)를 따른다. 이 ID/점수 규칙은 운영 서버 규칙이 아니다. 빈 결과·미제공 지표 처리는 별도 계약과 테스트로 유지한다.

`npm.cmd run test:contract`는 기존 계약과 새 Pulse OpenAPI 및 모든 스냅샷·부하 fixture를 검증한다. `test:data`는 날짜 경계·관계 무결성·요청 취소·위치 안정성, Playwright는 시간 이동·선택·화면·API 응답 경합·오류 복구를 검사한다. `makeStressMap()`은 20개 클러스터·500개 노드·1,000개 간선이다. 실행 결과는 [검증 기록](../../frontend/docs/VALIDATION.md)에 구분해 기록한다.
