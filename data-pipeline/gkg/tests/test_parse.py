"""GKG CSV 파싱 검증. 컬럼 배치는 실물(20241010120000.gkg.csv)로 확인한 값이다."""

from __future__ import annotations

from gkg.parse import MIN_COLUMNS, Record, parse_row, parse_text


def _row(**over) -> list[str]:
    """27컬럼 GKG 행 하나. over 로 특정 컬럼만 바꾼다."""
    cols = [""] * MIN_COLUMNS
    cols[0] = "20241010120000-0"
    cols[1] = "20241010120000"
    cols[3] = "example.com"
    cols[4] = "https://example.com/a"
    cols[7] = "NATURAL_DISASTER;NATURAL_DISASTER_HURRICANE"
    cols[9] = "1#Florida, United States#US#USFL#28#-81#FL"
    cols[13] = "Duke Energy;Florida Power Light"
    cols[14] = "Duke Energy,120;Generac Holdings,300"
    for k, v in over.items():
        cols[int(k[1:])] = v
    return cols


def test_parses_all_fields():
    rec = parse_row(_row())
    assert isinstance(rec, Record)
    assert rec.doc_id == "https://example.com/a"
    # V1(13) + V2(14) 합집합, 소문자, 오프셋 제거, 중복 제거(duke energy 한 번).
    assert rec.orgs == frozenset(
        {"duke energy", "florida power light", "generac holdings"}
    )
    assert rec.themes == ("NATURAL_DISASTER", "NATURAL_DISASTER_HURRICANE")
    assert rec.locations == ("florida, united states",)


def test_org_union_when_only_v2_present():
    rec = parse_row(_row(c13="", c14="Apple Inc,5;Apple Inc,90"))
    assert rec.orgs == frozenset({"apple inc"})  # 같은 기관 두 번 나와도 한 번


def test_empty_org_fields_yield_empty_set():
    rec = parse_row(_row(c13="", c14=""))
    assert rec.orgs == frozenset()


def test_truncated_row_is_dropped():
    assert parse_row(["a", "b", "c"]) is None


def test_doc_id_falls_back_to_record_id_when_url_missing():
    rec = parse_row(_row(c4=""))
    assert rec.doc_id == "20241010120000-0"


def test_parse_text_skips_blank_and_truncated_lines():
    good = "\t".join(_row())
    text = f"{good}\n\n" + "short\tline\n" + good
    recs = list(parse_text(text))
    assert len(recs) == 2


def test_location_without_fullname_is_skipped():
    # 풀네임(#-필드 index 1)이 비면 그 지역은 버린다.
    rec = parse_row(_row(c9="1##US#USFL#28#-81#FL"))
    assert rec.locations == ()
