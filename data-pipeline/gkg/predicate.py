"""클러스터 → GKG 이슈 술어 변환. WP-148.

`gkg/driver.py` 는 여태 이슈 술어를 사람이 손으로 줬다(`--theme HURRICANE
--location florida`). 실 파이프라인에서 이슈는 **위키 문서들의 묶음**이지 GKG 기사
필터가 아니라, 그 사이를 잇는 코드가 없었다 — 2026-09-18 1일 canary 도 이 단계를
우회해 통제 행을 넣었다. 이 모듈이 그 구멍이다.

핵심 규칙: **관측된 어휘에만 근거한다**
    클러스터 제목에서 뽑은 용어라도, 그 창의 GKG 코퍼스에 실제로 나타난 테마 코드·
    지역 풀네임에 걸리지 않으면 버린다. 이유는 실패가 조용하기 때문이다 — 없는 테마로
    술어를 만들면 이슈 기사가 0건이 되고, `rank()` 가 빈 리스트를 돌려주며, 파이프라인은
    "이 이슈에는 관련 기관이 없다"는 **정상 결과처럼** 흘러간다. 에러가 안 난다.

왜 Wikidata·LLM 을 쓰지 않나
    둘 다 이 프로젝트에서 이미 폐기됐다. Wikidata 관계 속성은 전수 검사에서 넓은 건
    무관한 배경을 다 끌어오고 좁은 건 진짜 문서를 놓쳐 게이트로 못 쓴다는 결론이
    났고(2026-09-09), 신규 사건 문서는 `claims: {}` 로 비어 있다 — 술어가 가장 필요한
    "막 생긴 이슈"에서 정확히 실패한다. LLM 생성은 비결정성과 환각이 실측됐고
    (2026-09-08), 여기서는 **존재하지 않는 테마 코드**를 지어내는 형태로 나타나 위의
    조용한 0건 실패로 직행한다.

⚠️ **지지도는 상한이다.** 용어 하나의 지지도를 "그 용어에 걸리는 코드들의 문서빈도 합"
으로 재는데, 한 기사가 `NATURAL_DISASTER_HURRICANE` 과 `HURRICANE_WARNING` 을 같이
달고 있으면 두 번 세어진다. 실제 기사 수보다 크거나 같다. 일반성 가드가 이 값으로
자르므로 **가드는 보수적으로 동작한다**(애매한 용어를 덜 통과시킨다). 정확한 기사 수가
필요하면 코퍼스를 한 번 더 훑어야 하는데, 가드 목적에는 상한으로 충분하다.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .lift import IssuePredicate
from .parse import Record

# 제목 토큰 중 테마 용어 후보에서 빼는 것들. 위키 제목의 구조어·연도·너무 흔한 말이다.
# ⚠️ 여기 없는 일반어는 일반성 가드(max_corpus_ratio)가 잡는다 — 목록으로 다 막으려
# 하지 말 것. 목록이 길어질수록 사건마다 손보게 되고 그게 곧 낡는다.
STOPWORDS = frozenset({
    "the", "of", "in", "on", "at", "to", "for", "and", "or", "a", "an",
    "list", "timeline", "history", "effects", "impact", "aftermath",
    "response", "reactions", "casualties", "deaths", "victims",
    "united", "states", "state", "national", "international", "world",
    "new", "old", "first", "second", "third", "century", "year", "years",
})

#: 테마 용어 최소 길이. `air`·`oil` 같은 3글자는 부분문자열 매칭에서 무관한 코드에
#: 광범위하게 걸린다(`oil` ⊂ `SPOILAGE`). 지역은 짧아도 단어 경계 매칭이라 제외.
MIN_THEME_TERM_LEN = 4


@dataclass(frozen=True)
class Member:
    """클러스터 멤버 하나. `cluster_member` 한 행에 대응한다."""

    title: str
    is_seed: bool = True


@dataclass(frozen=True)
class ScoredTerm:
    """채택된 술어 용어와 그 근거."""

    term: str
    support: int
    """이 용어에 걸리는 코퍼스 항목들의 문서빈도 합 (상한 — 모듈 docstring ⚠️)."""
    hits: tuple[str, ...]
    """실제로 걸린 관측 어휘. 왜 이 용어가 뽑혔는지 사람이 확인하는 용도다."""
    from_seed: bool


@dataclass(frozen=True)
class Vocabulary:
    """그 창의 GKG 코퍼스에서 **실제로 관측된** 어휘와 문서빈도.

    themes 는 대문자 코드 → 기사 수, locations 는 소문자 풀네임 → 기사 수.
    `parse.Record` 가 이미 그 대소문자로 정규화해 둔다.
    """

    n_docs: int
    themes: Mapping[str, int] = field(default_factory=dict)
    locations: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: Iterable[Record]) -> Vocabulary:
        """레코드 이터러블에서 어휘를 센다. 단일프로세스·테스트용.

        Spark 에서는 파티션마다 이걸 만들고 `merge` 로 합친다 — `Aggregate` 와 같은 꼴.
        """
        themes: Counter[str] = Counter()
        locations: Counter[str] = Counter()
        n = 0
        for record in records:
            n += 1
            # 한 기사 안의 중복은 한 번만 — 문서빈도지 언급 횟수가 아니다.
            themes.update(set(record.themes))
            locations.update(set(record.locations))
        return cls(n_docs=n, themes=dict(themes), locations=dict(locations))

    def merge(self, other: Vocabulary) -> Vocabulary:
        themes: Counter[str] = Counter(self.themes)
        themes.update(other.themes)
        locations: Counter[str] = Counter(self.locations)
        locations.update(other.locations)
        return Vocabulary(
            n_docs=self.n_docs + other.n_docs,
            themes=dict(themes),
            locations=dict(locations),
        )


@dataclass(frozen=True)
class Derivation:
    """변환 결과. 버린 것까지 들고 있다.

    🔴 **`predicate` 가 None 일 수 있다.** 양축 다 비면 `IssuePredicate` 가 생성자에서
    막는데(모든 기사가 이슈가 되어 lift 가 전부 1), 그걸 여기서 예외로 터뜨리지 않고
    None 으로 돌려준다 — 클러스터 수백 개를 도는 배치에서 하나 때문에 잡이 죽으면 안
    된다. 호출자가 세고 건너뛴다.

    `rejected` 는 (축, 용어, 이유) 다. 술어가 비었을 때 "왜 아무것도 안 뽑혔나"를
    여기서 읽는다. 이게 없으면 0건 결과와 구분이 안 된다.

    ⚠️ **축을 꼭 같이 적는다.** 한 용어가 한 축에서 떨어지고 다른 축에서 붙는 게
    정상이다 — `florida` 는 테마 코드엔 없고(거부) 지역 풀네임엔 있다(채택). 축 없이
    "florida 관측되지 않음"만 찍으면, 술어에 florida 가 들어가 있는데 버렸다고도
    적혀 있어 읽는 사람이 버그로 오해한다(2026-09-20 실데이터 로그에서 실제로 그랬다).
    """

    predicate: IssuePredicate | None
    themes: tuple[ScoredTerm, ...] = ()
    locations: tuple[ScoredTerm, ...] = ()
    rejected: tuple[tuple[str, str, str], ...] = ()
    #: 테마·지역이 둘 다 실패해 대신 쓴 키워드 (WP-221). 비어 있으면 대체 안 함.
    keywords: tuple[str, ...] = ()


def _flatten(rejected: Mapping[tuple[str, str], str]) -> tuple[tuple[str, str, str], ...]:
    """(축, 용어) → 이유 매핑을 (축, 용어, 이유) 로. 축·용어 순으로 안정 정렬한다."""
    return tuple(
        (axis, term, why)
        for (axis, term), why in sorted(rejected.items())
    )


def title_terms(title: str) -> tuple[str, ...]:
    """위키 문서 제목을 테마 용어 후보로 쪼갠다.

    `Effects of Hurricane Milton in Florida` → `('hurricane', 'milton', 'florida')`.
    괄호 한정어(`Milton (disambiguation)`)는 문서 구분용이라 뺀다. 숫자·연도도 뺀다 —
    `2024` 는 테마 코드에 없고 지역에도 없다.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", title)
    tokens = re.split(r"[^0-9A-Za-z]+", cleaned.lower())
    return tuple(
        t for t in tokens
        if t and not t.isdigit() and t not in STOPWORDS and len(t) >= MIN_THEME_TERM_LEN
    )


#: 대체 키워드 최대 개수. 씨드가 많은 클러스터에서 술어가 넓어지는 걸 막는다.
MAX_KEYWORDS = 3


def title_keyword(title: str) -> str:
    """위키 제목 → 키워드 구절. 괄호 한정어와 앞 관사를 떼고 소문자로.

    `The Odyssey (2026 film)` → `odyssey`, `SummerSlam (2026)` → `summerslam`.
    ⚠️ 앞 관사 `the` 를 떼는 이유: 기사 제목은 "Nolan's Odyssey…" 처럼 관사 없이
    부르는 경우가 많다. 단어 경계 매칭이라 `the odyssey` 로 두면 그 기사들이 빠진다.
    STOPWORDS 로만 된 구절·너무 짧은 구절은 빈 문자열(→ 버림).
    """
    phrase = re.sub(r"\([^)]*\)", " ", title).strip().lower()
    phrase = re.sub(r"\s+", " ", phrase)
    phrase = re.sub(r"^(the|a|an) ", "", phrase)
    words = [w for w in re.split(r"[^0-9a-z]+", phrase) if w]
    if not words or all(w in STOPWORDS or w.isdigit() for w in words):
        return ""
    return phrase if len(phrase) >= MIN_THEME_TERM_LEN else ""


def _keyword_fallback(members: Sequence[Member]) -> tuple[str, ...]:
    """씨드 멤버 제목을 키워드로. 씨드가 없으면 첫 멤버 하나."""
    seeds = [m for m in members if m.is_seed] or list(members[:1])
    out: list[str] = []
    for member in seeds:
        kw = title_keyword(member.title)
        if kw and kw not in out:
            out.append(kw)
        if len(out) >= MAX_KEYWORDS:
            break
    return tuple(out)


def _theme_candidates(
    term: str, vocab: Vocabulary
) -> tuple[int, tuple[str, ...]]:
    """`term` 이 부분문자열로 걸리는 관측 테마 코드들과 지지도 상한.

    `IssuePredicate` 의 테마 매칭과 **같은 의미**여야 한다 — 거기가 `term in code`
    (대문자)라 여기도 그렇게 센다. 두 곳이 갈리면 "뽑을 땐 걸렸는데 집계에선 안 걸리는"
    술어가 나온다.
    """
    upper = term.upper()
    hits = tuple(sorted(code for code in vocab.themes if upper in code))
    return sum(vocab.themes[c] for c in hits), hits


def _location_candidates(
    phrase: str, vocab: Vocabulary
) -> tuple[int, tuple[str, ...]]:
    """`phrase` 가 **단어 경계**로 걸리는 관측 지역 풀네임들과 지지도 상한.

    `IssuePredicate` 의 지역 매칭과 같은 의미다 — 부분문자열로 하면 `florida` 가
    실지명 `floridablanca` 를 오탐한다(lift.py 참조).
    """
    pattern = re.compile(r"\b" + re.escape(phrase.lower()) + r"\b")
    hits = tuple(sorted(name for name in vocab.locations if pattern.search(name)))
    return sum(vocab.locations[n] for n in hits), hits


def derive(
    members: Sequence[Member],
    vocab: Vocabulary,
    *,
    max_themes: int = 2,
    max_locations: int = 3,
    min_support: int = 3,
    min_support_ratio: float = 0.001,
    max_corpus_ratio: float = 0.5,
) -> Derivation:
    """클러스터 멤버에서 이슈 술어를 만든다.

    양축은 `IssuePredicate` 에서 AND 로 묶이고 축 안은 OR 다. 그래서 축을 하나만
    뽑으면 술어가 넓어지고(테마만 = 그 테마의 전 세계 기사), 둘 다 뽑으면 좁아진다
    (§11 Milton = `HURRICANE ∧ florida`).

    거르는 순서와 이유:

    1. **관측 안 됨** — 코퍼스에 그 어휘가 없다. 남기면 이슈 기사 0건이 된다.
    2. **지지도 < max(`min_support`, `min_support_ratio` × 코퍼스)** — 표본이 얇아
       lift 가 튄다. `rank()` 의 `min_issue_count` 와 같은 성격이다.

       ⚠️ **절대 하한만으로는 큰 코퍼스에서 무의미하다.** 하루치 실측(160,838 기사)에서
       `florida` 가 테마 축에도 붙었는데, 걸린 코드가 `TAX_WORLDREPTILES_FLORIDA_
       KINGSNAKE` **하나(19건)** 였다 — 플로리다 왕뱀이다(2026-09-20). 테마는 OR 이라
       이런 게 끼면 술어가 넓어진다. 비례 하한이 코퍼스 크기에 따라 같이 올라간다.
    3. **지지도 > `max_corpus_ratio` × 코퍼스** — 너무 일반적이다. 이슈 집합이
       코퍼스와 같아지면 lift 가 전부 1 로 수렴해 신호가 사라진다. `united`·`states`
       류는 STOPWORDS 로도 빠지지만, 사건마다 다른 일반어는 이 가드가 잡는다.

       ⚠️ **축 하나만 보고 0.25 처럼 조이지 말 것.** 두 축은 AND 로 묶이므로 각 축이
       다소 넓어도 교집합은 좁다 — 실제로 0.25 로 뒀더니 Milton 의 `hurricane`
       (코퍼스의 30%) 이 거부돼 **진짜 사건 테마가 통째로 탈락했다**(2026-09-20).
       0.5 는 "이건 이슈 필터가 아니라 그날 뉴스 사이클 전체다" 선이다. 큰 사건은
       짧은 창에서 코퍼스의 상당 비율을 정당하게 차지한다.

    씨드 멤버를 먼저 본다 — 루트·추가 씨드가 사건 자체의 문서고, 비-seed 는 재급증으로
    끌려온 배경 문서라 사건을 덜 대표한다(명세 §3.2 4번). 동점이면 씨드가 이긴다.
    """
    if not 0 < max_corpus_ratio <= 1:
        raise ValueError("max_corpus_ratio 는 (0, 1] 이어야 한다")
    if vocab.n_docs <= 0:
        return Derivation(predicate=None, rejected=(("*", "*", "코퍼스가 비었다"),))

    ceiling = max_corpus_ratio * vocab.n_docs
    floor = max(min_support, int(min_support_ratio * vocab.n_docs))
    # (축, 용어) 로 중복을 없앤다 — 멤버가 여럿이면 같은 용어가 여러 번 떨어진다.
    rejected: dict[tuple[str, str], str] = {}

    def screen(axis: str, term: str, support: int, hits: tuple[str, ...], seed: bool
               ) -> ScoredTerm | None:
        def drop(why: str) -> None:
            rejected.setdefault((axis, term), why)

        if not hits:
            drop("코퍼스에 관측되지 않음")
            return None
        if support < floor:
            drop(f"지지도 {support} < {floor}")
            return None
        if support > ceiling:
            drop(f"너무 일반적 — 지지도 {support} > {ceiling:.0f}"
                 f" ({max_corpus_ratio:.0%} of {vocab.n_docs})")
            return None
        return ScoredTerm(term=term, support=support, hits=hits, from_seed=seed)

    # --- 테마: 멤버 제목의 토큰 ---
    theme_seen: dict[str, ScoredTerm] = {}
    for member in members:
        for term in title_terms(member.title):
            if term in theme_seen:
                # 같은 용어가 씨드에서도 나왔으면 씨드 출처로 올린다.
                if member.is_seed and not theme_seen[term].from_seed:
                    prev = theme_seen[term]
                    theme_seen[term] = ScoredTerm(
                        prev.term, prev.support, prev.hits, from_seed=True)
                continue
            support, hits = _theme_candidates(term, vocab)
            scored = screen("테마", term, support, hits, member.is_seed)
            if scored:
                theme_seen[term] = scored

    # --- 지역: 멤버 제목 **전체** ---
    # 토큰이 아니라 제목 전체를 쓴다. `Strait of Hormuz` 를 토큰으로 쪼개면 `strait`
    # 하나가 세계의 모든 해협 기사를 끌어온다 — 지역은 고유명 통째로가 맞다.
    location_seen: dict[str, ScoredTerm] = {}
    for member in members:
        phrase = re.sub(r"\([^)]*\)", " ", member.title).strip().lower()
        phrase = re.sub(r"\s+", " ", phrase)
        if not phrase or phrase in location_seen:
            continue
        support, hits = _location_candidates(phrase, vocab)
        scored = screen("지역", phrase, support, hits, member.is_seed)
        if scored:
            location_seen[phrase] = scored

    def pick(pool: dict[str, ScoredTerm], cap: int) -> tuple[ScoredTerm, ...]:
        # 씨드 우선 → 지지도 큰 순 → 이름 순(동점에서 실행마다 흔들리지 않게).
        ordered = sorted(
            pool.values(), key=lambda s: (not s.from_seed, -s.support, s.term))
        return tuple(ordered[:cap])

    themes = pick(theme_seen, max_themes)
    locations = pick(location_seen, max_locations)

    if not themes and not locations:
        # 🔴 테마·지역으로 표현이 안 되는 이슈다(영화·공연·기업 문서). 여기서 멈추면 GDELT
        #    경로가 통째로 0 이 된다 — 2026-09-23 시연 이슈 3개(The Odyssey · IMAX ·
        #    SummerSlam)가 전부 이렇게 떨어졌고, 운영 후보는 100% 임베딩 단독이었다.
        #    씨드 제목을 기사 제목·기관명 키워드로 쓴다(WP-221).
        #    ⚠️ 이 축은 코퍼스 관측 여부를 여기서 못 본다(어휘 스캔이 제목을 안 센다).
        #    조용한 0건·과대 매칭은 driver 가 집계 뒤 이슈 기사 수로 막는다.
        keywords = _keyword_fallback(members)
        if not keywords:
            return Derivation(predicate=None, rejected=_flatten(rejected))
        return Derivation(
            predicate=IssuePredicate(keywords=keywords),
            rejected=_flatten(rejected),
            keywords=keywords,
        )

    predicate = IssuePredicate(
        themes=tuple(t.term.upper() for t in themes),
        locations=tuple(l.term for l in locations),
    )
    return Derivation(
        predicate=predicate,
        themes=themes,
        locations=locations,
        rejected=_flatten(rejected),
    )


def describe(derivation: Derivation) -> str:
    """사람이 읽는 한 덩이 설명. driver 로그에 그대로 찍는다.

    술어가 왜 그렇게 나왔는지가 로그에 없으면, 나중에 lift 가 이상할 때 술어 탓인지
    데이터 탓인지 가를 수 없다.
    """
    if derivation.predicate is None:
        lines = ["술어 생성 실패 — 채택된 용어가 없다."]
    elif derivation.keywords:
        lines = [f"술어: 키워드[{' ∨ '.join(derivation.keywords)}] "
                 "(테마·지역 실패 → 기사 제목·기관명 대체, WP-221)"]
    else:
        themes = " ∨ ".join(t.term.upper() for t in derivation.themes) or "(없음)"
        locations = " ∨ ".join(l.term for l in derivation.locations) or "(없음)"
        lines = [f"술어: 테마[{themes}] ∧ 지역[{locations}]"]
        for scored in derivation.themes + derivation.locations:
            sample = ", ".join(scored.hits[:3])
            more = f" 외 {len(scored.hits) - 3}" if len(scored.hits) > 3 else ""
            lines.append(
                f"  - {scored.term}: 지지도 {scored.support}"
                f"{' (씨드)' if scored.from_seed else ''} ← {sample}{more}")
    if derivation.rejected:
        # 축을 같이 찍는다 — 한 용어가 한 축에서만 떨어지는 건 정상이다(Derivation ⚠️).
        shown = "; ".join(
            f"{axis}:{term}({why})" for axis, term, why in derivation.rejected[:5])
        more = f" 외 {len(derivation.rejected) - 5}" if len(derivation.rejected) > 5 else ""
        lines.append(f"  버림 {len(derivation.rejected)}건: {shown}{more}")
    return "\n".join(lines)
