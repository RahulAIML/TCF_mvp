import { expect, test, type Page } from "@playwright/test";

type Watch = { problems: string[] };

function watch(page: Page): Watch {
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
  return { problems };
}

async function playListening(page: Page) {
  const play = page.getByRole("button", { name: /Play/ }).first();
  await play.click({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /Loading audio/ })).toHaveCount(0, { timeout: 45_000 });
}

test("live modules", async ({ page }) => {
  test.setTimeout(12 * 60_000);
  const seen = watch(page);
  const results: Record<string, string> = {};

  const run = async (name: string, body: () => Promise<string>) => {
    const before = seen.problems.length;
    try {
      const detail = await body();
      const fresh = seen.problems.slice(before);
      results[name] = fresh.length ? `FAIL ${detail} | ${fresh.join(" ; ")}` : `PASS ${detail}`;
    } catch (error) {
      results[name] = `FAIL ${error instanceof Error ? error.message : String(error)}`;
    }
  };

  await run("listening", async () => {
    await page.goto("/tcf/listening-exam?mode=practice");
    await expect(page.getByRole("heading", { name: "Listening Practice" })).toBeVisible();
    for (let i = 0; i < 5; i++) {
      await page.getByRole("button", { name: i === 0 ? "Start Practice" : "Next Question" }).click();
      await expect(page.getByRole("button", { name: /Play/ }).first()).toBeVisible({ timeout: 60_000 });
      await playListening(page);
      await page.getByRole("button", { name: "Show Transcript" }).click();
      await expect(page.locator("div.max-h-48")).toBeVisible();
      await page.getByRole("button", { name: /^B\./ }).click();
    }
    return "5 questions, audio started, transcript open";
  });

  await run("reading", async () => {
    await page.goto("/tcf/reading-practice");
    await page.getByRole("button", { name: "A1", exact: true }).click();
    for (let i = 0; i < 5; i++) {
      await expect(page.getByRole("button", { name: /^A\./ })).toBeVisible({ timeout: 60_000 });
      await page.getByRole("button", { name: /^A\./ }).click();
      const next = page.getByRole("button", { name: /Next/ });
      if (await next.count()) await next.first().click();
    }
    return "5 reading items answered";
  });

  await run("writing", async () => {
    await page.goto("/tcf/writing");
    await page.getByRole("button", { name: "Start Practice" }).click();
    await expect(page.getByText(/Tâche 1|Task 1/)).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("Preparing your writing prompts…")).toHaveCount(0);
    return "writing prompts visible";
  });

  await run("speaking", async () => {
    await page.goto("/tcf/speaking");
    await page.getByRole("button", { name: "Start Practice" }).click();
    await expect(page.getByText(/Bonjour|examinateur|je suis/i).first()).toBeVisible({ timeout: 60_000 });
    return "examiner opened the practice";
  });

  await run("grammar", async () => {
    await page.goto("/tcf/learn");
    await page.getByPlaceholder("Paste French text here... (article, passage, document)").fill(
      "Le marché de Montréal ouvre à huit heures. Les pommes coûtent deux dollars. Marie achète du pain et parle avec le vendeur.",
    );
    await page.getByRole("button", { name: "Analyze and Build Exercises" }).click();
    await expect(page.getByText(/Corrigez|exercice|Question/i).first()).toBeVisible({ timeout: 90_000 });
    return "learn built exercises, including grammar";
  });

  await run("vocab", async () => {
    await page.goto("/tcf/vocabulary");
    await page.getByRole("button", { name: "A2", exact: true }).click();
    await page.getByRole("button", { name: "Start Vocabulary Session" }).click();
    await expect(page.locator("body")).toContainText(/[A-Za-zÀ-ÿ]{3,}/, { timeout: 60_000 });
    return "vocabulary session started";
  });

  await run("pronunciation", async () => {
    await page.goto("/tcf/pronunciation");
    const words = page.getByRole("button").filter({ hasText: /Bonjour|Merci|Hello|café/i });
    await expect(words.first()).toBeVisible({ timeout: 20_000 });
    const count = await words.count();
    expect(count).toBeGreaterThan(0);
    return `${count} sample words visible`;
  });

  await run("tts", async () => {
    await page.goto("/tcf/tts");
    await expect(page.getByRole("button", { name: /French Male/ }).first()).toBeVisible({ timeout: 25_000 });
    await expect(page.getByText("Loading voices…")).toHaveCount(0);
    return "voices listed";
  });

  await run("exam", async () => {
    await page.goto("/tcf/listening-exam?mode=exam");
    await page.getByRole("button", { name: "Start Exam" }).click();
    for (let i = 0; i < 5; i++) {
      await expect(page.getByRole("button", { name: /Play/ }).first()).toBeVisible({ timeout: 60_000 });
      await page.getByRole("button", { name: /^A\./ }).click();
      const next = page.getByRole("button", { name: /Next/ });
      if (i < 4 && (await next.count())) await next.first().click();
    }
    return "5 exam questions opened";
  });

  console.log(JSON.stringify(results, null, 2));
  const failed = Object.entries(results).filter(([, value]) => value.startsWith("FAIL"));
  expect(failed, JSON.stringify(results, null, 2)).toEqual([]);
});
