package io.wikipulse.backend.issue.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 이슈 상세의 멤버 문서. API 명세 v0.3 §2 `GET /issues/{id}`.
 *
 * <p>weight 내림차순. isSeed=false 는 급증을 직접 통과하지 않고 Clickstream·
 * Wikidata 관계로 딸려온 문서다 — 화면에서 구분해 보여주게 내보낸다.
 * editCount·views 는 아직 안 채워졌으면 null.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record IssueMemberResponse(
        long pageId,
        String wiki,
        String title,
        double weight,
        boolean isSeed,
        Integer editCount,
        Integer views) {

    public interface Projection {
        long getPageId();
        String getWiki();
        String getTitle();
        double getWeight();
        boolean getIsSeed();
        Integer getEditCount();
        Integer getViews();
    }

    public static IssueMemberResponse from(Projection p) {
        return new IssueMemberResponse(
                p.getPageId(), p.getWiki(), p.getTitle(), p.getWeight(),
                p.getIsSeed(), p.getEditCount(), p.getViews());
    }
}
