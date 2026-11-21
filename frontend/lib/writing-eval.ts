import type { TcfWritingEvaluationResponse } from "@/types/tcf-writing";

export type ScoreKey = keyof TcfWritingEvaluationResponse["scores"];

/** An evaluation as it streams in: any field may still be missing. */
export interface PartialWritingEvaluation {
  level: string | null;
  scores: Record<ScoreKey, number | null>;
  feedback: string[];
  improved_version: string;
}

const SCORE_LABELS: Record<string, ScoreKey> = {
  STRUCTURE: "structure",
  GRAMMAIRE: "grammar",
  COHERENCE: "coherence",
  VOCABULAIRE: "vocab",
};

const stripAccentsUpper = (value: string) => value.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();

const splitFeedback = (lines: string[]) =>
  lines.map((line) => line.replace(/^\s*(?:[-•*–—]|\d{1,2}[.)])\s+/, "").trim()).filter(Boolean);

/** Mirrors backend parse_writing_evaluation_text so the card fills in while the model is still writing. */
export function parsePartialEvaluation(text: string): PartialWritingEvaluation {
  const result: PartialWritingEvaluation = {
    level: null,
    scores: { structure: null, grammar: null, coherence: null, vocab: null },
    feedback: [],
    improved_version: "",
  };
  const feedbackLines: string[] = [];
  const improvedLines: string[] = [];
  let section: "" | "feedback" | "improved" = "";
  const lines = text.split("\n");
  // The last line may still be mid-token: only trust it inside free-text sections.
  lines.forEach((line, index) => {
    const isLast = index === lines.length - 1;
    if (section === "improved") {
      improvedLines.push(line);
      return;
    }
    const header = /^([A-Z ]+?)\s*:\s*(.*)$/.exec(stripAccentsUpper(line.trim()));
    if (header) {
      const name = header[1].trim();
      const rest = header[2].trim();
      if (name === "NIVEAU") {
        const level = /\b(A1|A2|B1|B2|C1|C2)\b/.exec(rest);
        if (level && !isLast) result.level = level[1];
        section = "";
        return;
      }
      if (SCORE_LABELS[name]) {
        const value = /\d+/.exec(rest);
        if (value && !isLast) result.scores[SCORE_LABELS[name]] = Math.max(0, Math.min(10, Number(value[0])));
        section = "";
        return;
      }
      if (name.startsWith("POINTS")) {
        section = "feedback";
        return;
      }
      if (name.startsWith("VERSION AMELIOREE")) {
        section = "improved";
        const original = line.includes(":") ? line.slice(line.indexOf(":") + 1).trim() : "";
        if (original) improvedLines.push(original);
        return;
      }
    }
    if (section === "feedback") feedbackLines.push(line);
  });
  result.feedback = splitFeedback(feedbackLines);
  result.improved_version = improvedLines.join("\n").trim();
  return result;
}

export function toPartial(evaluation: TcfWritingEvaluationResponse): PartialWritingEvaluation {
  return { ...evaluation, level: evaluation.level, scores: { ...evaluation.scores } };
}

/** Step feedback streams as "- point" lines then "VERSION AMELIOREE:" and the improved text. */
export function parseStepFeedback(text: string): { feedback: string[]; improved_version: string } {
  const parts = text.split(/^\s*VERSION\s+AM[ÉE]LIOR[ÉE]E\s*:\s*/im);
  return {
    feedback: splitFeedback(parts[0].split("\n")),
    improved_version: (parts[1] ?? "").trim(),
  };
}
