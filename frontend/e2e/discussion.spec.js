import { test, expect } from "@playwright/test";
import { issueId } from "../src/data/mock/identity.js";

const EVENT = "iran-hormuz-2025";
const OTHER_EVENT = "ai-chip-controls";
const regionName = "이 사건에 대한 토론";

test.beforeEach(async ({ page }) => {
  page.__discussionErrors = [];
  page.on("pageerror", (error) => page.__discussionErrors.push(error.message));
});

test.afterEach(async ({ page }) => {
  expect(
    page.__discussionErrors,
    "Discussion interactions should not throw",
  ).toEqual([]);
});

async function openDiscussion(page, eventId = EVENT) {
  await page.goto(`/#/issues/${eventId}`);
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "토론", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  const board = page.getByRole("region", { name: regionName });
  await expect(board).toBeVisible();
  return board;
}

async function postThread(board, body) {
  await board
    .getByRole("textbox", { name: "내 의견 작성", exact: true })
    .fill(body);
  await board.getByRole("button", { name: "토론 등록", exact: true }).click();
  return board
    .locator(".dc-thread")
    .filter({ has: board.page().getByText(body.trim(), { exact: true }) });
}

test("report overview contains three example discussions, and the top CTA opens the discussion tab", async ({
  page,
}) => {
  await page.goto(`/#/issues/${EVENT}`);
  const overviewBoard = page.getByRole("region", { name: regionName });
  await expect(overviewBoard.locator(".dc-thread")).toHaveCount(3);
  await expect(overviewBoard).toContainText(
    "다른 사용자에게 전송되지 않습니다",
  );
  await expect(overviewBoard.locator(".dc-thread").first()).toContainText(
    "리서처 A",
  );
  await expect(
    overviewBoard
      .locator(".dc-thread")
      .first()
      .getByRole("button", { name: "답글 1", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "토론", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", { name: regionName })).toHaveCount(1);
  await expect(
    page.getByRole("region", { name: regionName }).locator(".dc-thread"),
  ).toHaveCount(3);
  await expect(page.getByRole("main")).toHaveCount(1);
});

test("composer rejects whitespace, enforces its length limit, trims a post and keeps markup literal and local", async ({
  page,
}) => {
  const board = await openDiscussion(page);
  const composer = board.getByRole("textbox", {
    name: "내 의견 작성",
    exact: true,
  });
  const submit = board.getByRole("button", { name: "토론 등록", exact: true });
  await expect(composer).toHaveAttribute("maxlength", "1000");
  await expect(submit).toBeDisabled();
  await composer.fill(" \n\t ");
  await expect(submit).toBeDisabled();
  await expect(board.locator(".dc-thread")).toHaveCount(3);
  const requests = [];
  page.on("request", (request) => {
    if (
      ["fetch", "xhr"].includes(request.resourceType()) ||
      /\/api\//.test(request.url())
    )
      requests.push(request.url());
  });
  const body = "참고: <b>원문 링크</b>도 확인하고 싶어요.";
  const own = await postThread(board, `  ${body}  \n`);
  await expect(board.locator(".dc-thread")).toHaveCount(4);
  await expect(
    board.locator(".dc-thread").first().locator(":scope > .dc-body"),
  ).toHaveText(body);
  await expect(own).toContainText("나 (이 브라우저)");
  await expect(own.locator(".dc-body b")).toHaveCount(0);
  await expect(composer).toHaveValue("");
  await expect(board.getByRole("status")).toContainText(
    "이 브라우저에서만 볼 수 있어요",
  );
  expect(requests, "Posting must not contact a backend").toEqual([]);
});

test("popular sorting changes order and liking is reversible without losing the selected sort", async ({
  page,
}) => {
  const board = await openDiscussion(page);
  const body = "최신순과 공감순에서 이 의견의 위치를 확인합니다.";
  await postThread(board, body);
  await expect(board.locator(".dc-thread").first()).toContainText(body);
  await board
    .getByRole("combobox", { name: "토론 정렬" })
    .selectOption("popular");
  const popular = board.locator(".dc-thread").first();
  await expect(popular).toContainText("리서처 A");
  await popular
    .getByRole("button", { name: "리서처 A의 토론 공감 4개", exact: true })
    .click();
  await expect(
    popular.getByRole("button", {
      name: "리서처 A의 토론 공감 5개",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(board.getByRole("combobox", { name: "토론 정렬" })).toHaveValue(
    "popular",
  );
  await popular
    .getByRole("button", { name: "리서처 A의 토론 공감 5개", exact: true })
    .click();
  await expect(
    popular.getByRole("button", {
      name: "리서처 A의 토론 공감 4개",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "false");
  await board
    .getByRole("combobox", { name: "토론 정렬" })
    .selectOption("latest");
  await expect(board.locator(".dc-thread").first()).toContainText(body);
});

test("replies can be added, collapsed and restored after tab remount and reload, isolated by event", async ({
  page,
}) => {
  let board = await openDiscussion(page);
  const body = "호르무즈 사건에만 남기는 내 토론입니다.";
  const reply = "이 의견의 근거를 편집 내역에서 함께 확인해 볼게요.";
  let own = await postThread(board, body);
  await own
    .getByRole("button", {
      name: "나 (이 브라우저)의 토론 공감 0개",
      exact: true,
    })
    .click();
  await own.getByRole("button", { name: "답글 0", exact: true }).click();
  await expect(
    own.getByRole("button", { name: "답글 등록", exact: true }),
  ).toBeDisabled();
  const replyComposer = own.getByRole("textbox", {
    name: "나 (이 브라우저)에게 답글 작성",
    exact: true,
  });
  await replyComposer.fill("  ");
  await expect(
    own.getByRole("button", { name: "답글 등록", exact: true }),
  ).toBeDisabled();
  await replyComposer.fill(`  ${reply}  `);
  await own.getByRole("button", { name: "답글 등록", exact: true }).click();
  await expect(own.locator(".dc-reply .dc-body")).toHaveText(reply);
  await expect(replyComposer).toHaveValue("");
  await own.getByRole("button", { name: "답글 1", exact: true }).click();
  await expect(own.locator(".dc-replies")).toBeHidden();
  await own.getByRole("button", { name: "답글 1", exact: true }).click();
  await expect(own.locator(".dc-reply .dc-body")).toBeVisible();
  await page.getByRole("tab", { name: "관련 소식", exact: true }).click();
  await page.getByRole("tab", { name: "토론", exact: true }).click();
  board = page.getByRole("region", { name: regionName });
  own = board
    .locator(".dc-thread")
    .filter({ has: page.getByText(body, { exact: true }) });
  await expect(own).toBeVisible();
  await expect(
    own.getByRole("button", {
      name: "나 (이 브라우저)의 토론 공감 1개",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  board = page.getByRole("region", { name: regionName });
  own = board
    .locator(".dc-thread")
    .filter({ has: page.getByText(body, { exact: true }) });
  await own.getByRole("button", { name: "답글 1", exact: true }).click();
  await expect(own.locator(".dc-reply .dc-body")).toHaveText(reply);
  await expect(
    own.getByRole("button", {
      name: "나 (이 브라우저)의 토론 공감 1개",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  const other = await openDiscussion(page, OTHER_EVENT);
  await expect(other.locator(".dc-thread")).toHaveCount(3);
  await expect(other.getByText(body, { exact: true })).toHaveCount(0);
  await expect(other.getByText(reply, { exact: true })).toHaveCount(0);
});

test("blocked storage warns while a submitted thread remains usable across report tabs", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = function () {
      throw new DOMException("Unavailable storage", "QuotaExceededError");
    };
  });
  let board = await openDiscussion(page);
  const body = "저장 공간이 없어도 현재 세션에서 이어갈 토론입니다.";
  await postThread(board, body);
  await expect(board.getByRole("status")).toContainText(
    "브라우저 저장 공간을 사용할 수 없어 새로고침하면 사라집니다",
  );
  await page.getByRole("tab", { name: "이벤트 개요", exact: true }).click();
  board = page.getByRole("region", { name: regionName });
  await expect(board.getByText(body, { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "토론", exact: true }).click();
  board = page.getByRole("region", { name: regionName });
  const own = board
    .locator(".dc-thread")
    .filter({ has: page.getByText(body, { exact: true }) });
  await own
    .getByRole("button", {
      name: "나 (이 브라우저)의 토론 공감 0개",
      exact: true,
    })
    .click();
  await expect(
    own.getByRole("button", {
      name: "나 (이 브라우저)의 토론 공감 1개",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("390px report exposes related stocks at the top and discussion remains within the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/#/issues/${EVENT}`);
  const stocks = page
    .locator(".dt-report-actions")
    .getByRole("link", { name: /^연관 주식/ });
  await expect(stocks).toBeInViewport();
  await expect(stocks).toHaveAttribute(
    "href",
    `#/issues/${issueId(EVENT)}/stocks`,
  );
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  const board = page.getByRole("region", { name: regionName });
  const own = await postThread(
    board,
    `모바일에서도 긴 문장이 읽혀야 합니다. ${"공급망과편집근거".repeat(35)}`,
  );
  await expect(own).toBeVisible();
  await own.getByRole("button", { name: "답글 0", exact: true }).click();
  await expect(
    own.getByRole("textbox", {
      name: "나 (이 브라우저)에게 답글 작성",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(1);
  const composerWidth = await board
    .getByRole("textbox", { name: "내 의견 작성", exact: true })
    .boundingBox();
  expect(composerWidth.width).toBeLessThanOrEqual(390);
  await stocks.click();
  await expect(page).toHaveURL(
    new RegExp(`#\/issues\/${issueId(EVENT)}\/stocks$`),
  );
  await expect(
    page.getByRole("heading", { name: "이 사건과 연결된 종목", exact: true }),
  ).toBeVisible();
});
