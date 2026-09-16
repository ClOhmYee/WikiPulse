"""verify_experiment.py의 스키마 검증·폐기 분기를 네트워크 호출 없이 확인한다.

py -3 test_validate.py
"""

from verify_experiment import validate, strip_fences

# 정상 — 통과(verified=true)
assert validate({
    "issue_class": "SECTOR_OR_REGION_EVENT",
    "verified": True, "match_path": "DIRECT_MENTION", "confidence": "strong",
    "rationale_en": "x", "rationale_ko": "y",
}) is None

# 정상 — 탈락(verified=false, 나머지 전부 null)
assert validate({
    "issue_class": "SINGLE_COMPANY_EVENT",
    "verified": False, "match_path": None, "confidence": None,
    "rationale_en": None, "rationale_ko": None,
}) is None

# 위반 — 탈락인데 근거 문장이 남아있음
assert validate({
    "issue_class": "SINGLE_COMPANY_EVENT",
    "verified": False, "match_path": None, "confidence": None,
    "rationale_en": "x", "rationale_ko": None,
}) is not None

# 위반 — 통과인데 근거 문장이 빔
assert validate({
    "issue_class": "SECTOR_OR_REGION_EVENT",
    "verified": True, "match_path": "REGION", "confidence": "weak",
    "rationale_en": "", "rationale_ko": "y",
}) is not None

# 위반 — match_path 값이 스키마 밖
assert validate({
    "issue_class": "SECTOR_OR_REGION_EVENT",
    "verified": True, "match_path": "OTHER", "confidence": "strong",
    "rationale_en": "x", "rationale_ko": "y",
}) is not None

# 위반 — issue_class 값이 스키마 밖
assert validate({
    "issue_class": "OTHER",
    "verified": False, "match_path": None, "confidence": None,
    "rationale_en": None, "rationale_ko": None,
}) is not None

# 위반 — 키 누락
assert validate({"verified": True}) is not None

# 위반 — object가 아님
assert validate(["not", "a", "dict"]) is not None

# 마크다운 펜스 제거
assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
assert strip_fences('{"a": 1}') == '{"a": 1}'

print("OK: validate()/strip_fences() 분기 전부 통과")
