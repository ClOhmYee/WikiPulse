"""-85 재현율·대조군 오탐 재실행 — 급증 판정을 건드릴 때마다 돌리는 회귀 도구.

    cd data-pipeline && python ../ai/slot-width/replay_regression.py

실덤프 4개월(`out/enwiki/2025-05`·`2025-06`·`2024-09`·`2024-10`)이 필요하다. Spark 안 쓴다.

⚠️ 대조군 14개는 **WP-85 가 쓴 목록이 아니다.** 그 목록이 저장소에 안 남아 있어
(README 에 이름 일부만) 성격만 따라 새로 골랐다 — -85 의 오탐 수치(101·57)와 직접
비교하면 안 된다. 같은 스크립트를 변경 전후로 돌려 **차이**를 보는 용도다.

⚠️ 리플레이는 편집 덤프만 써서 views=None 이다. 조회수 관문이 닫힌 채 도므로
조회수 쪽 변경(WP-87·-90)은 여기 숫자에 안 나타나는 게 정상이다.

기록된 값 (2026-09-15): 재현율 10/12 · 대조군 오탐 49건 · 3/14 문서
"""
import sys
from pathlib import Path
from producer.normalize import canonical_title
from spike.replay import aggregate, read_edit_events, replay_title, first_detection

MONTHS = ["2025-05", "2025-06", "2024-09", "2024-10"]
TARGETS = ["Air_India_Flight_171", "June_2025_Israeli_strikes_on_Iran",
           "June_2025_Los_Angeles_protests", "2025_shootings_of_Minnesota_legislators",
           "American_strikes_on_Iranian_nuclear_sites", "Strait_of_Hormuz",
           "2025_Iran_threat_of_Strait_of_Hormuz_closure", "Hurricane_Milton",
           "Liam_Payne", "Ratan_Tata", "October_2024_Iranian_strikes_against_Israel",
           "Hurricane_Helene"]
CONTROLS = ["List_of_people_named_Peter", "Deaths_in_2025", "Deaths_in_2024",
            "Timeline_of_science_fiction", "Association_football", "Cat",
            "India", "YouTube", "World_War_II", "Chess",
            "Taylor_Swift", "The_Beatles", "Elizabeth_II", "Solar_System"]

names = set(TARGETS) | set(CONTROLS)
by = aggregate((e for m in MONTHS for e in read_edit_events(Path("out/enwiki")/m)), names)

hit = 0
print("=== 대상 ===")
for t in TARGETS:
    obs = by.get(canonical_title(t), [])
    if not obs:
        print(f"  {t:46s} 관측 없음"); continue
    res = replay_title(obs)
    spikes = [r for r in res if r.decision.is_spike]
    first = first_detection(res)
    if spikes: hit += 1
    print(f"  {t:46s} 윈도우 {len(res):5d} 급증 {len(spikes):4d} "
          f"최초 {first.window_start if first else '-'}")
print(f"\n재현율 {hit}/{len(TARGETS)}")

fp_total = 0; fp_pages = 0
print("\n=== 대조군 ===")
for t in CONTROLS:
    obs = by.get(canonical_title(t), [])
    res = replay_title(obs) if obs else []
    spikes = [r for r in res if r.decision.is_spike]
    if spikes: fp_pages += 1
    fp_total += len(spikes)
    print(f"  {t:46s} 윈도우 {len(res):5d} 오탐 {len(spikes):4d}")
print(f"\n대조군 오탐 {fp_total}건 · {fp_pages}/{len(CONTROLS)} 문서")
