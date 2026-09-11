"""공통 크기 점수(sizeScore)와 척도 버전 (WP-75).

계약(PULSE_MAP.md §그래프와 지표)
    - sizeScore 는 백엔드가 제공할 공통 척도 0~1이다. 노드 반지름을 정한다.
    - 매 시점 최댓값으로 정규화하지 않는다 — 절대 척도라야 시점 간 크기가 비교된다.
    - 신규/기존 문서의 원시 점수 산식 차이를 여기서 흡수하고 scoreVersion 을 제공한다.
    - 미제공(원시 점수 없음)은 None 이며 0 과 구분한다. 화면이 작은 점선 노드로 그린다.

왜 최댓값 정규화가 아니라 squash 인가
    detector.py 의 spike_score 는 log 로 눌린 값이라 상한이 열려 있다
    (Milton 확정 9.7, 편집만 통과한 문서는 3~4). 매 시점 최댓값으로 나누면
    조용한 날의 작은 급증이 큰 급증처럼 부풀고, 시점 간 버블 크기가 뒤집힌다.
    상한이 1인 포화 함수 s/(s+K) 로 절대 척도를 만든다.

척도 버전
    K 나 산식을 바꾸면 과거 스냅샷과 크기가 어긋난다. 스냅샷마다 SCORE_VERSION 을
    함께 저장해(cluster_snapshot.score_version) 화면이 버전을 표시·구분한다.
"""

from __future__ import annotations

#: size_score 산식 버전. 산식·상수를 바꾸면 반드시 올린다.
SCORE_VERSION = "v1"

#: 포화 상수. spike_score=K 에서 0.5. Milton 확정 9.7 -> 0.66, 편집만 통과 4 -> 0.44.
#: detector.py 의 실측 점수 분포(3~10 대)에서 중간이 0.4~0.6 에 오도록 5.0.
SIZE_SCORE_K = 5.0


def size_score(spike_score: float | None) -> float | None:
    """급등도(spike_score)를 0~1 크기 점수로. 원시 점수가 없으면 None.

    비-씨드 멤버(급증 판정을 직접 통과하지 않고 관계로 딸려온 문서)는
    spike_score 가 없어 None 이다 — 화면은 이를 작은 점선 노드로 그린다.
    """
    if spike_score is None:
        return None
    s = max(0.0, float(spike_score))
    return round(s / (s + SIZE_SCORE_K), 4)


def pulse_score(seed_spike_scores: list[float]) -> float:
    """클러스터 급등도. 씨드 멤버들의 급등도 최댓값.

    합이 아니라 최댓값을 쓰는 이유: 문서 수가 많다고 이슈가 더 뜨거운 건 아니다.
    가장 강하게 급증한 문서가 이슈의 세기를 대표한다. 씨드가 없으면 0.
    """
    if not seed_spike_scores:
        return 0.0
    return round(max(seed_spike_scores), 3)
