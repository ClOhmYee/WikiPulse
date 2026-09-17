-- WikiPulse 리플레이 시연 데이터 — 연속 일별판 (2026-07-17 ~ 2026-09-17)
-- WikiPulse — 실제 위키백과 이벤트 기반, Wikimedia REST API 전체 구간 실측을
-- 매일 스냅샷으로 깐다(§10 "리플레이 시연 구간" 실행분, 사용자 요청: 핵심 사건
-- 3컷이 아니라 파이프라인이 두 달 내내 돌았을 때 나왔을 연속 시계열).
--
-- 실측(2026-09-17, 스크립트로 Wikimedia REST API 전체 구간 일괄 조회):
--   - views: 8개 문서 전부 2026-07-17~09-17 매일 실측(pageviews API, 처리 지연 없음).
--   - edits: 2026-08-31 이후는 API 처리 지연으로 없다(404) — 그 뒤 날짜는
--     edit_count를 NULL로 둔다. 지어내지 않았다.
--   - Haakon VIII는 views 실측이 08-24부터 시작한다(그 전엔 신설 왕세자 문서라
--     API가 집계 대상으로 안 잡았을 가능성 — 확인 안 됨, 추정하지 않고 그 전 날짜는
--     그냥 멤버 자체를 안 넣었다).
--
-- 데모 근사치(이 스크립트에서 계산, 실측 아님):
--   - view_baseline: 이 구간 자체 조회수 시계열의 중앙값(median). 실제 파이프라인의
--     28일 EWMA 기준선(page_baseline)이 아니다.
--   - spike_score = views / view_baseline 단순 배율. pulse_score = 그 배율의 로그
--     스케일 근사. 둘 다 spike/detector.py 실제 공식이 아니다.
--   - status는 전부 CONFIRMED로 고정(하루 단위로 DETECTED->VERIFYING->CONFIRMED
--     전이를 재현하지 않음 — 이 데모의 목적은 신호 연속성이지 상태 전이가 아니다).
--   - cluster_stock 근거문은 §11 실측 수치를 인용한 설명문이며 실제 LLM 호출
--     산출물이 아니다(-68 미착수).
--
-- 적용: docker exec -i wikipulse-postgres psql -U wikipulse -d wikipulse < 이 파일
-- 생성: scratchpad/gen_replay_seed.py(원본 API 수집) + build_sql.py(이 파일 생성)

BEGIN;

DELETE FROM issue_cluster WHERE issue_key LIKE 'demo-%';
DELETE FROM cluster_snapshot WHERE source = 'replay'
  AND snapshot_ts BETWEEN '2026-07-17T00:00:00Z' AND '2026-09-17T23:59:59Z';

INSERT INTO stock (ticker, name, exchange, sector) VALUES
  ('CVX', 'Chevron Corporation', 'NYSE', 'Energy'),
  ('XOM', 'Exxon Mobil Corporation', 'NYSE', 'Energy'),
  ('FRO', 'Frontline plc', 'NYSE', 'Energy')
ON CONFLICT (ticker) DO NOTHING;
INSERT INTO wiki_page (wiki, title) VALUES
  ('enwiki', '2026 Strait of Hormuz crisis'),
  ('enwiki', '2026 Iran war'),
  ('enwiki', 'List of attacks during the 2026 Iran war'),
  ('enwiki', 'Mojtaba Khamenei'),
  ('enwiki', 'Ali Khamenei'),
  ('enwiki', 'Islamic Revolutionary Guard Corps'),
  ('enwiki', 'Haakon VIII'),
  ('enwiki', 'Harald V')
ON CONFLICT (wiki, title) DO NOTHING;

-- 문서별 일별 편집·조회 실측 (편집 신호 흐름 차트 원자료)
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-18', 1),
  ('2026-07-20', 2),
  ('2026-07-21', 3),
  ('2026-07-22', 3),
  ('2026-07-23', 2),
  ('2026-07-25', 6),
  ('2026-07-26', 2),
  ('2026-07-28', 2),
  ('2026-08-01', 2),
  ('2026-08-02', 3),
  ('2026-08-03', 2),
  ('2026-08-06', 6),
  ('2026-08-08', 1),
  ('2026-08-10', 16),
  ('2026-08-12', 4),
  ('2026-08-14', 6),
  ('2026-08-16', 1),
  ('2026-08-18', 6),
  ('2026-08-19', 1),
  ('2026-08-20', 2),
  ('2026-08-21', 1),
  ('2026-08-26', 4),
  ('2026-08-30', 1)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='2026 Strait of Hormuz crisis'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 6310),
  ('2026-07-18', 5823),
  ('2026-07-19', 5051),
  ('2026-07-20', 6024),
  ('2026-07-21', 5611),
  ('2026-07-22', 5066),
  ('2026-07-23', 5098),
  ('2026-07-24', 4367),
  ('2026-07-25', 3974),
  ('2026-07-26', 4483),
  ('2026-07-27', 4620),
  ('2026-07-28', 4512),
  ('2026-07-29', 4346),
  ('2026-07-30', 4535),
  ('2026-07-31', 3816),
  ('2026-08-01', 3879),
  ('2026-08-02', 5740),
  ('2026-08-03', 5164),
  ('2026-08-04', 4994),
  ('2026-08-05', 4446),
  ('2026-08-06', 4586),
  ('2026-08-07', 5435),
  ('2026-08-08', 3661),
  ('2026-08-09', 4047),
  ('2026-08-10', 4587),
  ('2026-08-11', 4233),
  ('2026-08-12', 3778),
  ('2026-08-13', 3715),
  ('2026-08-14', 3675),
  ('2026-08-15', 3922),
  ('2026-08-16', 3742),
  ('2026-08-17', 4577),
  ('2026-08-18', 5214),
  ('2026-08-19', 4463),
  ('2026-08-20', 3959),
  ('2026-08-21', 3289),
  ('2026-08-22', 3069),
  ('2026-08-23', 3013),
  ('2026-08-24', 4331),
  ('2026-08-25', 4004),
  ('2026-08-26', 4087),
  ('2026-08-27', 4293),
  ('2026-08-28', 5077),
  ('2026-08-29', 3226),
  ('2026-08-30', 4112),
  ('2026-08-31', 6184),
  ('2026-09-01', 5133),
  ('2026-09-02', 4506),
  ('2026-09-03', 4232),
  ('2026-09-04', 3918),
  ('2026-09-05', 3104),
  ('2026-09-06', 3420),
  ('2026-09-07', 4430),
  ('2026-09-08', 3901),
  ('2026-09-09', 3985),
  ('2026-09-10', 3788),
  ('2026-09-11', 3882),
  ('2026-09-12', 3397),
  ('2026-09-13', 3560),
  ('2026-09-14', 4023),
  ('2026-09-15', 4527)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='2026 Strait of Hormuz crisis'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-17', 25),
  ('2026-07-18', 44),
  ('2026-07-19', 25),
  ('2026-07-20', 27),
  ('2026-07-21', 16),
  ('2026-07-22', 28),
  ('2026-07-23', 24),
  ('2026-07-24', 39),
  ('2026-07-25', 34),
  ('2026-07-26', 15),
  ('2026-07-27', 24),
  ('2026-07-28', 24),
  ('2026-07-29', 26),
  ('2026-07-30', 31),
  ('2026-07-31', 13),
  ('2026-08-01', 20),
  ('2026-08-02', 33),
  ('2026-08-03', 19),
  ('2026-08-04', 21),
  ('2026-08-05', 13),
  ('2026-08-06', 13),
  ('2026-08-07', 4),
  ('2026-08-08', 18),
  ('2026-08-09', 22),
  ('2026-08-10', 7),
  ('2026-08-11', 13),
  ('2026-08-12', 23),
  ('2026-08-13', 22),
  ('2026-08-14', 10),
  ('2026-08-15', 27),
  ('2026-08-16', 11),
  ('2026-08-17', 24),
  ('2026-08-18', 21),
  ('2026-08-19', 6),
  ('2026-08-20', 14),
  ('2026-08-21', 1),
  ('2026-08-22', 7),
  ('2026-08-23', 20),
  ('2026-08-24', 20),
  ('2026-08-25', 10),
  ('2026-08-26', 9),
  ('2026-08-27', 2),
  ('2026-08-28', 9),
  ('2026-08-29', 7),
  ('2026-08-30', 24)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='2026 Iran war'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 43638),
  ('2026-07-18', 53591),
  ('2026-07-19', 59613),
  ('2026-07-20', 60711),
  ('2026-07-21', 54747),
  ('2026-07-22', 50695),
  ('2026-07-23', 47787),
  ('2026-07-24', 47314),
  ('2026-07-25', 39930),
  ('2026-07-26', 40379),
  ('2026-07-27', 47310),
  ('2026-07-28', 40388),
  ('2026-07-29', 47900),
  ('2026-07-30', 52618),
  ('2026-07-31', 38111),
  ('2026-08-01', 36537),
  ('2026-08-02', 36087),
  ('2026-08-03', 33093),
  ('2026-08-04', 32432),
  ('2026-08-05', 32505),
  ('2026-08-06', 30863),
  ('2026-08-07', 29405),
  ('2026-08-08', 27398),
  ('2026-08-09', 28561),
  ('2026-08-10', 36206),
  ('2026-08-11', 31614),
  ('2026-08-12', 27739),
  ('2026-08-13', 28143),
  ('2026-08-14', 26233),
  ('2026-08-15', 25071),
  ('2026-08-16', 26871),
  ('2026-08-17', 31349),
  ('2026-08-18', 30670),
  ('2026-08-19', 28950),
  ('2026-08-20', 26925),
  ('2026-08-21', 25223),
  ('2026-08-22', 23115),
  ('2026-08-23', 23212),
  ('2026-08-24', 28542),
  ('2026-08-25', 26775),
  ('2026-08-26', 27776),
  ('2026-08-27', 24092),
  ('2026-08-28', 24595),
  ('2026-08-29', 21109),
  ('2026-08-30', 24074),
  ('2026-08-31', 31109),
  ('2026-09-01', 30528),
  ('2026-09-02', 34532),
  ('2026-09-03', 31258),
  ('2026-09-04', 27050),
  ('2026-09-05', 25003),
  ('2026-09-06', 23668),
  ('2026-09-07', 25394),
  ('2026-09-08', 28179),
  ('2026-09-09', 31043),
  ('2026-09-10', 31785),
  ('2026-09-11', 33002),
  ('2026-09-12', 29652),
  ('2026-09-13', 27953),
  ('2026-09-14', 32539),
  ('2026-09-15', 32341)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='2026 Iran war'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-17', 2),
  ('2026-08-19', 1),
  ('2026-08-25', 1),
  ('2026-08-26', 1)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='List of attacks during the 2026 Iran war'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 869),
  ('2026-07-18', 952),
  ('2026-07-19', 1086),
  ('2026-07-20', 1073),
  ('2026-07-21', 986),
  ('2026-07-22', 888),
  ('2026-07-23', 878),
  ('2026-07-24', 859),
  ('2026-07-25', 657),
  ('2026-07-26', 662),
  ('2026-07-27', 691),
  ('2026-07-28', 585),
  ('2026-07-29', 728),
  ('2026-07-30', 737),
  ('2026-07-31', 639),
  ('2026-08-01', 599),
  ('2026-08-02', 556),
  ('2026-08-03', 545),
  ('2026-08-04', 453),
  ('2026-08-05', 480),
  ('2026-08-06', 451),
  ('2026-08-07', 701),
  ('2026-08-08', 530),
  ('2026-08-09', 422),
  ('2026-08-10', 512),
  ('2026-08-11', 485),
  ('2026-08-12', 357),
  ('2026-08-13', 410),
  ('2026-08-14', 346),
  ('2026-08-15', 366),
  ('2026-08-16', 350),
  ('2026-08-17', 510),
  ('2026-08-18', 590),
  ('2026-08-19', 529),
  ('2026-08-20', 587),
  ('2026-08-21', 556),
  ('2026-08-22', 457),
  ('2026-08-23', 447),
  ('2026-08-24', 478),
  ('2026-08-25', 593),
  ('2026-08-26', 568),
  ('2026-08-27', 490),
  ('2026-08-28', 513),
  ('2026-08-29', 497),
  ('2026-08-30', 532),
  ('2026-08-31', 783),
  ('2026-09-01', 769),
  ('2026-09-02', 834),
  ('2026-09-03', 759),
  ('2026-09-04', 762),
  ('2026-09-05', 497),
  ('2026-09-06', 489),
  ('2026-09-07', 521),
  ('2026-09-08', 539),
  ('2026-09-09', 600),
  ('2026-09-10', 617),
  ('2026-09-11', 617),
  ('2026-09-12', 528),
  ('2026-09-13', 439),
  ('2026-09-14', 470),
  ('2026-09-15', 498)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='List of attacks during the 2026 Iran war'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-19', 1),
  ('2026-07-20', 1),
  ('2026-07-23', 1),
  ('2026-07-28', 2),
  ('2026-07-29', 2),
  ('2026-08-05', 1),
  ('2026-08-08', 2),
  ('2026-08-09', 2),
  ('2026-08-22', 2),
  ('2026-08-25', 1),
  ('2026-08-26', 1),
  ('2026-08-28', 1),
  ('2026-08-30', 1)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='Mojtaba Khamenei'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 5377),
  ('2026-07-18', 6525),
  ('2026-07-19', 7748),
  ('2026-07-20', 6342),
  ('2026-07-21', 5878),
  ('2026-07-22', 5528),
  ('2026-07-23', 5263),
  ('2026-07-24', 5428),
  ('2026-07-25', 5379),
  ('2026-07-26', 5289),
  ('2026-07-27', 5285),
  ('2026-07-28', 4809),
  ('2026-07-29', 5456),
  ('2026-07-30', 4869),
  ('2026-07-31', 4189),
  ('2026-08-01', 4047),
  ('2026-08-02', 4226),
  ('2026-08-03', 4181),
  ('2026-08-04', 4722),
  ('2026-08-05', 4620),
  ('2026-08-06', 4905),
  ('2026-08-07', 6904),
  ('2026-08-08', 8566),
  ('2026-08-09', 8370),
  ('2026-08-10', 7793),
  ('2026-08-11', 6665),
  ('2026-08-12', 4747),
  ('2026-08-13', 4049),
  ('2026-08-14', 3575),
  ('2026-08-15', 3623),
  ('2026-08-16', 3991),
  ('2026-08-17', 4053),
  ('2026-08-18', 3950),
  ('2026-08-19', 3772),
  ('2026-08-20', 3690),
  ('2026-08-21', 3743),
  ('2026-08-22', 4111),
  ('2026-08-23', 3679),
  ('2026-08-24', 4252),
  ('2026-08-25', 5922),
  ('2026-08-26', 6044),
  ('2026-08-27', 5092),
  ('2026-08-28', 4591),
  ('2026-08-29', 4107),
  ('2026-08-30', 4642),
  ('2026-08-31', 4905),
  ('2026-09-01', 4220),
  ('2026-09-02', 4296),
  ('2026-09-03', 3904),
  ('2026-09-04', 3463),
  ('2026-09-05', 3199),
  ('2026-09-06', 3643),
  ('2026-09-07', 4117),
  ('2026-09-08', 4840),
  ('2026-09-09', 3844),
  ('2026-09-10', 4801),
  ('2026-09-11', 6547),
  ('2026-09-12', 6924),
  ('2026-09-13', 6117),
  ('2026-09-14', 5248),
  ('2026-09-15', 4283)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='Mojtaba Khamenei'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-17', 1),
  ('2026-07-18', 8),
  ('2026-07-19', 2),
  ('2026-08-01', 2),
  ('2026-08-06', 1),
  ('2026-08-08', 3),
  ('2026-08-09', 1),
  ('2026-08-11', 1),
  ('2026-08-19', 1),
  ('2026-08-21', 1),
  ('2026-08-25', 1),
  ('2026-08-26', 1),
  ('2026-08-27', 2),
  ('2026-08-28', 3)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='Ali Khamenei'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 6503),
  ('2026-07-18', 6552),
  ('2026-07-19', 7067),
  ('2026-07-20', 6252),
  ('2026-07-21', 5990),
  ('2026-07-22', 5832),
  ('2026-07-23', 5372),
  ('2026-07-24', 5754),
  ('2026-07-25', 5238),
  ('2026-07-26', 5425),
  ('2026-07-27', 5595),
  ('2026-07-28', 5248),
  ('2026-07-29', 5314),
  ('2026-07-30', 5058),
  ('2026-07-31', 4445),
  ('2026-08-01', 4322),
  ('2026-08-02', 4907),
  ('2026-08-03', 4653),
  ('2026-08-04', 4573),
  ('2026-08-05', 4548),
  ('2026-08-06', 4652),
  ('2026-08-07', 5004),
  ('2026-08-08', 5623),
  ('2026-08-09', 5913),
  ('2026-08-10', 5603),
  ('2026-08-11', 5421),
  ('2026-08-12', 4912),
  ('2026-08-13', 4302),
  ('2026-08-14', 3925),
  ('2026-08-15', 4081),
  ('2026-08-16', 4193),
  ('2026-08-17', 4278),
  ('2026-08-18', 4354),
  ('2026-08-19', 4086),
  ('2026-08-20', 4213),
  ('2026-08-21', 4342),
  ('2026-08-22', 4123),
  ('2026-08-23', 4248),
  ('2026-08-24', 4698),
  ('2026-08-25', 5033),
  ('2026-08-26', 5282),
  ('2026-08-27', 4817),
  ('2026-08-28', 4708),
  ('2026-08-29', 4180),
  ('2026-08-30', 4232),
  ('2026-08-31', 4997),
  ('2026-09-01', 4786),
  ('2026-09-02', 4721),
  ('2026-09-03', 4586),
  ('2026-09-04', 4084),
  ('2026-09-05', 3841),
  ('2026-09-06', 4172),
  ('2026-09-07', 4036),
  ('2026-09-08', 4330),
  ('2026-09-09', 4029),
  ('2026-09-10', 4463),
  ('2026-09-11', 5761),
  ('2026-09-12', 6393),
  ('2026-09-13', 5855),
  ('2026-09-14', 5258),
  ('2026-09-15', 4961)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='Ali Khamenei'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-28', 3),
  ('2026-08-05', 1),
  ('2026-08-09', 1),
  ('2026-08-10', 1),
  ('2026-08-12', 1),
  ('2026-08-16', 1),
  ('2026-08-19', 1),
  ('2026-08-27', 1)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='Islamic Revolutionary Guard Corps'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 3389),
  ('2026-07-18', 3434),
  ('2026-07-19', 3543),
  ('2026-07-20', 3318),
  ('2026-07-21', 2944),
  ('2026-07-22', 2684),
  ('2026-07-23', 2802),
  ('2026-07-24', 2852),
  ('2026-07-25', 2366),
  ('2026-07-26', 2361),
  ('2026-07-27', 2601),
  ('2026-07-28', 2278),
  ('2026-07-29', 2733),
  ('2026-07-30', 2909),
  ('2026-07-31', 2243),
  ('2026-08-01', 2083),
  ('2026-08-02', 2076),
  ('2026-08-03', 2149),
  ('2026-08-04', 2060),
  ('2026-08-05', 2053),
  ('2026-08-06', 2068),
  ('2026-08-07', 1954),
  ('2026-08-08', 2033),
  ('2026-08-09', 2239),
  ('2026-08-10', 3136),
  ('2026-08-11', 3184),
  ('2026-08-12', 2568),
  ('2026-08-13', 2211),
  ('2026-08-14', 1880),
  ('2026-08-15', 1746),
  ('2026-08-16', 1946),
  ('2026-08-17', 2231),
  ('2026-08-18', 2025),
  ('2026-08-19', 1818),
  ('2026-08-20', 1828),
  ('2026-08-21', 1720),
  ('2026-08-22', 1508),
  ('2026-08-23', 1716),
  ('2026-08-24', 1714),
  ('2026-08-25', 1731),
  ('2026-08-26', 1787),
  ('2026-08-27', 1645),
  ('2026-08-28', 1552),
  ('2026-08-29', 1368),
  ('2026-08-30', 1663),
  ('2026-08-31', 2377),
  ('2026-09-01', 2281),
  ('2026-09-02', 2299),
  ('2026-09-03', 1855),
  ('2026-09-04', 1768),
  ('2026-09-05', 1635),
  ('2026-09-06', 1792),
  ('2026-09-07', 1740),
  ('2026-09-08', 1911),
  ('2026-09-09', 2377),
  ('2026-09-10', 1995),
  ('2026-09-11', 2283),
  ('2026-09-12', 2061),
  ('2026-09-13', 2045),
  ('2026-09-14', 2112),
  ('2026-09-15', 1997)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='Islamic Revolutionary Guard Corps'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-31', 1),
  ('2026-08-02', 1),
  ('2026-08-18', 10),
  ('2026-08-19', 1),
  ('2026-08-24', 4),
  ('2026-08-27', 7),
  ('2026-08-28', 220),
  ('2026-08-29', 41),
  ('2026-08-30', 21)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='Haakon VIII'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-20', 1),
  ('2026-08-28', 292634),
  ('2026-08-29', 157648),
  ('2026-08-30', 80096),
  ('2026-08-31', 59147),
  ('2026-09-01', 65977),
  ('2026-09-02', 33700),
  ('2026-09-03', 15990),
  ('2026-09-04', 17381),
  ('2026-09-05', 13752),
  ('2026-09-06', 15117),
  ('2026-09-07', 12940),
  ('2026-09-08', 7823),
  ('2026-09-09', 43959),
  ('2026-09-10', 31328),
  ('2026-09-11', 27602),
  ('2026-09-12', 16945),
  ('2026-09-13', 9426),
  ('2026-09-14', 6343),
  ('2026-09-15', 4655)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='Haakon VIII'
ON CONFLICT DO NOTHING;
INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, editor_count)
SELECT p.id, d::timestamptz, d::timestamptz + interval '1 day', e, greatest(1, round(e/2.5)::int)
FROM wiki_page p, (VALUES
  ('2026-07-19', 1),
  ('2026-07-24', 2),
  ('2026-07-29', 1),
  ('2026-08-03', 1),
  ('2026-08-18', 16),
  ('2026-08-19', 1),
  ('2026-08-24', 2),
  ('2026-08-26', 5),
  ('2026-08-27', 61),
  ('2026-08-28', 251),
  ('2026-08-29', 27),
  ('2026-08-30', 22)
) AS t(d, e)
WHERE p.wiki='enwiki' AND p.title='Harald V'
ON CONFLICT DO NOTHING;
INSERT INTO page_view_hourly (page_id, ts_hour, views)
SELECT p.id, d::timestamptz, v
FROM wiki_page p, (VALUES
  ('2026-07-17', 1954),
  ('2026-07-18', 2412),
  ('2026-07-19', 2754),
  ('2026-07-20', 2438),
  ('2026-07-21', 1985),
  ('2026-07-22', 1923),
  ('2026-07-23', 1718),
  ('2026-07-24', 1562),
  ('2026-07-25', 1616),
  ('2026-07-26', 1623),
  ('2026-07-27', 1533),
  ('2026-07-28', 1522),
  ('2026-07-29', 1374),
  ('2026-07-30', 1289),
  ('2026-07-31', 1356),
  ('2026-08-01', 1480),
  ('2026-08-02', 1692),
  ('2026-08-03', 1501),
  ('2026-08-04', 1427),
  ('2026-08-05', 1464),
  ('2026-08-06', 1359),
  ('2026-08-07', 1593),
  ('2026-08-08', 1627),
  ('2026-08-09', 1662),
  ('2026-08-10', 1917),
  ('2026-08-11', 1710),
  ('2026-08-12', 1479),
  ('2026-08-13', 1601),
  ('2026-08-14', 1406),
  ('2026-08-15', 1518),
  ('2026-08-16', 1628),
  ('2026-08-17', 2922),
  ('2026-08-18', 5376),
  ('2026-08-19', 2627),
  ('2026-08-20', 1910),
  ('2026-08-21', 1731),
  ('2026-08-22', 1650),
  ('2026-08-23', 6484),
  ('2026-08-24', 16317),
  ('2026-08-25', 7693),
  ('2026-08-26', 4631),
  ('2026-08-27', 81599),
  ('2026-08-28', 563555),
  ('2026-08-29', 197930),
  ('2026-08-30', 90655),
  ('2026-08-31', 63170),
  ('2026-09-01', 50544),
  ('2026-09-02', 30168),
  ('2026-09-03', 18963),
  ('2026-09-04', 18262),
  ('2026-09-05', 15647),
  ('2026-09-06', 16811),
  ('2026-09-07', 14049),
  ('2026-09-08', 10210),
  ('2026-09-09', 56715),
  ('2026-09-10', 37187),
  ('2026-09-11', 43259),
  ('2026-09-12', 24244),
  ('2026-09-13', 11422),
  ('2026-09-14', 7488),
  ('2026-09-15', 5366)
) AS t(d, v)
WHERE p.wiki='enwiki' AND p.title='Harald V'
ON CONFLICT DO NOTHING;

-- 일별 스냅샷 (issue_cluster + cluster_member), 날짜당 cluster_snapshot 1건
-- 2026-07-17 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-17T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c1_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c1_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-17T00:00:00Z', '2026-07-17T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 6310, true, NULL::integer, 6310, 3816.0, 1.65, 0.14),
  ('2026 Iran war', 43638, true, 25, 43638, 26925.0, 1.62, 1.0),
  ('List of attacks during the 2026 Iran war', 869, true, 2, 869, 485.0, 1.79, 0.02),
  ('Mojtaba Khamenei', 5377, false, NULL::integer, 5377, 4049.0, 1.33, 0.12),
  ('Ali Khamenei', 6503, false, 1, 6503, 4278.0, 1.52, 0.15),
  ('Islamic Revolutionary Guard Corps', 3389, false, NULL::integer, 3389, 1792.0, 1.89, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-17T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 7.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c2_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c2_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-17T00:00:00Z', '2026-07-17T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1954, false, NULL::integer, 1954, 1593.0, 1.23, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-17T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-18 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-18T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.5, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c3_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c3_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-18T00:00:00Z', '2026-07-18T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5823, true, 1, 5823, 3816.0, 1.53, 0.11),
  ('2026 Iran war', 53591, true, 44, 53591, 26925.0, 1.99, 1.0),
  ('List of attacks during the 2026 Iran war', 952, true, NULL::integer, 952, 485.0, 1.96, 0.02),
  ('Mojtaba Khamenei', 6525, false, NULL::integer, 6525, 4049.0, 1.61, 0.12),
  ('Ali Khamenei', 6552, false, 8, 6552, 4278.0, 1.53, 0.12),
  ('Islamic Revolutionary Guard Corps', 3434, false, NULL::integer, 3434, 1792.0, 1.92, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-18T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 8.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c4_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c4_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-18T00:00:00Z', '2026-07-18T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 2412, false, NULL::integer, 2412, 1593.0, 1.51, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-18T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-19 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-19T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 10.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c5_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c5_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-19T00:00:00Z', '2026-07-19T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5051, true, NULL::integer, 5051, 3816.0, 1.32, 0.08),
  ('2026 Iran war', 59613, true, 25, 59613, 26925.0, 2.21, 1.0),
  ('List of attacks during the 2026 Iran war', 1086, true, NULL::integer, 1086, 485.0, 2.24, 0.02),
  ('Mojtaba Khamenei', 7748, false, 1, 7748, 4049.0, 1.91, 0.13),
  ('Ali Khamenei', 7067, false, 2, 7067, 4278.0, 1.65, 0.12),
  ('Islamic Revolutionary Guard Corps', 3543, false, NULL::integer, 3543, 1792.0, 1.98, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-19T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 8.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c6_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c6_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-19T00:00:00Z', '2026-07-19T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 2754, false, 1, 2754, 1593.0, 1.73, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-19T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-20 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-20T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 10.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c7_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c7_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-20T00:00:00Z', '2026-07-20T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 6024, true, 2, 6024, 3816.0, 1.58, 0.1),
  ('2026 Iran war', 60711, true, 27, 60711, 26925.0, 2.25, 1.0),
  ('List of attacks during the 2026 Iran war', 1073, true, NULL::integer, 1073, 485.0, 2.21, 0.02),
  ('Mojtaba Khamenei', 6342, false, 1, 6342, 4049.0, 1.57, 0.1),
  ('Ali Khamenei', 6252, false, NULL::integer, 6252, 4278.0, 1.46, 0.1),
  ('Islamic Revolutionary Guard Corps', 3318, false, NULL::integer, 3318, 1792.0, 1.85, 0.05)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-20T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 8.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c8_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c8_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-20T00:00:00Z', '2026-07-20T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 1, true, NULL::integer, 1, 9426.0, 0.0, 0.0),
  ('Harald V', 2438, false, NULL::integer, 2438, 1593.0, 1.53, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-20T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-21 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-21T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.6, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c9_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c9_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-21T00:00:00Z', '2026-07-21T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5611, true, 3, 5611, 3816.0, 1.47, 0.1),
  ('2026 Iran war', 54747, true, 16, 54747, 26925.0, 2.03, 1.0),
  ('List of attacks during the 2026 Iran war', 986, true, NULL::integer, 986, 485.0, 2.03, 0.02),
  ('Mojtaba Khamenei', 5878, false, NULL::integer, 5878, 4049.0, 1.45, 0.11),
  ('Ali Khamenei', 5990, false, NULL::integer, 5990, 4278.0, 1.4, 0.11),
  ('Islamic Revolutionary Guard Corps', 2944, false, NULL::integer, 2944, 1792.0, 1.64, 0.05)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-21T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 7.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c10_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c10_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-21T00:00:00Z', '2026-07-21T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1985, false, NULL::integer, 1985, 1593.0, 1.25, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-21T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-22 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-22T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c11_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c11_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-22T00:00:00Z', '2026-07-22T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5066, true, 3, 5066, 3816.0, 1.33, 0.1),
  ('2026 Iran war', 50695, true, 28, 50695, 26925.0, 1.88, 1.0),
  ('List of attacks during the 2026 Iran war', 888, true, NULL::integer, 888, 485.0, 1.83, 0.02),
  ('Mojtaba Khamenei', 5528, false, NULL::integer, 5528, 4049.0, 1.37, 0.11),
  ('Ali Khamenei', 5832, false, NULL::integer, 5832, 4278.0, 1.36, 0.12),
  ('Islamic Revolutionary Guard Corps', 2684, false, NULL::integer, 2684, 1792.0, 1.5, 0.05)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-22T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.9, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c12_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c12_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-22T00:00:00Z', '2026-07-22T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1923, false, NULL::integer, 1923, 1593.0, 1.21, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-22T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-23 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-23T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c13_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c13_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-23T00:00:00Z', '2026-07-23T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5098, true, 2, 5098, 3816.0, 1.34, 0.11),
  ('2026 Iran war', 47787, true, 24, 47787, 26925.0, 1.77, 1.0),
  ('List of attacks during the 2026 Iran war', 878, true, NULL::integer, 878, 485.0, 1.81, 0.02),
  ('Mojtaba Khamenei', 5263, false, 1, 5263, 4049.0, 1.3, 0.11),
  ('Ali Khamenei', 5372, false, NULL::integer, 5372, 4278.0, 1.26, 0.11),
  ('Islamic Revolutionary Guard Corps', 2802, false, NULL::integer, 2802, 1792.0, 1.56, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-23T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.4, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c14_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c14_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-23T00:00:00Z', '2026-07-23T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1718, false, NULL::integer, 1718, 1593.0, 1.08, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-23T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-24 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-24T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.8, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c15_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c15_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-24T00:00:00Z', '2026-07-24T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4367, true, NULL::integer, 4367, 3816.0, 1.14, 0.09),
  ('2026 Iran war', 47314, true, 39, 47314, 26925.0, 1.76, 1.0),
  ('List of attacks during the 2026 Iran war', 859, true, NULL::integer, 859, 485.0, 1.77, 0.02),
  ('Mojtaba Khamenei', 5428, false, NULL::integer, 5428, 4049.0, 1.34, 0.11),
  ('Ali Khamenei', 5754, false, NULL::integer, 5754, 4278.0, 1.35, 0.12),
  ('Islamic Revolutionary Guard Corps', 2852, false, NULL::integer, 2852, 1792.0, 1.59, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-24T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.9, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c16_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c16_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-24T00:00:00Z', '2026-07-24T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1562, false, 2, 1562, 1593.0, 0.98, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-24T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-25 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-25T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c17_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c17_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-25T00:00:00Z', '2026-07-25T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3974, true, 6, 3974, 3816.0, 1.04, 0.1),
  ('2026 Iran war', 39930, true, 34, 39930, 26925.0, 1.48, 1.0),
  ('List of attacks during the 2026 Iran war', 657, true, NULL::integer, 657, 485.0, 1.35, 0.02),
  ('Mojtaba Khamenei', 5379, false, NULL::integer, 5379, 4049.0, 1.33, 0.13),
  ('Ali Khamenei', 5238, false, NULL::integer, 5238, 4278.0, 1.22, 0.13),
  ('Islamic Revolutionary Guard Corps', 2366, false, NULL::integer, 2366, 1792.0, 1.32, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-25T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c18_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c18_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-25T00:00:00Z', '2026-07-25T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1616, false, NULL::integer, 1616, 1593.0, 1.01, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-25T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-26 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-26T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c19_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c19_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-26T00:00:00Z', '2026-07-26T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4483, true, 2, 4483, 3816.0, 1.17, 0.11),
  ('2026 Iran war', 40379, true, 15, 40379, 26925.0, 1.5, 1.0),
  ('List of attacks during the 2026 Iran war', 662, true, NULL::integer, 662, 485.0, 1.36, 0.02),
  ('Mojtaba Khamenei', 5289, false, NULL::integer, 5289, 4049.0, 1.31, 0.13),
  ('Ali Khamenei', 5425, false, NULL::integer, 5425, 4278.0, 1.27, 0.13),
  ('Islamic Revolutionary Guard Corps', 2361, false, NULL::integer, 2361, 1792.0, 1.32, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-26T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c20_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c20_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-26T00:00:00Z', '2026-07-26T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1623, false, NULL::integer, 1623, 1593.0, 1.02, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-26T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-27 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-27T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.8, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c21_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c21_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-27T00:00:00Z', '2026-07-27T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4620, true, NULL::integer, 4620, 3816.0, 1.21, 0.1),
  ('2026 Iran war', 47310, true, 24, 47310, 26925.0, 1.76, 1.0),
  ('List of attacks during the 2026 Iran war', 691, true, NULL::integer, 691, 485.0, 1.42, 0.01),
  ('Mojtaba Khamenei', 5285, false, NULL::integer, 5285, 4049.0, 1.31, 0.11),
  ('Ali Khamenei', 5595, false, NULL::integer, 5595, 4278.0, 1.31, 0.12),
  ('Islamic Revolutionary Guard Corps', 2601, false, NULL::integer, 2601, 1792.0, 1.45, 0.05)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-27T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c22_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c22_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-27T00:00:00Z', '2026-07-27T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1533, false, NULL::integer, 1533, 1593.0, 0.96, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-27T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-28 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-28T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c23_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c23_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-28T00:00:00Z', '2026-07-28T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4512, true, 2, 4512, 3816.0, 1.18, 0.11),
  ('2026 Iran war', 40388, true, 24, 40388, 26925.0, 1.5, 1.0),
  ('List of attacks during the 2026 Iran war', 585, true, NULL::integer, 585, 485.0, 1.21, 0.01),
  ('Mojtaba Khamenei', 4809, false, 2, 4809, 4049.0, 1.19, 0.12),
  ('Ali Khamenei', 5248, false, NULL::integer, 5248, 4278.0, 1.23, 0.13),
  ('Islamic Revolutionary Guard Corps', 2278, false, 3, 2278, 1792.0, 1.27, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-28T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c24_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c24_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-28T00:00:00Z', '2026-07-28T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1522, false, NULL::integer, 1522, 1593.0, 0.96, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-28T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-29 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-29T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c25_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c25_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-29T00:00:00Z', '2026-07-29T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4346, true, NULL::integer, 4346, 3816.0, 1.14, 0.09),
  ('2026 Iran war', 47900, true, 26, 47900, 26925.0, 1.78, 1.0),
  ('List of attacks during the 2026 Iran war', 728, true, NULL::integer, 728, 485.0, 1.5, 0.02),
  ('Mojtaba Khamenei', 5456, false, 2, 5456, 4049.0, 1.35, 0.11),
  ('Ali Khamenei', 5314, false, NULL::integer, 5314, 4278.0, 1.24, 0.11),
  ('Islamic Revolutionary Guard Corps', 2733, false, NULL::integer, 2733, 1792.0, 1.53, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-29T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.4, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c26_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c26_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-29T00:00:00Z', '2026-07-29T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1374, false, 1, 1374, 1593.0, 0.86, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-29T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-30 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-30T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.4, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c27_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c27_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-30T00:00:00Z', '2026-07-30T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4535, true, NULL::integer, 4535, 3816.0, 1.19, 0.09),
  ('2026 Iran war', 52618, true, 31, 52618, 26925.0, 1.95, 1.0),
  ('List of attacks during the 2026 Iran war', 737, true, NULL::integer, 737, 485.0, 1.52, 0.01),
  ('Mojtaba Khamenei', 4869, false, NULL::integer, 4869, 4049.0, 1.2, 0.09),
  ('Ali Khamenei', 5058, false, NULL::integer, 5058, 4278.0, 1.18, 0.1),
  ('Islamic Revolutionary Guard Corps', 2909, false, NULL::integer, 2909, 1792.0, 1.62, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-30T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c28_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c28_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-30T00:00:00Z', '2026-07-30T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1289, false, NULL::integer, 1289, 1593.0, 0.81, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-30T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-07-31 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-31T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c29_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c29_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-31T00:00:00Z', '2026-07-31T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3816, true, NULL::integer, 3816, 3816.0, 1.0, 0.1),
  ('2026 Iran war', 38111, true, 13, 38111, 26925.0, 1.42, 1.0),
  ('List of attacks during the 2026 Iran war', 639, true, NULL::integer, 639, 485.0, 1.32, 0.02),
  ('Mojtaba Khamenei', 4189, false, NULL::integer, 4189, 4049.0, 1.03, 0.11),
  ('Ali Khamenei', 4445, false, NULL::integer, 4445, 4278.0, 1.04, 0.12),
  ('Islamic Revolutionary Guard Corps', 2243, false, NULL::integer, 2243, 1792.0, 1.25, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-07-31T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c30_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c30_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-07-31T00:00:00Z', '2026-07-31T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1356, false, NULL::integer, 1356, 1593.0, 0.85, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-07-31T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-01 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-01T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.5, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c31_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c31_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-01T00:00:00Z', '2026-08-01T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3879, true, 2, 3879, 3816.0, 1.02, 0.11),
  ('2026 Iran war', 36537, true, 20, 36537, 26925.0, 1.36, 1.0),
  ('List of attacks during the 2026 Iran war', 599, true, NULL::integer, 599, 485.0, 1.24, 0.02),
  ('Mojtaba Khamenei', 4047, false, NULL::integer, 4047, 4049.0, 1.0, 0.11),
  ('Ali Khamenei', 4322, false, 2, 4322, 4278.0, 1.01, 0.12),
  ('Islamic Revolutionary Guard Corps', 2083, false, NULL::integer, 2083, 1792.0, 1.16, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-01T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c32_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c32_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-01T00:00:00Z', '2026-08-01T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1480, false, NULL::integer, 1480, 1593.0, 0.93, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-01T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-02 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-02T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c33_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c33_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-02T00:00:00Z', '2026-08-02T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5740, true, 3, 5740, 3816.0, 1.5, 0.16),
  ('2026 Iran war', 36087, true, 33, 36087, 26925.0, 1.34, 1.0),
  ('List of attacks during the 2026 Iran war', 556, true, NULL::integer, 556, 485.0, 1.15, 0.02),
  ('Mojtaba Khamenei', 4226, false, NULL::integer, 4226, 4049.0, 1.04, 0.12),
  ('Ali Khamenei', 4907, false, NULL::integer, 4907, 4278.0, 1.15, 0.14),
  ('Islamic Revolutionary Guard Corps', 2076, false, NULL::integer, 2076, 1792.0, 1.16, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-02T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c34_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c34_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-02T00:00:00Z', '2026-08-02T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1692, false, NULL::integer, 1692, 1593.0, 1.06, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-02T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-03 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-03T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.4, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c35_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c35_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-03T00:00:00Z', '2026-08-03T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5164, true, 2, 5164, 3816.0, 1.35, 0.16),
  ('2026 Iran war', 33093, true, 19, 33093, 26925.0, 1.23, 1.0),
  ('List of attacks during the 2026 Iran war', 545, true, NULL::integer, 545, 485.0, 1.12, 0.02),
  ('Mojtaba Khamenei', 4181, false, NULL::integer, 4181, 4049.0, 1.03, 0.13),
  ('Ali Khamenei', 4653, false, NULL::integer, 4653, 4278.0, 1.09, 0.14),
  ('Islamic Revolutionary Guard Corps', 2149, false, NULL::integer, 2149, 1792.0, 1.2, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-03T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c36_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c36_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-03T00:00:00Z', '2026-08-03T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1501, false, 1, 1501, 1593.0, 0.94, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-03T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-04 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-04T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.3, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c37_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c37_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-04T00:00:00Z', '2026-08-04T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4994, true, NULL::integer, 4994, 3816.0, 1.31, 0.15),
  ('2026 Iran war', 32432, true, 21, 32432, 26925.0, 1.2, 1.0),
  ('List of attacks during the 2026 Iran war', 453, true, NULL::integer, 453, 485.0, 0.93, 0.01),
  ('Mojtaba Khamenei', 4722, false, NULL::integer, 4722, 4049.0, 1.17, 0.15),
  ('Ali Khamenei', 4573, false, NULL::integer, 4573, 4278.0, 1.07, 0.14),
  ('Islamic Revolutionary Guard Corps', 2060, false, NULL::integer, 2060, 1792.0, 1.15, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-04T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.6, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c38_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c38_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-04T00:00:00Z', '2026-08-04T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1427, false, NULL::integer, 1427, 1593.0, 0.9, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-04T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-05 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-05T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c39_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c39_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-05T00:00:00Z', '2026-08-05T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4446, true, NULL::integer, 4446, 3816.0, 1.17, 0.14),
  ('2026 Iran war', 32505, true, 13, 32505, 26925.0, 1.21, 1.0),
  ('List of attacks during the 2026 Iran war', 480, true, NULL::integer, 480, 485.0, 0.99, 0.01),
  ('Mojtaba Khamenei', 4620, false, 1, 4620, 4049.0, 1.14, 0.14),
  ('Ali Khamenei', 4548, false, NULL::integer, 4548, 4278.0, 1.06, 0.14),
  ('Islamic Revolutionary Guard Corps', 2053, false, 1, 2053, 1792.0, 1.15, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-05T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c40_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c40_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-05T00:00:00Z', '2026-08-05T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1464, false, NULL::integer, 1464, 1593.0, 0.92, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-05T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-06 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-06T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c41_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c41_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-06T00:00:00Z', '2026-08-06T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4586, true, 6, 4586, 3816.0, 1.2, 0.15),
  ('2026 Iran war', 30863, true, 13, 30863, 26925.0, 1.15, 1.0),
  ('List of attacks during the 2026 Iran war', 451, true, NULL::integer, 451, 485.0, 0.93, 0.01),
  ('Mojtaba Khamenei', 4905, false, NULL::integer, 4905, 4049.0, 1.21, 0.16),
  ('Ali Khamenei', 4652, false, 1, 4652, 4278.0, 1.09, 0.15),
  ('Islamic Revolutionary Guard Corps', 2068, false, NULL::integer, 2068, 1792.0, 1.15, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-06T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c42_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c42_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-06T00:00:00Z', '2026-08-06T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1359, false, NULL::integer, 1359, 1593.0, 0.85, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-06T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-07 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-07T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c43_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c43_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-07T00:00:00Z', '2026-08-07T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5435, true, NULL::integer, 5435, 3816.0, 1.42, 0.18),
  ('2026 Iran war', 29405, true, 4, 29405, 26925.0, 1.09, 1.0),
  ('List of attacks during the 2026 Iran war', 701, true, NULL::integer, 701, 485.0, 1.45, 0.02),
  ('Mojtaba Khamenei', 6904, false, NULL::integer, 6904, 4049.0, 1.71, 0.23),
  ('Ali Khamenei', 5004, false, NULL::integer, 5004, 4278.0, 1.17, 0.17),
  ('Islamic Revolutionary Guard Corps', 1954, false, NULL::integer, 1954, 1792.0, 1.09, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-07T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c44_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c44_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-07T00:00:00Z', '2026-08-07T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1593, false, NULL::integer, 1593, 1593.0, 1.0, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-07T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-08 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-08T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c45_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c45_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-08T00:00:00Z', '2026-08-08T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3661, true, 1, 3661, 3816.0, 0.96, 0.13),
  ('2026 Iran war', 27398, true, 18, 27398, 26925.0, 1.02, 1.0),
  ('List of attacks during the 2026 Iran war', 530, true, NULL::integer, 530, 485.0, 1.09, 0.02),
  ('Mojtaba Khamenei', 8566, false, 2, 8566, 4049.0, 2.12, 0.31),
  ('Ali Khamenei', 5623, false, 3, 5623, 4278.0, 1.31, 0.21),
  ('Islamic Revolutionary Guard Corps', 2033, false, NULL::integer, 2033, 1792.0, 1.13, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-08T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c46_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c46_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-08T00:00:00Z', '2026-08-08T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1627, false, NULL::integer, 1627, 1593.0, 1.02, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-08T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-09 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-09T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c47_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c47_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-09T00:00:00Z', '2026-08-09T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4047, true, NULL::integer, 4047, 3816.0, 1.06, 0.14),
  ('2026 Iran war', 28561, true, 22, 28561, 26925.0, 1.06, 1.0),
  ('List of attacks during the 2026 Iran war', 422, true, NULL::integer, 422, 485.0, 0.87, 0.01),
  ('Mojtaba Khamenei', 8370, false, 2, 8370, 4049.0, 2.07, 0.29),
  ('Ali Khamenei', 5913, false, 1, 5913, 4278.0, 1.38, 0.21),
  ('Islamic Revolutionary Guard Corps', 2239, false, 1, 2239, 1792.0, 1.25, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-09T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c48_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c48_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-09T00:00:00Z', '2026-08-09T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1662, false, NULL::integer, 1662, 1593.0, 1.04, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-09T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-10 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-10T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 9.3, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c49_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c49_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-10T00:00:00Z', '2026-08-10T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4587, true, 16, 4587, 3816.0, 1.2, 0.13),
  ('2026 Iran war', 36206, true, 7, 36206, 26925.0, 1.34, 1.0),
  ('List of attacks during the 2026 Iran war', 512, true, NULL::integer, 512, 485.0, 1.06, 0.01),
  ('Mojtaba Khamenei', 7793, false, NULL::integer, 7793, 4049.0, 1.92, 0.22),
  ('Ali Khamenei', 5603, false, NULL::integer, 5603, 4278.0, 1.31, 0.15),
  ('Islamic Revolutionary Guard Corps', 3136, false, 1, 3136, 1792.0, 1.75, 0.09)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-10T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c50_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c50_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-10T00:00:00Z', '2026-08-10T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1917, false, NULL::integer, 1917, 1593.0, 1.2, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-10T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-11 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-11T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c51_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c51_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-11T00:00:00Z', '2026-08-11T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4233, true, NULL::integer, 4233, 3816.0, 1.11, 0.13),
  ('2026 Iran war', 31614, true, 13, 31614, 26925.0, 1.17, 1.0),
  ('List of attacks during the 2026 Iran war', 485, true, NULL::integer, 485, 485.0, 1.0, 0.02),
  ('Mojtaba Khamenei', 6665, false, NULL::integer, 6665, 4049.0, 1.65, 0.21),
  ('Ali Khamenei', 5421, false, 1, 5421, 4278.0, 1.27, 0.17),
  ('Islamic Revolutionary Guard Corps', 3184, false, NULL::integer, 3184, 1792.0, 1.78, 0.1)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-11T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c52_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c52_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-11T00:00:00Z', '2026-08-11T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1710, false, NULL::integer, 1710, 1593.0, 1.07, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-11T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-12 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-12T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c53_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c53_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-12T00:00:00Z', '2026-08-12T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3778, true, 4, 3778, 3816.0, 0.99, 0.14),
  ('2026 Iran war', 27739, true, 23, 27739, 26925.0, 1.03, 1.0),
  ('List of attacks during the 2026 Iran war', 357, true, NULL::integer, 357, 485.0, 0.74, 0.01),
  ('Mojtaba Khamenei', 4747, false, NULL::integer, 4747, 4049.0, 1.17, 0.17),
  ('Ali Khamenei', 4912, false, NULL::integer, 4912, 4278.0, 1.15, 0.18),
  ('Islamic Revolutionary Guard Corps', 2568, false, 1, 2568, 1792.0, 1.43, 0.09)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-12T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c54_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c54_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-12T00:00:00Z', '2026-08-12T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1479, false, NULL::integer, 1479, 1593.0, 0.93, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-12T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-13 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-13T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c55_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c55_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-13T00:00:00Z', '2026-08-13T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3715, true, NULL::integer, 3715, 3816.0, 0.97, 0.13),
  ('2026 Iran war', 28143, true, 22, 28143, 26925.0, 1.05, 1.0),
  ('List of attacks during the 2026 Iran war', 410, true, NULL::integer, 410, 485.0, 0.85, 0.01),
  ('Mojtaba Khamenei', 4049, false, NULL::integer, 4049, 4049.0, 1.0, 0.14),
  ('Ali Khamenei', 4302, false, NULL::integer, 4302, 4278.0, 1.01, 0.15),
  ('Islamic Revolutionary Guard Corps', 2211, false, NULL::integer, 2211, 1792.0, 1.23, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-13T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c56_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c56_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-13T00:00:00Z', '2026-08-13T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1601, false, NULL::integer, 1601, 1593.0, 1.01, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-13T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-14 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-14T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c57_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c57_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-14T00:00:00Z', '2026-08-14T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3675, true, 6, 3675, 3816.0, 0.96, 0.14),
  ('2026 Iran war', 26233, true, 10, 26233, 26925.0, 0.97, 1.0),
  ('List of attacks during the 2026 Iran war', 346, true, NULL::integer, 346, 485.0, 0.71, 0.01),
  ('Mojtaba Khamenei', 3575, false, NULL::integer, 3575, 4049.0, 0.88, 0.14),
  ('Ali Khamenei', 3925, false, NULL::integer, 3925, 4278.0, 0.92, 0.15),
  ('Islamic Revolutionary Guard Corps', 1880, false, NULL::integer, 1880, 1792.0, 1.05, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-14T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.5, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c58_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c58_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-14T00:00:00Z', '2026-08-14T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1406, false, NULL::integer, 1406, 1593.0, 0.88, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-14T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-15 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-15T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c59_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c59_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-15T00:00:00Z', '2026-08-15T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3922, true, NULL::integer, 3922, 3816.0, 1.03, 0.16),
  ('2026 Iran war', 25071, true, 27, 25071, 26925.0, 0.93, 1.0),
  ('List of attacks during the 2026 Iran war', 366, true, NULL::integer, 366, 485.0, 0.75, 0.01),
  ('Mojtaba Khamenei', 3623, false, NULL::integer, 3623, 4049.0, 0.89, 0.14),
  ('Ali Khamenei', 4081, false, NULL::integer, 4081, 4278.0, 0.95, 0.16),
  ('Islamic Revolutionary Guard Corps', 1746, false, NULL::integer, 1746, 1792.0, 0.97, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-15T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 5.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c60_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c60_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-15T00:00:00Z', '2026-08-15T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1518, false, NULL::integer, 1518, 1593.0, 0.95, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-15T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-16 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-16T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.4, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c61_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c61_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-16T00:00:00Z', '2026-08-16T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3742, true, 1, 3742, 3816.0, 0.98, 0.14),
  ('2026 Iran war', 26871, true, 11, 26871, 26925.0, 1.0, 1.0),
  ('List of attacks during the 2026 Iran war', 350, true, NULL::integer, 350, 485.0, 0.72, 0.01),
  ('Mojtaba Khamenei', 3991, false, NULL::integer, 3991, 4049.0, 0.99, 0.15),
  ('Ali Khamenei', 4193, false, NULL::integer, 4193, 4278.0, 0.98, 0.16),
  ('Islamic Revolutionary Guard Corps', 1946, false, 1, 1946, 1792.0, 1.09, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-16T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c62_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c62_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-16T00:00:00Z', '2026-08-16T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1628, false, NULL::integer, 1628, 1593.0, 1.02, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-16T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-17 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-17T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c63_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c63_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-17T00:00:00Z', '2026-08-17T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4577, true, NULL::integer, 4577, 3816.0, 1.2, 0.15),
  ('2026 Iran war', 31349, true, 24, 31349, 26925.0, 1.16, 1.0),
  ('List of attacks during the 2026 Iran war', 510, true, NULL::integer, 510, 485.0, 1.05, 0.02),
  ('Mojtaba Khamenei', 4053, false, NULL::integer, 4053, 4049.0, 1.0, 0.13),
  ('Ali Khamenei', 4278, false, NULL::integer, 4278, 4278.0, 1.0, 0.14),
  ('Islamic Revolutionary Guard Corps', 2231, false, NULL::integer, 2231, 1792.0, 1.24, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-17T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 9.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c64_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c64_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-17T00:00:00Z', '2026-08-17T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 2922, false, NULL::integer, 2922, 1593.0, 1.83, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-17T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-18 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-18T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.5, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c65_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c65_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-18T00:00:00Z', '2026-08-18T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5214, true, 6, 5214, 3816.0, 1.37, 0.17),
  ('2026 Iran war', 30670, true, 21, 30670, 26925.0, 1.14, 1.0),
  ('List of attacks during the 2026 Iran war', 590, true, NULL::integer, 590, 485.0, 1.22, 0.02),
  ('Mojtaba Khamenei', 3950, false, NULL::integer, 3950, 4049.0, 0.98, 0.13),
  ('Ali Khamenei', 4354, false, NULL::integer, 4354, 4278.0, 1.02, 0.14),
  ('Islamic Revolutionary Guard Corps', 2025, false, NULL::integer, 2025, 1792.0, 1.13, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-18T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 12.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c66_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c66_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-18T00:00:00Z', '2026-08-18T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 5376, false, 16, 5376, 1593.0, 3.37, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-18T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-19 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-19T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c67_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c67_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-19T00:00:00Z', '2026-08-19T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4463, true, 1, 4463, 3816.0, 1.17, 0.15),
  ('2026 Iran war', 28950, true, 6, 28950, 26925.0, 1.08, 1.0),
  ('List of attacks during the 2026 Iran war', 529, true, 1, 529, 485.0, 1.09, 0.02),
  ('Mojtaba Khamenei', 3772, false, NULL::integer, 3772, 4049.0, 0.93, 0.13),
  ('Ali Khamenei', 4086, false, 1, 4086, 4278.0, 0.96, 0.14),
  ('Islamic Revolutionary Guard Corps', 1818, false, 1, 1818, 1792.0, 1.01, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-19T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 8.5, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c68_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c68_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-19T00:00:00Z', '2026-08-19T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 2627, false, 1, 2627, 1593.0, 1.65, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-19T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-20 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-20T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c69_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c69_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-20T00:00:00Z', '2026-08-20T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3959, true, 2, 3959, 3816.0, 1.04, 0.15),
  ('2026 Iran war', 26925, true, 14, 26925, 26925.0, 1.0, 1.0),
  ('List of attacks during the 2026 Iran war', 587, true, NULL::integer, 587, 485.0, 1.21, 0.02),
  ('Mojtaba Khamenei', 3690, false, NULL::integer, 3690, 4049.0, 0.91, 0.14),
  ('Ali Khamenei', 4213, false, NULL::integer, 4213, 4278.0, 0.98, 0.16),
  ('Islamic Revolutionary Guard Corps', 1828, false, NULL::integer, 1828, 1792.0, 1.02, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-20T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c70_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c70_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-20T00:00:00Z', '2026-08-20T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1910, false, NULL::integer, 1910, 1593.0, 1.2, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-20T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-21 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-21T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.6, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c71_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c71_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-21T00:00:00Z', '2026-08-21T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3289, true, 1, 3289, 3816.0, 0.86, 0.13),
  ('2026 Iran war', 25223, true, 1, 25223, 26925.0, 0.94, 1.0),
  ('List of attacks during the 2026 Iran war', 556, true, NULL::integer, 556, 485.0, 1.15, 0.02),
  ('Mojtaba Khamenei', 3743, false, NULL::integer, 3743, 4049.0, 0.92, 0.15),
  ('Ali Khamenei', 4342, false, 1, 4342, 4278.0, 1.01, 0.17),
  ('Islamic Revolutionary Guard Corps', 1720, false, NULL::integer, 1720, 1792.0, 0.96, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-21T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.4, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c72_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c72_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-21T00:00:00Z', '2026-08-21T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1731, false, NULL::integer, 1731, 1593.0, 1.09, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-21T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-22 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-22T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c73_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c73_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-22T00:00:00Z', '2026-08-22T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3069, true, NULL::integer, 3069, 3816.0, 0.8, 0.13),
  ('2026 Iran war', 23115, true, 7, 23115, 26925.0, 0.86, 1.0),
  ('List of attacks during the 2026 Iran war', 457, true, NULL::integer, 457, 485.0, 0.94, 0.02),
  ('Mojtaba Khamenei', 4111, false, 2, 4111, 4049.0, 1.02, 0.18),
  ('Ali Khamenei', 4123, false, NULL::integer, 4123, 4278.0, 0.96, 0.18),
  ('Islamic Revolutionary Guard Corps', 1508, false, NULL::integer, 1508, 1792.0, 0.84, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-22T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 6.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c74_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c74_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-22T00:00:00Z', '2026-08-22T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 1650, false, NULL::integer, 1650, 1593.0, 1.04, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-22T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-23 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-23T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c75_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c75_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-23T00:00:00Z', '2026-08-23T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3013, true, NULL::integer, 3013, 3816.0, 0.79, 0.13),
  ('2026 Iran war', 23212, true, 20, 23212, 26925.0, 0.86, 1.0),
  ('List of attacks during the 2026 Iran war', 447, true, NULL::integer, 447, 485.0, 0.92, 0.02),
  ('Mojtaba Khamenei', 3679, false, NULL::integer, 3679, 4049.0, 0.91, 0.16),
  ('Ali Khamenei', 4248, false, NULL::integer, 4248, 4278.0, 0.99, 0.18),
  ('Islamic Revolutionary Guard Corps', 1716, false, NULL::integer, 1716, 1792.0, 0.96, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-23T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 14.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c76_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c76_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-23T00:00:00Z', '2026-08-23T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 6484, false, NULL::integer, 6484, 1593.0, 4.07, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-23T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-24 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-24T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.6, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c77_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c77_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-24T00:00:00Z', '2026-08-24T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4331, true, NULL::integer, 4331, 3816.0, 1.13, 0.15),
  ('2026 Iran war', 28542, true, 20, 28542, 26925.0, 1.06, 1.0),
  ('List of attacks during the 2026 Iran war', 478, true, NULL::integer, 478, 485.0, 0.99, 0.02),
  ('Mojtaba Khamenei', 4252, false, NULL::integer, 4252, 4049.0, 1.05, 0.15),
  ('Ali Khamenei', 4698, false, NULL::integer, 4698, 4278.0, 1.1, 0.16),
  ('Islamic Revolutionary Guard Corps', 1714, false, NULL::integer, 1714, 1792.0, 0.96, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-24T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 21.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c78_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c78_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-24T00:00:00Z', '2026-08-24T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 16317, false, 2, 16317, 1593.0, 10.24, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-24T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-25 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-25T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.8, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c79_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c79_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-25T00:00:00Z', '2026-08-25T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4004, true, NULL::integer, 4004, 3816.0, 1.05, 0.15),
  ('2026 Iran war', 26775, true, 10, 26775, 26925.0, 0.99, 1.0),
  ('List of attacks during the 2026 Iran war', 593, true, 1, 593, 485.0, 1.22, 0.02),
  ('Mojtaba Khamenei', 5922, false, 1, 5922, 4049.0, 1.46, 0.22),
  ('Ali Khamenei', 5033, false, 1, 5033, 4278.0, 1.18, 0.19),
  ('Islamic Revolutionary Guard Corps', 1731, false, NULL::integer, 1731, 1792.0, 0.97, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-25T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 15.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c80_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c80_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-25T00:00:00Z', '2026-08-25T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 7693, false, NULL::integer, 7693, 1593.0, 4.83, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-25T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-26 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-26T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.9, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c81_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c81_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-26T00:00:00Z', '2026-08-26T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4087, true, 4, 4087, 3816.0, 1.07, 0.15),
  ('2026 Iran war', 27776, true, 9, 27776, 26925.0, 1.03, 1.0),
  ('List of attacks during the 2026 Iran war', 568, true, 1, 568, 485.0, 1.17, 0.02),
  ('Mojtaba Khamenei', 6044, false, 1, 6044, 4049.0, 1.49, 0.22),
  ('Ali Khamenei', 5282, false, 1, 5282, 4278.0, 1.23, 0.19),
  ('Islamic Revolutionary Guard Corps', 1787, false, NULL::integer, 1787, 1792.0, 1.0, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-26T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 11.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c82_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c82_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-26T00:00:00Z', '2026-08-26T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 4631, false, 5, 4631, 1593.0, 2.91, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-26T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-27 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-27T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c83_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c83_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-27T00:00:00Z', '2026-08-27T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4293, true, NULL::integer, 4293, 3816.0, 1.12, 0.18),
  ('2026 Iran war', 24092, true, 2, 24092, 26925.0, 0.89, 1.0),
  ('List of attacks during the 2026 Iran war', 490, true, NULL::integer, 490, 485.0, 1.01, 0.02),
  ('Mojtaba Khamenei', 5092, false, NULL::integer, 5092, 4049.0, 1.26, 0.21),
  ('Ali Khamenei', 4817, false, 2, 4817, 4278.0, 1.13, 0.2),
  ('Islamic Revolutionary Guard Corps', 1645, false, 1, 1645, 1792.0, 0.92, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-27T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 34.4, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c84_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c84_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-27T00:00:00Z', '2026-08-27T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Harald V', 81599, false, 61, 81599, 1593.0, 51.22, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-27T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-28 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-28T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.3, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c85_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c85_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-28T00:00:00Z', '2026-08-28T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5077, true, NULL::integer, 5077, 3816.0, 1.33, 0.21),
  ('2026 Iran war', 24595, true, 9, 24595, 26925.0, 0.91, 1.0),
  ('List of attacks during the 2026 Iran war', 513, true, NULL::integer, 513, 485.0, 1.06, 0.02),
  ('Mojtaba Khamenei', 4591, false, 1, 4591, 4049.0, 1.13, 0.19),
  ('Ali Khamenei', 4708, false, 3, 4708, 4278.0, 1.1, 0.19),
  ('Islamic Revolutionary Guard Corps', 1552, false, NULL::integer, 1552, 1792.0, 0.87, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-28T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 51.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c86_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c86_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-28T00:00:00Z', '2026-08-28T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 292634, true, 220, 292634, 9426.0, 31.05, 0.52),
  ('Harald V', 563555, false, 251, 563555, 1593.0, 353.77, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-28T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-29 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-29T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c87_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c87_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-29T00:00:00Z', '2026-08-29T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3226, true, NULL::integer, 3226, 3816.0, 0.85, 0.15),
  ('2026 Iran war', 21109, true, 7, 21109, 26925.0, 0.78, 1.0),
  ('List of attacks during the 2026 Iran war', 497, true, NULL::integer, 497, 485.0, 1.02, 0.02),
  ('Mojtaba Khamenei', 4107, false, NULL::integer, 4107, 4049.0, 1.01, 0.19),
  ('Ali Khamenei', 4180, false, NULL::integer, 4180, 4278.0, 0.98, 0.2),
  ('Islamic Revolutionary Guard Corps', 1368, false, NULL::integer, 1368, 1792.0, 0.76, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-29T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 42.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c88_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c88_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-29T00:00:00Z', '2026-08-29T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 157648, true, 41, 157648, 9426.0, 16.72, 0.8),
  ('Harald V', 197930, false, 27, 197930, 1593.0, 124.25, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-29T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-30 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-30T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.6, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c89_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c89_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-30T00:00:00Z', '2026-08-30T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4112, true, 1, 4112, 3816.0, 1.08, 0.17),
  ('2026 Iran war', 24074, true, 24, 24074, 26925.0, 0.89, 1.0),
  ('List of attacks during the 2026 Iran war', 532, true, NULL::integer, 532, 485.0, 1.1, 0.02),
  ('Mojtaba Khamenei', 4642, false, 1, 4642, 4049.0, 1.15, 0.19),
  ('Ali Khamenei', 4232, false, NULL::integer, 4232, 4278.0, 0.99, 0.18),
  ('Islamic Revolutionary Guard Corps', 1663, false, NULL::integer, 1663, 1792.0, 0.93, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-30T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 35.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c90_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c90_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-30T00:00:00Z', '2026-08-30T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 80096, true, 21, 80096, 9426.0, 8.5, 0.88),
  ('Harald V', 90655, false, 22, 90655, 1593.0, 56.91, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-30T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-08-31 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-31T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.4, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c91_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c91_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-31T00:00:00Z', '2026-08-31T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 6184, true, NULL::integer, 6184, 3816.0, 1.62, 0.2),
  ('2026 Iran war', 31109, true, NULL::integer, 31109, 26925.0, 1.16, 1.0),
  ('List of attacks during the 2026 Iran war', 783, true, NULL::integer, 783, 485.0, 1.61, 0.03),
  ('Mojtaba Khamenei', 4905, false, NULL::integer, 4905, 4049.0, 1.21, 0.16),
  ('Ali Khamenei', 4997, false, NULL::integer, 4997, 4278.0, 1.17, 0.16),
  ('Islamic Revolutionary Guard Corps', 2377, false, NULL::integer, 2377, 1792.0, 1.33, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-08-31T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 32.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c92_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c92_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-08-31T00:00:00Z', '2026-08-31T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 59147, true, NULL::integer, 59147, 9426.0, 6.27, 0.94),
  ('Harald V', 63170, false, NULL::integer, 63170, 1593.0, 39.65, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-08-31T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-01 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-01T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.3, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c93_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c93_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-01T00:00:00Z', '2026-09-01T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 5133, true, NULL::integer, 5133, 3816.0, 1.35, 0.17),
  ('2026 Iran war', 30528, true, NULL::integer, 30528, 26925.0, 1.13, 1.0),
  ('List of attacks during the 2026 Iran war', 769, true, NULL::integer, 769, 485.0, 1.59, 0.03),
  ('Mojtaba Khamenei', 4220, false, NULL::integer, 4220, 4049.0, 1.04, 0.14),
  ('Ali Khamenei', 4786, false, NULL::integer, 4786, 4278.0, 1.12, 0.16),
  ('Islamic Revolutionary Guard Corps', 2281, false, NULL::integer, 2281, 1792.0, 1.27, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-01T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 30.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c94_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c94_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-01T00:00:00Z', '2026-09-01T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 65977, true, NULL::integer, 65977, 9426.0, 7.0, 1.0),
  ('Harald V', 50544, false, NULL::integer, 50544, 1593.0, 31.73, 0.77)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-01T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-02 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-02T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c95_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c95_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-02T00:00:00Z', '2026-09-02T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4506, true, NULL::integer, 4506, 3816.0, 1.18, 0.13),
  ('2026 Iran war', 34532, true, NULL::integer, 34532, 26925.0, 1.28, 1.0),
  ('List of attacks during the 2026 Iran war', 834, true, NULL::integer, 834, 485.0, 1.72, 0.02),
  ('Mojtaba Khamenei', 4296, false, NULL::integer, 4296, 4049.0, 1.06, 0.12),
  ('Ali Khamenei', 4721, false, NULL::integer, 4721, 4278.0, 1.1, 0.14),
  ('Islamic Revolutionary Guard Corps', 2299, false, NULL::integer, 2299, 1792.0, 1.28, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-02T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 26.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c96_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c96_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-02T00:00:00Z', '2026-09-02T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 33700, true, NULL::integer, 33700, 9426.0, 3.58, 1.0),
  ('Harald V', 30168, false, NULL::integer, 30168, 1593.0, 18.94, 0.9)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-02T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-03 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-03T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c97_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c97_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-03T00:00:00Z', '2026-09-03T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4232, true, NULL::integer, 4232, 3816.0, 1.11, 0.14),
  ('2026 Iran war', 31258, true, NULL::integer, 31258, 26925.0, 1.16, 1.0),
  ('List of attacks during the 2026 Iran war', 759, true, NULL::integer, 759, 485.0, 1.56, 0.02),
  ('Mojtaba Khamenei', 3904, false, NULL::integer, 3904, 4049.0, 0.96, 0.12),
  ('Ali Khamenei', 4586, false, NULL::integer, 4586, 4278.0, 1.07, 0.15),
  ('Islamic Revolutionary Guard Corps', 1855, false, NULL::integer, 1855, 1792.0, 1.04, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-03T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 22.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c98_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c98_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-03T00:00:00Z', '2026-09-03T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 15990, true, NULL::integer, 15990, 9426.0, 1.7, 0.84),
  ('Harald V', 18963, false, NULL::integer, 18963, 1593.0, 11.9, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-03T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-04 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-04T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c99_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c99_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-04T00:00:00Z', '2026-09-04T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3918, true, NULL::integer, 3918, 3816.0, 1.03, 0.14),
  ('2026 Iran war', 27050, true, NULL::integer, 27050, 26925.0, 1.0, 1.0),
  ('List of attacks during the 2026 Iran war', 762, true, NULL::integer, 762, 485.0, 1.57, 0.03),
  ('Mojtaba Khamenei', 3463, false, NULL::integer, 3463, 4049.0, 0.86, 0.13),
  ('Ali Khamenei', 4084, false, NULL::integer, 4084, 4278.0, 0.95, 0.15),
  ('Islamic Revolutionary Guard Corps', 1768, false, NULL::integer, 1768, 1792.0, 0.99, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-04T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 21.9, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c100_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c100_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-04T00:00:00Z', '2026-09-04T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 17381, true, NULL::integer, 17381, 9426.0, 1.84, 0.95),
  ('Harald V', 18262, false, NULL::integer, 18262, 1593.0, 11.46, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-04T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-05 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-05T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c101_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c101_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-05T00:00:00Z', '2026-09-05T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3104, true, NULL::integer, 3104, 3816.0, 0.81, 0.12),
  ('2026 Iran war', 25003, true, NULL::integer, 25003, 26925.0, 0.93, 1.0),
  ('List of attacks during the 2026 Iran war', 497, true, NULL::integer, 497, 485.0, 1.02, 0.02),
  ('Mojtaba Khamenei', 3199, false, NULL::integer, 3199, 4049.0, 0.79, 0.13),
  ('Ali Khamenei', 3841, false, NULL::integer, 3841, 4278.0, 0.9, 0.15),
  ('Islamic Revolutionary Guard Corps', 1635, false, NULL::integer, 1635, 1792.0, 0.91, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-05T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 20.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c102_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c102_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-05T00:00:00Z', '2026-09-05T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 13752, true, NULL::integer, 13752, 9426.0, 1.46, 0.88),
  ('Harald V', 15647, false, NULL::integer, 15647, 1593.0, 9.82, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-05T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-06 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-06T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c103_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c103_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-06T00:00:00Z', '2026-09-06T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3420, true, NULL::integer, 3420, 3816.0, 0.9, 0.14),
  ('2026 Iran war', 23668, true, NULL::integer, 23668, 26925.0, 0.88, 1.0),
  ('List of attacks during the 2026 Iran war', 489, true, NULL::integer, 489, 485.0, 1.01, 0.02),
  ('Mojtaba Khamenei', 3643, false, NULL::integer, 3643, 4049.0, 0.9, 0.15),
  ('Ali Khamenei', 4172, false, NULL::integer, 4172, 4278.0, 0.98, 0.18),
  ('Islamic Revolutionary Guard Corps', 1792, false, NULL::integer, 1792, 1792.0, 1.0, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-06T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 21.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c104_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c104_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-06T00:00:00Z', '2026-09-06T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 15117, true, NULL::integer, 15117, 9426.0, 1.6, 0.9),
  ('Harald V', 16811, false, NULL::integer, 16811, 1593.0, 10.55, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-06T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-07 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-07T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c105_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c105_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-07T00:00:00Z', '2026-09-07T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4430, true, NULL::integer, 4430, 3816.0, 1.16, 0.17),
  ('2026 Iran war', 25394, true, NULL::integer, 25394, 26925.0, 0.94, 1.0),
  ('List of attacks during the 2026 Iran war', 521, true, NULL::integer, 521, 485.0, 1.07, 0.02),
  ('Mojtaba Khamenei', 4117, false, NULL::integer, 4117, 4049.0, 1.02, 0.16),
  ('Ali Khamenei', 4036, false, NULL::integer, 4036, 4278.0, 0.94, 0.16),
  ('Islamic Revolutionary Guard Corps', 1740, false, NULL::integer, 1740, 1792.0, 0.97, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-07T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 19.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c106_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c106_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-07T00:00:00Z', '2026-09-07T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 12940, true, NULL::integer, 12940, 9426.0, 1.37, 0.92),
  ('Harald V', 14049, false, NULL::integer, 14049, 1593.0, 8.82, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-07T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-08 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-08T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.8, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c107_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c107_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-08T00:00:00Z', '2026-09-08T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3901, true, NULL::integer, 3901, 3816.0, 1.02, 0.14),
  ('2026 Iran war', 28179, true, NULL::integer, 28179, 26925.0, 1.05, 1.0),
  ('List of attacks during the 2026 Iran war', 539, true, NULL::integer, 539, 485.0, 1.11, 0.02),
  ('Mojtaba Khamenei', 4840, false, NULL::integer, 4840, 4049.0, 1.2, 0.17),
  ('Ali Khamenei', 4330, false, NULL::integer, 4330, 4278.0, 1.01, 0.15),
  ('Islamic Revolutionary Guard Corps', 1911, false, NULL::integer, 1911, 1792.0, 1.07, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-08T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 17.4, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c108_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c108_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-08T00:00:00Z', '2026-09-08T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 7823, true, NULL::integer, 7823, 9426.0, 0.83, 0.77),
  ('Harald V', 10210, false, NULL::integer, 10210, 1593.0, 6.41, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-08T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-09 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-09T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.3, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c109_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c109_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-09T00:00:00Z', '2026-09-09T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3985, true, NULL::integer, 3985, 3816.0, 1.04, 0.13),
  ('2026 Iran war', 31043, true, NULL::integer, 31043, 26925.0, 1.15, 1.0),
  ('List of attacks during the 2026 Iran war', 600, true, NULL::integer, 600, 485.0, 1.24, 0.02),
  ('Mojtaba Khamenei', 3844, false, NULL::integer, 3844, 4049.0, 0.95, 0.12),
  ('Ali Khamenei', 4029, false, NULL::integer, 4029, 4278.0, 0.94, 0.13),
  ('Islamic Revolutionary Guard Corps', 2377, false, NULL::integer, 2377, 1792.0, 1.33, 0.08)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-09T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 31.3, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c110_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c110_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-09T00:00:00Z', '2026-09-09T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 43959, true, NULL::integer, 43959, 9426.0, 4.66, 0.78),
  ('Harald V', 56715, false, NULL::integer, 56715, 1593.0, 35.6, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-09T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-10 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-10T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.1, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c111_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c111_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-10T00:00:00Z', '2026-09-10T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3788, true, NULL::integer, 3788, 3816.0, 0.99, 0.12),
  ('2026 Iran war', 31785, true, NULL::integer, 31785, 26925.0, 1.18, 1.0),
  ('List of attacks during the 2026 Iran war', 617, true, NULL::integer, 617, 485.0, 1.27, 0.02),
  ('Mojtaba Khamenei', 4801, false, NULL::integer, 4801, 4049.0, 1.19, 0.15),
  ('Ali Khamenei', 4463, false, NULL::integer, 4463, 4278.0, 1.04, 0.14),
  ('Islamic Revolutionary Guard Corps', 1995, false, NULL::integer, 1995, 1792.0, 1.11, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-10T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 27.7, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c112_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c112_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-10T00:00:00Z', '2026-09-10T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 31328, true, NULL::integer, 31328, 9426.0, 3.32, 0.84),
  ('Harald V', 37187, false, NULL::integer, 37187, 1593.0, 23.34, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-10T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-11 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-11T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.4, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c113_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c113_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-11T00:00:00Z', '2026-09-11T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3882, true, NULL::integer, 3882, 3816.0, 1.02, 0.12),
  ('2026 Iran war', 33002, true, NULL::integer, 33002, 26925.0, 1.23, 1.0),
  ('List of attacks during the 2026 Iran war', 617, true, NULL::integer, 617, 485.0, 1.27, 0.02),
  ('Mojtaba Khamenei', 6547, false, NULL::integer, 6547, 4049.0, 1.62, 0.2),
  ('Ali Khamenei', 5761, false, NULL::integer, 5761, 4278.0, 1.35, 0.17),
  ('Islamic Revolutionary Guard Corps', 2283, false, NULL::integer, 2283, 1792.0, 1.27, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-11T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 29.0, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c114_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c114_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-11T00:00:00Z', '2026-09-11T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 27602, true, NULL::integer, 27602, 9426.0, 2.93, 0.64),
  ('Harald V', 43259, false, NULL::integer, 43259, 1593.0, 27.16, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-11T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-12 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-12T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.7, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c115_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c115_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-12T00:00:00Z', '2026-09-12T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3397, true, NULL::integer, 3397, 3816.0, 0.89, 0.11),
  ('2026 Iran war', 29652, true, NULL::integer, 29652, 26925.0, 1.1, 1.0),
  ('List of attacks during the 2026 Iran war', 528, true, NULL::integer, 528, 485.0, 1.09, 0.02),
  ('Mojtaba Khamenei', 6924, false, NULL::integer, 6924, 4049.0, 1.71, 0.23),
  ('Ali Khamenei', 6393, false, NULL::integer, 6393, 4278.0, 1.49, 0.22),
  ('Islamic Revolutionary Guard Corps', 2061, false, NULL::integer, 2061, 1792.0, 1.15, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-12T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 24.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c116_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c116_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-12T00:00:00Z', '2026-09-12T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 16945, true, NULL::integer, 16945, 9426.0, 1.8, 0.7),
  ('Harald V', 24244, false, NULL::integer, 24244, 1593.0, 15.22, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-12T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-13 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-13T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 8.0, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c117_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c117_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-13T00:00:00Z', '2026-09-13T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 3560, true, NULL::integer, 3560, 3816.0, 0.93, 0.13),
  ('2026 Iran war', 27953, true, NULL::integer, 27953, 26925.0, 1.04, 1.0),
  ('List of attacks during the 2026 Iran war', 439, true, NULL::integer, 439, 485.0, 0.91, 0.02),
  ('Mojtaba Khamenei', 6117, false, NULL::integer, 6117, 4049.0, 1.51, 0.22),
  ('Ali Khamenei', 5855, false, NULL::integer, 5855, 4278.0, 1.37, 0.21),
  ('Islamic Revolutionary Guard Corps', 2045, false, NULL::integer, 2045, 1792.0, 1.14, 0.07)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-13T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 18.2, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c118_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c118_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-13T00:00:00Z', '2026-09-13T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 9426, true, NULL::integer, 9426, 9426.0, 1.0, 0.83),
  ('Harald V', 11422, false, NULL::integer, 11422, 1593.0, 7.17, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-13T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-14 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-14T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 7.2, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c119_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c119_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-14T00:00:00Z', '2026-09-14T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4023, true, NULL::integer, 4023, 3816.0, 1.05, 0.12),
  ('2026 Iran war', 32539, true, NULL::integer, 32539, 26925.0, 1.21, 1.0),
  ('List of attacks during the 2026 Iran war', 470, true, NULL::integer, 470, 485.0, 0.97, 0.01),
  ('Mojtaba Khamenei', 5248, false, NULL::integer, 5248, 4049.0, 1.3, 0.16),
  ('Ali Khamenei', 5258, false, NULL::integer, 5258, 4278.0, 1.23, 0.16),
  ('Islamic Revolutionary Guard Corps', 2112, false, NULL::integer, 2112, 1792.0, 1.18, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-14T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 15.1, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c120_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c120_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-14T00:00:00Z', '2026-09-14T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 6343, true, NULL::integer, 6343, 9426.0, 0.67, 0.85),
  ('Harald V', 7488, false, NULL::integer, 7488, 1593.0, 4.7, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-14T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());
-- 2026-09-15 (2개 이슈 활성)
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-15T23:59:59Z', '2026 Iran War — Strait of Hormuz Crisis', 6.8, 'CONFIRMED', 'replay', 'demo-iran-hormuz-2026', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c121_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c121_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-15T00:00:00Z', '2026-09-15T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('2026 Strait of Hormuz crisis', 4527, true, NULL::integer, 4527, 3816.0, 1.19, 0.14),
  ('2026 Iran war', 32341, true, NULL::integer, 32341, 26925.0, 1.2, 1.0),
  ('List of attacks during the 2026 Iran war', 498, true, NULL::integer, 498, 485.0, 1.03, 0.02),
  ('Mojtaba Khamenei', 4283, false, NULL::integer, 4283, 4049.0, 1.06, 0.13),
  ('Ali Khamenei', 4961, false, NULL::integer, 4961, 4278.0, 1.16, 0.15),
  ('Islamic Revolutionary Guard Corps', 1997, false, NULL::integer, 1997, 1792.0, 1.11, 0.06)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status, source, issue_key, first_detected_at, hot, category)
VALUES ('2026-09-15T23:59:59Z', 'Harald V 국왕 서거 — Haakon 8세 즉위', 12.8, 'CONFIRMED', 'replay', 'demo-haakon-succession-2026-08-28', '2026-07-17T00:00:00Z', false, 'world')
RETURNING id \gset c122_
INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, views, view_baseline, spike_score, size_score, completeness, window_start, window_end)
SELECT :c122_id, p.id, v.weight, v.is_seed, v.ec, v.vw, v.vb, v.sp, v.sz, 'complete', '2026-09-15T00:00:00Z', '2026-09-15T23:59:59Z'
FROM wiki_page p
JOIN (VALUES
  ('Haakon VIII', 4655, true, NULL::integer, 4655, 9426.0, 0.49, 0.87),
  ('Harald V', 5366, false, NULL::integer, 5366, 1593.0, 3.37, 1.0)
) AS v(title, weight, is_seed, ec, vw, vb, sp, sz) ON p.title = v.title
WHERE p.wiki = 'enwiki';
INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at)
VALUES ('2026-09-15T23:59:59Z', 'replay', 2, 'v1-demo', 24, now());

-- 대표 issue_report·cluster_stock — 각 이슈의 최신 스냅샷에만 부착
-- (issue_key로 재사용되므로 프론트는 상세 조회 시 항상 최신 걸 본다는 뜻은
-- 아니다 — 지금 스키마는 cluster_id 단위라 스냅샷마다 따로다. 데모 목적상
-- 최신 스냅샷만 채운다.)

INSERT INTO issue_report (cluster_id, summary, model)
SELECT id, '2026-07-17~09-17 실제 위키백과 편집·조회 시계열 기반 리플레이 데모. '
  || '2026 Iran War — Strait of Hormuz Crisis 관련 문서 6개의 실측 신호를 매일 스냅샷으로 재구성했다.',
  'demo-manual-2026-09-17'
FROM issue_cluster WHERE issue_key = 'demo-iran-hormuz-2026' ORDER BY snapshot_ts DESC LIMIT 1
ON CONFLICT (cluster_id) DO NOTHING;

INSERT INTO issue_report (cluster_id, summary, model)
SELECT id, '2026-07-17~09-17 실제 위키백과 편집·조회 시계열 기반 리플레이 데모. '
  || 'Harald V 국왕 서거 — Haakon 8세 즉위 관련 문서 2개의 실측 신호를 매일 스냅샷으로 재구성했다.',
  'demo-manual-2026-09-17'
FROM issue_cluster WHERE issue_key = 'demo-haakon-succession-2026-08-28' ORDER BY snapshot_ts DESC LIMIT 1
ON CONFLICT (cluster_id) DO NOTHING;

INSERT INTO cluster_stock (cluster_id, ticker, tier, similarity, gdelt_lift, verified, match_path, rationale, verified_at, issue_key, prompt_version, check_state, confidence)
SELECT id, 'CVX', 'BOTH', 0.21, 3.6, true, 'REGION',
  '§11 실측(2026-09-07) 이란·원유 테마 GDELT 동시출현 3.6배 인용.',
  now(), 'demo-iran-hormuz-2026', 'v1', 'DONE', 'strong'
FROM issue_cluster WHERE issue_key = 'demo-iran-hormuz-2026' ORDER BY snapshot_ts DESC LIMIT 1;

INSERT INTO cluster_stock (cluster_id, ticker, tier, gdelt_lift, verified, match_path, rationale, verified_at, issue_key, prompt_version, check_state, confidence)
SELECT id, 'XOM', 'GDELT_ONLY', 2.6, true, 'REGION',
  '§11 실측(2026-09-07) 동시출현 2.6배 인용.',
  now(), 'demo-iran-hormuz-2026', 'v1', 'DONE', 'strong'
FROM issue_cluster WHERE issue_key = 'demo-iran-hormuz-2026' ORDER BY snapshot_ts DESC LIMIT 1;

INSERT INTO cluster_stock (cluster_id, ticker, tier, similarity, verified, match_path, rationale, verified_at, issue_key, prompt_version, check_state, confidence)
SELECT id, 'FRO', 'EMBEDDING_ONLY', 0.19, true, 'SUPPLY_CHAIN',
  '호르무즈 해협 봉쇄 위협 지속 시 유조선 운임 급등 경로 — 뉴스 동시출현으로는 아직 안 잡히는 2차 효과.',
  now(), 'demo-iran-hormuz-2026', 'v1', 'DONE', 'weak'
FROM issue_cluster WHERE issue_key = 'demo-iran-hormuz-2026' ORDER BY snapshot_ts DESC LIMIT 1;
-- Haakon 8세 즉위: 관련 상장 종목 없음(의도적으로 안 넣음 — 왕실 승계는 매칭 경로가 없다).

COMMIT;

SELECT issue_key, count(*) AS 스냅샷수, min(snapshot_ts) AS 시작, max(snapshot_ts) AS 끝, max(pulse_score) AS 최고점수
FROM issue_cluster WHERE issue_key LIKE 'demo-%' GROUP BY issue_key;
