import { expect, test, type Page } from "@playwright/test";

function attach(page: Page): string[] {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror ${error.message}`));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (/favicon|Download the React DevTools/i.test(text)) return;
    problems.push(`console ${text}`);
  });
  page.on("response", (res) => {
    if (res.status() >= 500) problems.push(`${res.status()} ${res.url()}`);
  });
  page.on("requestfailed", (req) => {
    const text = req.failure()?.errorText ?? "";
    if (/CORS|ERR_FAILED|ERR_CONNECTION/i.test(text)) problems.push(`${text} ${req.url()}`);
  });
  return problems;
}

async function answerFirst(page: Page) {
  await page.locator("label").filter({ has: page.locator("input[type=radio]") }).first().click();
}

async function playListening(page: Page) {
  await page.getByRole("button", { name: /^Play/ }).first().click();
  await expect(page.getByRole("button", { name: /Loading audio/ })).toHaveCount(0, { timeout: 50_000 });
}

test.describe("live modules", () => {
  test("listening", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/listening-exam?mode=practice");
    await expect(page.getByRole("heading", { name: "Listening Practice" })).toBeVisible();
    for (let i = 0; i < 5; i++) {
      await page.getByRole("button", { name: i === 0 ? "Start Practice" : "Next Question" }).click();
      await expect(page.getByRole("button", { name: /^Play/ }).first()).toBeVisible({ timeout: 70_000 });
      await playListening(page);
      await page.getByRole("button", { name: "Show Transcript" }).click();
      await expect(page.locator("div.max-h-48")).toBeVisible();
      await answerFirst(page);
    }
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("reading", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/reading-practice");
    await page.getByRole("button", { name: "A1", exact: true }).click();
    for (let i = 0; i < 5; i++) {
      await expect(page.locator("label").filter({ has: page.locator("input[type=radio]") }).first()).toBeVisible({ timeout: 70_000 });
      await answerFirst(page);
      const check = page.getByRole("button", { name: "Check Answer" });
      if (await check.count()) await check.click();
      await page.getByRole("button", { name: "Next Question" }).click();
    }
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("writing", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/writing");
    await page.getByRole("button", { name: "Start Practice" }).click();
    await expect(page.getByText("Preparing your writing prompts…")).toHaveCount(0, { timeout: 70_000 });
    await expect(page.getByText("Task 1 - Message")).toBeVisible();
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("speaking", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/speaking");
    await page.getByRole("button", { name: "Task 1 — Interview" }).click();
    await page.getByRole("button", { name: "Start Practice" }).click();
    await expect(page.getByText(/Bonjour|je suis|examin/i).first()).toBeVisible({ timeout: 70_000 });
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("grammar", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/learn");
    await page.getByPlaceholder("Paste French text here... (article, passage, document)").fill(
      "Le marché de Montréal ouvre à huit heures. Les pommes coûtent deux dollars. Marie achète du pain et parle avec le vendeur.",
    );
    await page.getByRole("button", { name: "Analyze and Build Exercises" }).click();
    await expect(page.getByText("5 exercises ready")).toBeVisible({ timeout: 90_000 });
    await page.getByRole("button", { name: "Start Exercises" }).click();
    await expect(page.getByText(/Corrigez|Question|phrase/i).first()).toBeVisible();
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("vocab", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/vocabulary");
    await page.getByRole("button", { name: /A2 Elementary/ }).click();
    await page.getByRole("button", { name: "Start Vocabulary Session" }).click();
    await expect(page.getByRole("button", { name: "Change settings" })).toBeVisible({ timeout: 70_000 });
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("pronunciation", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/pronunciation");
    await expect(page.getByRole("button", { name: /Bonjour|Merci|Hello/ }).first()).toBeVisible({ timeout: 20_000 });
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("tts", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/tts");
    await expect(page.getByRole("button", { name: /French Male/ }).first()).toBeVisible({ timeout: 25_000 });
    await expect(page.getByText("Loading voices…")).toHaveCount(0);
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test("exam", async ({ page }) => {
    const problems = attach(page);
    await page.goto("/tcf/listening-exam?mode=exam");
    await page.getByRole("button", { name: "Start Exam" }).click();
    for (let i = 0; i < 5; i++) {
      await expect(page.getByRole("button", { name: /^Play/ }).first()).toBeVisible({ timeout: 70_000 });
      await answerFirst(page);
      if (i < 4) await page.getByRole("button", { name: String(i + 2), exact: true }).click();
    }
    expect(problems, problems.join("\n")).toEqual([]);
  });
});
