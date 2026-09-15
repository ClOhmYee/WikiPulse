-- WP-90: page_baseline 에 view_stddev 를 추가한다.
--
-- 왜 필요한가
--   명세 §3.2 3번은 조회수 급등을 "z >= 3 AND >= 2배" 로 정의한다. 그런데 detector 는
--   여태 **배수만** 봤다 — Baseline 에 view_stddev 가 없어 z 를 못 냈기 때문이다.
--   VIEW_Z_THRESHOLD 상수는 선언만 되고 쓰이지 않았다(spike/replay.py 에 알려진 공백으로
--   적혀 있었다).
--
--   조회수가 편집 뒤에 오는 **보조** 판정일 때는 그래도 됐다. 편집 관문이 이미 후보를
--   좁혀 놓기 때문이다. 그런데 WP-90 에서 기존 문서 경로가 AND -> OR 로 바뀌면서
--   조회수가 **단독 트리거**가 된다 — 이때 배수만 보면 "평소의 2배"만으로 발동한다.
--   WP-86 이 잰 조회수 오탐(대조군 434 문서·일에서 3건)도 z 와 배수를 둘 다
--   걸고 잰 값이라, z 없이는 그 수치를 가져올 수 없다.
--
-- NULL 을 허용하는 이유
--   edit_stddev 와 같다. 그 슬롯에 관측이 하나뿐이면 분산을 못 낸다. 0 으로 채우면
--   detector._z 가 나눗셈을 하려 들거나(stddev<=0 을 z 불가로 처리하므로 실제로는 막히지만)
--   "분산이 0인 문서"와 "표본이 없는 문서"가 구분되지 않는다. 조회수 자체가 결측인
--   슬롯(view_ewma IS NULL)도 여전히 있다.
--
-- 기존 행을 비우지 않는 이유
--   V3 와 달리 키 구조가 안 바뀐다. 새 컬럼은 다음 baseline_sink 적재 때 채워진다.
--   그 전까지는 NULL 이고, detector 는 view_stddev 가 NULL 이면 조회수 z 를 못 내
--   조회수 단독 발동을 하지 않는다 — 안전한 쪽으로 닫힌다.

ALTER TABLE page_baseline ADD COLUMN view_stddev DOUBLE PRECISION;

COMMENT ON COLUMN page_baseline.view_stddev IS
    '조회수 가중 표준편차(모집단). NULL 이면 z 를 못 낸다 — 그 경우 조회수 단독 발동은 '
    '하지 않는다. edit_stddev 와 같은 2-pass 로 산출한다 (spike/ewma.py).';

COMMENT ON COLUMN page_baseline.view_ewma IS
    '조회수 가중 평균. 급등 배수(views / view_ewma)의 분모다. '
    'view_stddev 와 함께 명세 §3.2 3번의 "z >= 3 AND >= 2배" 를 이룬다.';
