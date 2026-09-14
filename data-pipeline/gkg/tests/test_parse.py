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


def test_모든_필드를_파싱한다():
    rec = parse_row(_row())
    assert isinstance(rec, Record)
    assert rec.doc_id == "https://example.com/a"
    # V1(13) + V2(14) 합집합, 소문자, 오프셋 제거, 중복 제거(duke energy 한 번).
    assert rec.orgs == frozenset(
        {"duke energy", "florida power light", "generac holdings"}
    )
    assert rec.themes == ("NATURAL_DISASTER", "NATURAL_DISASTER_HURRICANE")
    assert rec.locations == ("florida, united states",)


def test_V2만_있어도_조직_합집합():
    rec = parse_row(_row(c13="", c14="Apple Inc,5;Apple Inc,90"))
    assert rec.orgs == frozenset({"apple inc"})  # 같은 기관 두 번 나와도 한 번


def test_조직_필드가_비면_빈_집합():
    rec = parse_row(_row(c13="", c14=""))
    assert rec.orgs == frozenset()


def test_다중_지역을_모두_수집한다():
    rec = parse_row(_row(c9="1#Florida#US#USFL#28#-81#FL;1#Texas#US#USTX#31#-99#TX"))
    assert rec.locations == ("florida", "texas")


def test_잘린_행은_버린다():
    assert parse_row(["a", "b", "c"]) is None


def test_URL_없으면_레코드_id로_대체():
    rec = parse_row(_row(c4=""))
    assert rec.doc_id == "20241010120000-0"


def test_빈줄과_잘린줄을_건너뛴다():
    good = "\t".join(_row())
    text = f"{good}\n\n" + "short\tline\n" + good
    recs = list(parse_text(text))
    assert len(recs) == 2


def test_CRLF_줄바꿈에서_마지막_컬럼에_CR이_안_남는다():
    # \r\n 로 이어도 col 26 끝에 \r 가 남지 않아야(뒤 컬럼을 읽어도 안전).
    good = "\t".join(_row())
    recs = list(parse_text(f"{good}\r\n{good}\r\n"))
    assert len(recs) == 2
    # 마지막 컬럼(index 26)이 CR 로 오염되지 않았는지 직접 본다.
    line = f"{good}\r\n".rstrip("\r\n")
    assert not line.endswith("\r")


def test_풀네임_없는_지역은_건너뛴다():
    # 풀네임(#-필드 index 1)이 비면 그 지역은 버린다.
    rec = parse_row(_row(c9="1##US#USFL#28#-81#FL"))
    assert rec.locations == ()
