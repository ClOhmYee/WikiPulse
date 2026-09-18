# 생성 기준 시각 대기 전수 감사 — 2025-06-12

- 검증 ID: `VAL-2026-09-18-LOCAL-02`
- 실행일: 2026-09-18 KST
- 환경: 로컬 Windows·Python, EC2/원격 DB 미사용
- 대상: 2025-06-12 UTC 편집 후보 중 `creation` 대기로 분류된 윈도우
- 판정: **PASS** — 보존 수량과 원인을 설명했고, 현재 API를 과거 replay에 쓰면 안 되는
  근거를 확보했다
- 전수 결과: [CSV](data/2026-09-18-creation-pending-audit.csv)

## 1. 질문과 수용 기준

앞선 하루 E2E에서 72,632개 편집 윈도우 중 73개가 `creation` 대기로 남았다. 다음을
확인했다.

1. 73개가 누락·중복 없이 다시 계산되는가.
2. 덤프 결측과 문서 삭제·이동·재생성에 따른 미래 시각을 구분할 수 있는가.
3. 같은 월 전체를 읽으면 당일 행의 결측이 해소되는가.
4. 현재 MediaWiki API를 과거 replay 보강에 사용해도 시간·문서 정체성이 보존되는가.

## 2. 입력 증거

| 입력 | 크기·범위 | SHA-256 |
| --- | --- | --- |
| `2026-08.enwiki.2025-06.tsv.bz2` | 515,334,641 B · 5,501,827행 | `1879B9C02091AB2740A2557F66148390801023FE5A24AFBB0C642F8681B1A207` |
| `edit-windows-2025-06-12.jsonl.gz` | 1,369,596 B · 72,632 윈도우·60,412 문서 | `C8DF8418207DA6D9A15B1000C8C63592C0575634773665BAB367ECE7D6C44621` |

편집 윈도우 파일의 집계 수는 앞선 Spark 실측과 일치한다. 생성 기준 시각은 이 감사에서
원본 덤프로 다시 계산했으며 파일 안의 기존 `page_created_at` 값은 사용하지 않았다.

## 3. 방법

1. 6월 12일 덤프 행 185,931개 중 60,412개 후보 제목의 namespace 0 행을 선택했다.
2. 코드와 같은 규칙으로 각 행의 `page_first_edit_timestamp`를 우선하고, 그 행에서 결측일
   때만 `page_creation_timestamp <= event_timestamp`인 값을 사용했다.
3. 문서별 가장 이른 값을 선택하고 `page_created_at < window_end`인지 확인했다.
4. 당일 대기 문서의 historical title과 page ID를 월 전체 5,501,827행에서 다시 추적했다.
5. 남은 제목은 현재 MediaWiki API의 가장 오래된 revision을 단건 조회했다. API 결과는
   진단에만 사용하고 historical 판정 입력에는 넣지 않았다.

## 4. 결과

### 당일 행만 사용

| 원인 | 문서 | 윈도우 |
| --- | ---: | ---: |
| first-edit와 lifecycle 생성 시각 모두 결측 | 49 | 63 |
| 선택된 시각이 윈도우 끝 이상 | 2 | 10 |
| 합계 | **51** | **73** |

49개 결측 문서 중 43개는 당일 행에 `page_is_deleted=true`가 있었고, 42개는 revision이
페이지 삭제로 삭제됐다는 플래그가 있었다. 나머지 6개는 삭제 플래그가 없지만 두 시각이
모두 비어 있었다.

### 같은 월 전체로 보강

월 전체에서 같은 title/page ID를 다시 읽자 6개 문서·13개 윈도우가 복원됐다.

- `2025–26 Cymru Premier`
- `A357 road`
- `Chaz Molder`
- `Daniela Avanzini`
- `Mae Nam`
- `Man's Best Friend (Sabrina Carpenter album)` — 8개 윈도우

| 월 전체 적용 후 원인 | 문서 | 윈도우 |
| --- | ---: | ---: |
| 월 전체에서도 시각 결측 | 34 | 41 |
| 삭제·재생성 후 시각이 과거 편집보다 늦음 | 11 | 19 |
| 합계 | **45** | **60** |

따라서 하루 E2E의 `creation 대기 73`은 당일 행만으로 메타데이터를 만들었을 때의
보수적 결과다. historical metadata를 선택한 월 전체에서 먼저 보강하면 같은 입력의 실제
대기는 60개다.

### 현재 MediaWiki API 진단

월 전체에서도 남은 45개 제목을 2026-09-18 현재 단건 조회했다.

| 결과 | 문서/윈도우 |
| --- | ---: |
| 현재 페이지와 oldest revision 존재 | 44문서 |
| 현재 missing 또는 revision 없음 | 1문서 (`Mehmet Oz/Temp`) |
| API oldest revision이 모든 대상 윈도우보다 이름 | 12문서·15윈도우 |
| API oldest revision도 대상 윈도우보다 늦음 | 32문서·44윈도우 |
| 2025년 덤프와 현재 API page ID 동일 | 14문서 |
| page ID 다름 | 30문서 |

현재 API는 44개를 반환했지만 30개가 당시 page ID와 달랐다. 동일 제목이 삭제 후 다른
페이지로 재생성된 경우가 섞였고, 44개 윈도우는 API의 oldest revision도 사건보다 미래다.
현재 API 결과를 과거 replay에 넣으면 **미래 정보와 동명 재생성 페이지를 과거에 소급**한다.

## 5. 판정

- 73개는 runtime의 유실이 아니라 당일 범위 메타데이터의 결측·불일치 결과다.
- historical replay의 메타데이터는 목표 하루만 읽지 말고 선택한 snapshot/month 전체에서
  먼저 보강해야 한다.
- 월 전체에서도 `page_created_at >= window_end`이거나 결측이면 추정하지 않고
  `creation` 대기로 유지한다.
- LIVE의 신규 문서 보강에는 현재 API를 사용할 수 있지만, historical replay 보강에는
  현재 API를 사용하지 않는다.
- 60개 대기는 72,632개 중 약 0.083%다. 소량이라는 이유로 0이나 `first_seen`으로
  바꾸지 않는다.

## 6. 명세 영향

[요구사항 명세 §10](../requirements-v0.3.md#10-open-issues)의 문서 생성 기준 시각 계약에
다음을 추가했다.

1. historical metadata는 대상 snapshot/month 전체에서 먼저 보강한다.
2. 현재 MediaWiki API는 LIVE 보강 전용이며 과거 replay backfill에 사용하지 않는다.
3. 월 전체에서도 해결되지 않은 값은 `creation` 대기로 보존한다.

제품 판정 수식이나 DB 스키마 변경은 필요하지 않다.

## 7. 한계와 다음 검증

- 현재 API 결과는 2026-09-18 시점 진단값이며 이후 바뀔 수 있다.
- 2025-06 이외 월에서도 같은 결측률인지 아직 확인하지 않았다.
- 다음 우선순위는 실제 사건·대조군 표본의 28일 `other/pageviews` 기준선 품질 검증이다.
