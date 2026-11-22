import { expect, test, type Page, type Route } from "@playwright/test";

function wavBytes(): Buffer {
  const samples = 4000;
  const data = Buffer.alloc(44 + samples * 2);
  data.write("RIFF", 0);
  data.writeUInt32LE(36 + samples * 2, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(8000, 24);
  data.writeUInt32LE(16000, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(samples * 2, 40);
  return data;
}

function listeningQuestion(number: number) {
  return {
    question_id: `listen-${number}`,
    level: "A1",
    script: "Sophie : Le café coûte deux dollars à Montréal.\nMarc : D'accord, je prends le café.\nSophie : Il est près de la porte.",
    audio_url: null,
    question: `Combien coûte le café ? (${number})`,
    options: ["A. Un dollar", "B. Deux dollars", "C. Trois dollars", "D. Quatre dollars"],
    correct_answer: "B",
    explanation: "Le café coûte deux dollars.",
    format_type: "un échange très court",
    speakers: ["Sophie", "Marc"],
  };
}

function readingQuestion(number: number) {
  return {
    question_number: number,
    text: "La clinique de Montréal ouvre à neuf heures.",
    question: `À quelle heure ouvre la clinique ? (${number})`,
    options: ["A. À huit heures", "B. À neuf heures", "C. À dix heures", "D. À midi"],
    correct_answer: "B",
    explanation: "Le texte dit neuf heures.",
    question_type: "reading_a1",
  };
}

async function mockListening(page: Page, audio: "ok" | "hang" | "fail-then-ok") {
  let audioCalls = 0;
  await page.route("**/tcf/generate-listening-question", async (route: Route) => {
    const body = route.request().postDataJSON() as { question_number?: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(listeningQuestion(body.question_number ?? 1)),
    });
  });
  await page.route("**/tcf/generate-listening-audio", async (route: Route) => {
    audioCalls += 1;
    if (audio === "hang") {
      await new Promise((resolve) => setTimeout(resolve, 60_000));
      return;
    }
    if (audio === "fail-then-ok" && audioCalls === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "The audio could not be generated right now. Please try again." }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ audio_url: "/audio/e2e.wav", status: "ready", voices: [] }),
    });
  });
  await page.route("**/audio/e2e.wav", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "audio/wav", body: wavBytes() });
  });
  await page.route("**/tcf/submit-listening-exam", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ score: 1, total: 1, accuracy: 100, completion_time: 5 }),
    });
  });
}

test("listening opens on Practice, not the mock exam", async ({ page }) => {
  await page.goto("/tcf/listening-exam");
  await expect(page.getByRole("tab", { name: "Practice" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Listening Practice" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Listening Mock Exam" })).toHaveCount(0);
});

test("listening mock exam reaches a results screen and counts only opened questions", async ({ page }) => {
  await mockListening(page, "ok");
  await page.goto("/tcf/listening-exam?mode=exam");
  await page.getByRole("tab", { name: "Mock Exam" }).click();
  await page.getByRole("button", { name: "Start Exam" }).click();
  await expect(page.getByText("Combien coûte le café ? (1)")).toBeVisible();
  await expect(page.getByText("Starts when the first question is ready")).toHaveCount(0);

  await page.getByText("Deux dollars").click();
  await page.getByRole("button", { name: "Submit Exam" }).click();
  const note = page.getByText("You opened 1 of 39 questions.");
  await expect(note).toHaveCount(1);
  await page.getByRole("button", { name: "Submit anyway" }).click();

  await expect(page.getByRole("heading", { name: "You scored 1 / 1" })).toBeVisible();
  await expect(page.getByText("NCLC: not assigned.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Question review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit Exam" })).toHaveCount(0);
});

test("a failed audio load does not use up the only play and does not spin forever", async ({ page }) => {
  await mockListening(page, "fail-then-ok");
  await page.goto("/tcf/listening-exam?mode=exam");
  await page.getByRole("tab", { name: "Mock Exam" }).click();
  await page.getByRole("button", { name: "Start Exam" }).click();
  await expect(page.getByText("Combien coûte le café ? (1)")).toBeVisible();
  await page.getByRole("button", { name: "Play (1 left)" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Limit reached")).toHaveCount(0);
});

test("audio that never arrives stops loading and keeps the play", async ({ page }) => {
  test.setTimeout(45_000);
  await mockListening(page, "hang");
  await page.goto("/tcf/listening-exam?mode=exam");
  await page.getByRole("tab", { name: "Mock Exam" }).click();
  await page.getByRole("button", { name: "Start Exam" }).click();
  await expect(page.getByText("Combien coûte le café ? (1)")).toBeVisible();
  await page.getByRole("button", { name: "Play (1 left)" }).click();
  await expect(page.getByText("Loading audio…")).toBeVisible();
  await expect(page.getByText("The audio is not available right now.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Play (1 left)" })).toBeVisible();
});

test("reading mock exam submit replaces the paper with results", async ({ page }) => {
  await page.route("**/tcf/generate-question", async (route: Route) => {
    const body = route.request().postDataJSON() as { question_number?: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(readingQuestion(body.question_number ?? 1)),
    });
  });
  await page.route("**/tcf/submit-exam", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        score: 1,
        total: 1,
        accuracy: 100,
        completion_time: 4,
        results: [{
          question_number: 1,
          correct_answer: "B",
          user_answer: "B",
          is_correct: true,
          explanation: "Le texte dit neuf heures.",
          question_type: "reading_a1",
        }],
      }),
    });
  });
  await page.goto("/tcf/mock-exam");
  await page.getByRole("button", { name: "Start Exam" }).click();
  await expect(page.getByText("À quelle heure ouvre la clinique ? (1)")).toBeVisible();
  await page.getByText("À neuf heures", { exact: true }).click();
  await page.getByRole("button", { name: "Submit Exam" }).click();
  await expect(page.getByText("You opened 1 of 39 questions.")).toHaveCount(1);
  await page.getByRole("button", { name: "Submit anyway" }).click();
  await expect(page.getByRole("heading", { name: "You scored 1 / 1" })).toBeVisible();
  await expect(page.getByText("NCLC: not assigned.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit Exam" })).toHaveCount(0);
});
