// 리포트 섹션을 화면 배치로 바꾼다 (WP-225).
//
// 섹션이 하나면 기사형 문단(-188), 둘 이상이면 섹션 카드다. 운영 AI 리포트(-223)는
// 개요·함께 움직인 문서·관측 신호·관련 종목 네 섹션으로 오고, 예시 리포트는 한 섹션에
// 문단 여러 개로 온다 — 둘을 같은 문단 나열로 보이면 섹션 제목과 섹션별 근거가 사라진다.

const splitParagraphs = (body) =>
  (body || "")
    .split(/\n\s*\n/)
    .map((text) => text.trim())
    .filter(Boolean);

export function reportView(report, articles = []) {
  const sections = (report?.sections || []).filter(
    (section) => splitParagraphs(section.body).length,
  );
  const articleById = new Map(
    articles.map((article) => [String(article.id), article]),
  );
  const evidenceOf = (ids) =>
    [...new Set((ids || []).map(String))]
      .map((id) => articleById.get(id))
      .filter(Boolean);

  return {
    layout: sections.length > 1 ? "cards" : "article",
    paragraphs: sections.flatMap((section) => splitParagraphs(section.body)),
    cards: sections.map((section) => ({
      id: section.id,
      title: section.title,
      paragraphs: splitParagraphs(section.body),
      evidence: evidenceOf(section.evidenceIds),
    })),
    evidence: evidenceOf(sections.flatMap((section) => section.evidenceIds || [])),
  };
}
