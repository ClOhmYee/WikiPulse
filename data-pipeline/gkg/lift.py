"""이슈 술어 + 기관명 lift 집계·랭킹. 순수 파이썬(Spark 의존 없음).

lift = P(기관 | 이슈 기사) / P(기관 | 전체 기사)
     = (기관이 나온 이슈 기사 수 / 이슈 기사 수) / (기관이 나온 전체 기사 수 / 전체 기사 수)

이슈 기사는 전체(코퍼스)의 부분집합이다 — 같은 기간 GKG 전체가 코퍼스, 그중 이슈
술어를 통과한 것이 이슈 기사다. 명세 §11 Milton 은 이슈 = `테마에 HURRICANE ∧
지역에 florida` 로 잡아 10,707 기사, FPL 10.5·Generac 9.3·Duke 8.4·무관 Nvidia 0.4
가 나왔다.

Aggregate 는 병합 가능하다(merge). Spark 는 파일별 부분합을 reduce 로 합치고,
단일프로세스(테스트·소규모)는 aggregate() 한 번으로 낸다 — 같은 산식을 공유한다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from .parse import Record


@dataclass(frozen=True)
class IssuePredicate:
    """이슈 기사를 코퍼스에서 골라내는 술어.

    themes·locations 각각은 "부분일치할 문자열들"이다. 지정된 차원끼리는 AND,
    한 차원 안의 여러 항목은 OR 다 — `themes=("HURRICANE",), locations=("florida",)`
    는 "테마에 HURRICANE 이 있고 그리고 지역에 florida 가 있는" 기사(§11 Milton).

    - theme 매칭: 기사 테마 코드에 term 이 부분문자열로 있으면 참
      (term "HURRICANE" ⊂ 코드 "NATURAL_DISASTER_HURRICANE").
    - location 매칭: 기사 지역 풀네임에 term 이 부분문자열로 있으면 참.
    비교는 대소문자 무시(테마는 대문자, 지역은 소문자로 정규화해 둠).
    """

    themes: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.themes and not self.locations:
            raise ValueError(
                "IssuePredicate 는 themes 나 locations 중 최소 하나가 필요하다. "
                "둘 다 비면 모든 기사가 이슈가 되어 lift 가 전부 1 이 된다."
            )

    def _theme_terms(self) -> tuple[str, ...]:
        return tuple(t.upper() for t in self.themes)

    def _location_terms(self) -> tuple[str, ...]:
        return tuple(l.lower() for l in self.locations)

    def matches(self, record: Record) -> bool:
        if self.themes:
            terms = self._theme_terms()
            if not any(term in code for code in record.themes for term in terms):
                return False
        if self.locations:
            terms = self._location_terms()
            if not any(term in loc for loc in record.locations for term in terms):
                return False
        return True


@dataclass
class Aggregate:
    """기관명 문서빈도 부분합. 병합 가능(Spark reduce 용).

    n_issue/n_corpus 는 기사 수(문서 빈도의 분모). org_issue/org_corpus 는 기관명별
    "그 기관이 나온 기사 수"다.
    """

    n_issue: int = 0
    n_corpus: int = 0
    org_issue: Counter = field(default_factory=Counter)
    org_corpus: Counter = field(default_factory=Counter)

    def add(self, record: Record, is_issue: bool) -> None:
        self.n_corpus += 1
        for org in record.orgs:
            self.org_corpus[org] += 1
        if is_issue:
            self.n_issue += 1
            for org in record.orgs:
                self.org_issue[org] += 1

    def merge(self, other: "Aggregate") -> "Aggregate":
        """부분합 둘을 합친다. Spark reduce 가 파일별 결과를 접을 때 쓴다."""
        self.n_issue += other.n_issue
        self.n_corpus += other.n_corpus
        self.org_issue.update(other.org_issue)
        self.org_corpus.update(other.org_corpus)
        return self


def aggregate(records: Iterable[Record], predicate: IssuePredicate) -> Aggregate:
    """레코드 이터러블을 한 Aggregate 로. 단일프로세스·테스트용."""
    agg = Aggregate()
    for record in records:
        agg.add(record, predicate.matches(record))
    return agg


def compute_lift(issue_count: int, corpus_count: int, n_issue: int, n_corpus: int) -> float:
    """lift = (issue_count/n_issue) / (corpus_count/n_corpus).

    호출자가 issue_count>=1 을 보장하므로 corpus_count>=1(이슈 기사는 코퍼스의
    부분집합), n_issue>=1, n_corpus>=1 이다 — 0 나눗셈이 나지 않는다.
    """
    return (issue_count / n_issue) / (corpus_count / n_corpus)


@dataclass(frozen=True)
class OrgLift:
    """한 기관의 이슈 내 동시 출현 근거."""

    org_name: str
    issue_count: int
    corpus_count: int
    lift: float


def rank(agg: Aggregate, *, min_issue_count: int = 1, top: int | None = None) -> list[OrgLift]:
    """이슈 기사에 나온 기관들을 lift 내림차순으로.

    min_issue_count 로 표본이 얇은 기관(이슈 기사 1건뿐인데 코퍼스에도 1건이라
    lift 가 튀는 잡음)을 거른다. top 이 있으면 상위 N 만.
    동점은 issue_count 큰 순 → 이름 순으로 안정 정렬한다.
    """
    if agg.n_issue == 0:
        return []
    out: list[OrgLift] = []
    for org, issue_count in agg.org_issue.items():
        if issue_count < min_issue_count:
            continue
        corpus_count = agg.org_corpus[org]
        out.append(OrgLift(
            org_name=org,
            issue_count=issue_count,
            corpus_count=corpus_count,
            lift=compute_lift(issue_count, corpus_count, agg.n_issue, agg.n_corpus),
        ))
    out.sort(key=lambda o: (-o.lift, -o.issue_count, o.org_name))
    return out[:top] if top is not None else out
