# WikiPulse — Team 926 (WikiPulse)

팀 프로젝트 WikiPulse 팀의 repository입니다.

위키피디아 편집 활동에서 실시간으로 급증 신호를 포착하고, 노이즈가 아닌 실제 화제성 이슈인지 검증한 뒤, 연관된 미국 상장 종목을 자동 매칭해 이슈 피드로 제공합니다.

## 링크

| 항목 | 주소 |
| --- | --- |
| Jira 보드 | https://github.com/ClOhmYee/WikiPulse |
| GitLab | https://github.com/ClOhmYee/WikiPulse |

## 브랜치 모델

git-flow를 사용합니다. 기본 브랜치는 `develop`이며, 모든 feature 브랜치는 develop에서 분기해 develop으로 병합합니다.

```
master   배포용. 스프린트 종료 시 release 머지로만 갱신
develop  통합 브랜치 (기본 브랜치)
feature/{이슈키}-{설명}
release/sprint-{N}
hotfix/{이슈키}-{설명}
```

브랜치·커밋·MR 컨벤션과 GitLab-Jira 연동 규칙은 `docs/team-conventions.md`를 참고하세요.
