package io.wikipulse.backend.issue.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 이슈 상세의 멤버 문서. API 명세 v0.3 §2 `GET /issues/{id}`.
 *
 * <p>weight 내림차순. isSeed=false 는 급증을 직접 통과하지 않고 Clickstream·
 * Wikidata 관계로 딸려온 문서다 — 화면에서 구분해 보여주게 내보낸다.
 *
 * <p>🔴 editCount·views 는 <b>그 스냅샷에서 판정에 쓴 고정값</b>이다 (WP-129 5번).
 * 최신 원시 테이블 값이 아니다 — 과거 시점을 열면 그때 값이 보여야 한다.
 * 안 채워졌으면 null 이고, 그 null 이 무슨 뜻인지는 completeness 가 말한다:
 * {@code complete}(판정 끝) / {@code pending}(입력 대기) / {@code unavailable}(원본 없음).
 *
 * <p>{@code titleKo} 는 표시 전용 ko.wikipedia 대응 제목이다(V20). ko 문서가 없으면 null 이고
 * (실측상 절반이 그렇다) 화면은 {@code title} 로 떨어진다. 🔴 {@code title}(영문)을 대체하지
 * 않는다 — Wikipedia 링크·식별자가 그걸 쓴다. 펄스맵 {@code PulseMap.Node} 와 같은 어휘다.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record IssueMemberResponse(
        long pageId,
        String wiki,
        String title,
        String titleKo,
        double weight,
        boolean isSeed,
        Integer editCount,
        Integer views,
        String completeness) {

    public interface Projection {
        long getPageId();
        String getWiki();
        String getTitle();
        String getTitleKo();
        double getWeight();
        boolean getIsSeed();
        Integer getEditCount();
        Integer getViews();
        String getCompleteness();
    }

    public static IssueMemberResponse from(Projection p) {
        return new IssueMemberResponse(
                p.getPageId(), p.getWiki(), p.getTitle(), p.getTitleKo(), p.getWeight(),
                p.getIsSeed(), p.getEditCount(), p.getViews(), p.getCompleteness());
    }
}
