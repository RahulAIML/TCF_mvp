import { expect, test } from "@playwright/test";

test("home listening and reading cards open practice", async ({ page }) => {
  await page.goto("/tcf");
  await expect(page.locator('a[href="/tcf/listening-exam?mode=practice"]').first()).toBeVisible();
  await expect(page.locator('a[href="/tcf/reading-practice"]').first()).toBeVisible();
});

test("pronunciation shows sample words even when the prompt API fails", async ({ page }) => {
  await page.route("**/api/pronunciation/prompts", (route) => route.abort());
  await page.goto("/tcf/pronunciation");
  await expect(page.getByRole("button", { name: /Bonjour/ })).toBeVisible();
  await expect(page.getByText("Showing saved sample words.")).toBeVisible();
});

test("a listening transcript puts each speaker on their own line", async ({ page }) => {
  await page.route("**/tcf/generate-listening-question", async (route) => {
    await route.fulfill({
      json: {
        question_id: "line-1",
        level: "A1",
        script: "Sophie : Bonjour à Montréal.\nMarc : Bonjour, le café est prêt.",
        audio_url: null,
        question: "Où sommes-nous ?",
        options: ["A. Paris", "B. Montréal", "C. Lyon", "D. Nice"],
        correct_answer: "B",
        explanation: "Ils sont à Montréal.",
        speakers: ["Sophie", "Marc"],
      },
    });
  });
  await page.goto("/tcf/listening-exam?mode=practice");
  await page.getByRole("button", { name: "Start Practice" }).click();
  await page.getByRole("button", { name: "Show Transcript" }).click();
  const html = await page.locator("div.max-h-48").innerHTML();
  expect(html).toContain("<br");
  await expect(page.getByText("Sophie").first()).toBeVisible();
  await expect(page.getByText("Marc").first()).toBeVisible();
});
