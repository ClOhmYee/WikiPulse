import test from "node:test";
import assert from "node:assert/strict";
import { reportView } from "../src/components/event/reportView.js";

const articles = [
  { id: "1", title: "2026 FIFA World Cup" },
  { id: "2", title: "Rodri" },
  { id: "3", title: "Pedri" },
];

test("섹션이 하나면 기사형 문단이다 (-188 예시 리포트)", () => {
  const view = reportView(
    {
      sections: [
        { id: "article", title: "x", body: "첫 문단\n\n둘째 문단", evidenceIds: ["1", "2"] },
      ],
    },
    articles,
  );
  assert.equal(view.layout, "article");
  assert.deepEqual(view.paragraphs, ["첫 문단", "둘째 문단"]);
  assert.equal(view.evidence.length, 2);
});

test("섹션이 여럿이면 카드이고 카드마다 자기 근거만 갖는다 (-223 AI 리포트)", () => {
  const view = reportView(
    {
      sections: [
        { id: "overview", title: "이슈 개요", body: "개요", evidenceIds: ["1"] },
        { id: "documents", title: "함께 움직인 문서", body: "문서", evidenceIds: ["2", "3", "2"] },
        { id: "stocks", title: "관련 종목", body: "종목", evidenceIds: [] },
      ],
    },
    articles,
  );
  assert.equal(view.layout, "cards");
  assert.deepEqual(
    view.cards.map((card) => [card.id, card.title, card.evidence.map((a) => a.id)]),
    [
      ["overview", "이슈 개요", ["1"]],
      ["documents", "함께 움직인 문서", ["2", "3"]],
      ["stocks", "관련 종목", []],
    ],
  );
  // 아래 "참고 문서" 전체 목록은 섹션을 가로질러 중복 없이 모은다.
  assert.deepEqual(view.evidence.map((a) => a.id), ["1", "2", "3"]);
});

test("본문 없는 섹션은 빼고, 멤버가 아닌 근거 id 는 버린다", () => {
  const view = reportView(
    {
      sections: [
        { id: "overview", title: "개요", body: "  ", evidenceIds: ["1"] },
        { id: "signal", title: "신호", body: "신호", evidenceIds: ["999", 2] },
      ],
    },
    articles,
  );
  assert.equal(view.layout, "article");
  assert.deepEqual(view.cards.map((card) => card.id), ["signal"]);
  assert.deepEqual(view.evidence.map((a) => a.id), ["2"]);
});

test("리포트가 없으면 빈 화면 자료다", () => {
  const view = reportView(null, articles);
  assert.equal(view.layout, "article");
  assert.deepEqual(view.paragraphs, []);
  assert.deepEqual(view.evidence, []);
});
