"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SLOW_MESSAGE, useSlow } from "@/lib/slow-load";

import TcfAppShell from "@/components/TcfAppShell";
import WritingStepper, { WritingStep } from "@/components/WritingStepper";
import WritingEvaluationCard from "@/components/WritingEvaluationCard";
import WritingAssistantPanel from "@/components/WritingAssistantPanel";
import TimerClock from "@/components/TimerClock";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { generateTcfWritingTasks, saveTcfWritingProgress } from "@/services/api";
import { streamSSE } from "@/lib/sse";
import {
  parsePartialEvaluation,
  parseStepFeedback,
  toPartial,
  type PartialWritingEvaluation
} from "@/lib/writing-eval";
import type {
  TcfGenerateWritingTasksResponse,
  TcfWritingEvaluationResponse,
  TcfWritingMode,
  TcfWritingStepFeedbackResponse,
  TcfWritingTaskType
} from "@/types/tcf-writing";
import ExamResumeDialog from "@/components/ExamResumeDialog";
import {
  saveExamProgress,
  loadExamProgress,
  clearExamProgress,
  hasRecentProgress,
  type WritingProgressState,
} from "@/lib/exam-progress";

const EXAM_DURATION_SECONDS = 60 * 60;
const TASKS: TcfWritingTaskType[] = ["task1", "task2", "task3"];

// Official TCF Canada writing tasks (France Éducation international candidate manual).
const TASK_INFO: Record<TcfWritingTaskType, { title: string; min: number; max: number }> = {
  task1: { title: "Task 1 - Message", min: 60, max: 120 },
  task2: { title: "Task 2 - Article / Letter", min: 120, max: 150 },
  task3: { title: "Task 3 - Compare viewpoints & give your opinion", min: 120, max: 180 },
};

const TASK1_STEPS: WritingStep[] = [
  {
    key: "situation",
    title: "Greeting & purpose",
    description: "Greet the recipient(s) and say why you are writing.",
    helperPhrases: ["Bonjour Marie,", "Chers voisins,", "Je vous écris pour…", "Je t'écris pour…"],
    placeholder: "Saluez le destinataire et donnez la raison de votre message."
  },
  {
    key: "details",
    title: "Describe / explain",
    description: "Give the information the prompt asks for: what, where, when, why.",
    placeholder: "Décrivez ou expliquez avec des détails précis."
  },
  {
    key: "request",
    title: "Request or proposal",
    description: "Say clearly what you want, propose or expect.",
    helperPhrases: ["Pourriez-vous…", "Je souhaiterais…", "Est-ce que tu pourrais…"],
    placeholder: "Indiquez clairement votre demande ou proposition."
  },
  {
    key: "closing",
    title: "Closing",
    description: "Finish politely with a register that suits the recipient.",
    helperPhrases: ["Merci d'avance.", "Bien à vous,", "À bientôt !", "Cordialement,"],
    placeholder: "Ajoutez une formule de clôture adaptée."
  }
];

const TASK2_STEPS: WritingStep[] = [
  {
    key: "context",
    title: "Context",
    description: "Introduce the event or experience: what, where, when, who.",
    placeholder: "Présentez l'événement ou l'expérience."
  },
  {
    key: "account",
    title: "Account",
    description: "Tell what happened, in a logical order.",
    helperPhrases: ["D'abord,", "Ensuite,", "Puis,", "Finalement,"],
    placeholder: "Racontez ce qui s'est passé."
  },
  {
    key: "opinion",
    title: "Your opinion",
    description: "Give your opinion about it.",
    helperPhrases: ["À mon avis,", "Selon moi,", "Je trouve que…"],
    placeholder: "Donnez votre opinion."
  },
  {
    key: "arguments",
    title: "Arguments",
    description: "Justify your opinion with one or two reasons or examples.",
    helperPhrases: ["En effet,", "Par exemple,", "De plus,"],
    placeholder: "Justifiez avec des arguments et des exemples."
  },
  {
    key: "closing",
    title: "Conclusion",
    description: "Close the article or letter in one or two sentences.",
    placeholder: "Concluez brièvement."
  }
];

const TASK3_STEPS: WritingStep[] = [
  {
    key: "comparison",
    title: "Compare the two viewpoints",
    description: "In 40-60 words, summarise and compare the two documents in your own words.",
    helperPhrases: ["Le premier document affirme que…", "En revanche, le second…", "Alors que…, …"],
    placeholder: "Comparez les deux points de vue sans recopier."
  },
  {
    key: "position",
    title: "Your position",
    description: "State your own position clearly.",
    helperPhrases: ["Pour ma part,", "Je partage l'avis de…", "Je ne suis pas d'accord avec…"],
    placeholder: "Indiquez clairement votre position."
  },
  {
    key: "argument1",
    title: "Argument 1",
    description: "Give one reason with an example.",
    placeholder: "Argument 1 : idée + explication + exemple."
  },
  {
    key: "argument2",
    title: "Argument 2",
    description: "Give a second reason or answer an objection.",
    helperPhrases: ["De plus,", "Certes…, mais…", "Cependant,"],
    placeholder: "Argument 2 : idée + explication + exemple."
  },
  {
    key: "conclusion",
    title: "Conclusion",
    description: "Sum up your position.",
    helperPhrases: ["En conclusion,", "Pour conclure,"],
    placeholder: "Résumez votre position."
  }
];

const STEPS: Record<TcfWritingTaskType, WritingStep[]> = { task1: TASK1_STEPS, task2: TASK2_STEPS, task3: TASK3_STEPS };

type PerTask<T> = Record<TcfWritingTaskType, T>;
const perTask = <T,>(value: () => T): PerTask<T> => ({ task1: value(), task2: value(), task3: value() });

const buildSessionId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const wordCount = (text: string) => {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
};

const buildCombinedText = (steps: WritingStep[], values: Record<string, string>) =>
  steps
    .map((step) => values[step.key]?.trim())
    .filter(Boolean)
    .join("\n\n");

const emptyPartial = (): PartialWritingEvaluation => ({
  level: null,
  scores: { structure: null, grammar: null, coherence: null, vocab: null },
  feedback: [],
  improved_version: ""
});

const promptsOf = (tasks: TcfGenerateWritingTasksResponse): PerTask<string> => ({
  task1: tasks.task1_prompt,
  task2: tasks.task2_prompt,
  task3: tasks.task3_prompt,
});

function WordCount({ task, count }: { task: TcfWritingTaskType; count: number }) {
  const { min, max } = TASK_INFO[task];
  const tone = count === 0 ? "text-slate-500" : count < min ? "text-amber-600" : count > max ? "text-rose-600" : "text-emerald-600";
  return (
    <span className={`text-sm ${tone}`}>
      Words: {count} / {min}-{max}
    </span>
  );
}

/** Prompt text with "Document 1 : …" / "Document 2 : …" shown as separate blocks for Task 3. */
function TaskPrompt({ text }: { text: string }) {
  if (!text) return <p className="text-sm text-slate-400">Loading…</p>;
  const parts = text.split(/(?=Document\s+[12]\s*:)/);
  return (
    <div className="space-y-2 text-sm text-slate-600">
      {parts.map((part, i) =>
        /^Document\s+[12]/.test(part) ? (
          <blockquote key={i} className="rounded-lg border-l-4 border-indigo-200 bg-slate-50 px-3 py-2 whitespace-pre-line">
            {part.trim()}
          </blockquote>
        ) : (
          <p key={i} className="whitespace-pre-line">{part.trim()}</p>
        )
      )}
    </div>
  );
}

export default function WritingPage() {
  const [mode, setMode] = useState<TcfWritingMode | null>(null);
  const [isStarted, setIsStarted] = useState(false);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const promptsSlow = useSlow(loadingPrompts);
  const [error, setError] = useState("");
  const [prompts, setPrompts] = useState<PerTask<string>>(perTask(() => ""));
  const [stepIndex, setStepIndex] = useState<PerTask<number>>(perTask(() => 0));
  const [stepValues, setStepValues] = useState<PerTask<Record<string, string>>>(perTask(() => ({})));
  const [drafts, setDrafts] = useState<PerTask<string>>(perTask(() => ""));
  const [stepFeedback, setStepFeedback] = useState<PerTask<Record<string, TcfWritingStepFeedbackResponse>>>(perTask(() => ({})));
  const [stepFeedbackLoading, setStepFeedbackLoading] = useState<PerTask<boolean>>(perTask(() => false));
  const [evaluations, setEvaluations] = useState<PerTask<PartialWritingEvaluation | null>>(perTask(() => null));
  const [evalLoading, setEvalLoading] = useState<PerTask<boolean>>(perTask(() => false));
  const [finalEvaluation, setFinalEvaluation] = useState<PerTask<PartialWritingEvaluation | null> | null>(null);
  const [finalStreaming, setFinalStreaming] = useState<PerTask<boolean>>(perTask(() => false));
  const [finalErrors, setFinalErrors] = useState<PerTask<string>>(perTask(() => ""));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [timerKey, setTimerKey] = useState(0);
  const [timerActive, setTimerActive] = useState(false);
  const [examDuration, setExamDuration] = useState(EXAM_DURATION_SECONDS);
  const [examTask, setExamTask] = useState<TcfWritingTaskType>("task1");
  const [decompositionMode, setDecompositionMode] = useState(true);

  const [showResumeDialog, setShowResumeDialog] = useState(false);
  const [resumeSavedAt, setResumeSavedAt] = useState(0);

  const sessionIdRef = useRef<string | null>(null);
  const examStartedAtRef = useRef<number | null>(null);
  // Prompt sets are pre-generated server-side; one more is kept ready here so "New prompts" is instant.
  const browserSessionRef = useRef<string>(buildSessionId());
  const nextTasksRef = useRef<Promise<TcfGenerateWritingTasksResponse> | null>(null);

  const prefetchTasks = useCallback(() => {
    if (nextTasksRef.current) return;
    const request = generateTcfWritingTasks({ session_id: browserSessionRef.current });
    request.catch(() => {
      if (nextTasksRef.current === request) nextTasksRef.current = null;
    });
    nextTasksRef.current = request;
  }, []);

  const takeTasks = useCallback(async (): Promise<TcfGenerateWritingTasksResponse> => {
    const pending = nextTasksRef.current;
    nextTasksRef.current = null;
    let tasks: TcfGenerateWritingTasksResponse;
    if (pending) {
      try {
        tasks = await pending;
      } catch {
        tasks = await generateTcfWritingTasks({ session_id: browserSessionRef.current });
      }
    } else {
      tasks = await generateTcfWritingTasks({ session_id: browserSessionRef.current });
    }
    prefetchTasks();
    return tasks;
  }, [prefetchTasks]);

  useEffect(() => {
    prefetchTasks();
    if (hasRecentProgress("writing")) {
      const record = loadExamProgress<WritingProgressState>("writing");
      if (record) {
        setResumeSavedAt(record.savedAt);
        setShowResumeDialog(true);
      }
    }
  }, [prefetchTasks]);

  const combined = useMemo<PerTask<string>>(() => ({
    task1: buildCombinedText(TASK1_STEPS, stepValues.task1),
    task2: buildCombinedText(TASK2_STEPS, stepValues.task2),
    task3: buildCombinedText(TASK3_STEPS, stepValues.task3),
  }), [stepValues]);

  const textFor = useCallback(
    (task: TcfWritingTaskType) => (mode === "exam" ? drafts[task] : combined[task]),
    [mode, drafts, combined]
  );

  // Auto-save every 10 s: exam mode saves the free-text drafts, practice saves the steps.
  // The interval reads a ref so continuous typing does not keep postponing the save.
  const progressRef = useRef<WritingProgressState | null>(null);
  progressRef.current = mode
    ? {
        task1Text: textFor("task1"),
        task2Text: textFor("task2"),
        task3Text: textFor("task3"),
        currentTask: examTask === "task1" ? 1 : examTask === "task2" ? 2 : 3,
        sessionId: sessionIdRef.current,
        prompts: [prompts.task1, prompts.task2, prompts.task3],
        mode,
        examStartedAt: examStartedAtRef.current,
        stepValues: mode === "practice" ? [stepValues.task1, stepValues.task2, stepValues.task3] : undefined,
      }
    : null;

  useEffect(() => {
    if (!isStarted || !mode || finalEvaluation) return;
    const interval = setInterval(() => {
      if (progressRef.current && progressRef.current.prompts.every(Boolean)) {
        saveExamProgress<WritingProgressState>("writing", progressRef.current);
      }
    }, 10_000);
    return () => clearInterval(interval);
  }, [isStarted, mode, finalEvaluation]);

  const assistantContext = useMemo(() => {
    if (!mode) return "";
    if (mode === "exam") return prompts[examTask];
    return prompts.task1 || prompts.task2 || prompts.task3;
  }, [mode, examTask, prompts]);

  const assistantContextLabel = useMemo(() => {
    if (!mode) return "";
    if (mode === "exam") return examTask === "task1" ? "Task 1 Prompt" : examTask === "task2" ? "Task 2 Prompt" : "Task 3 Prompt";
    return "Task Prompt";
  }, [mode, examTask]);

  const assistantDraft = useMemo(() => {
    if (!mode) return "";
    if (mode === "exam") return drafts[examTask];
    return combined.task1 || combined.task2 || combined.task3;
  }, [mode, examTask, drafts, combined]);

  const resetState = useCallback(() => {
    setPrompts(perTask(() => ""));
    setStepIndex(perTask(() => 0));
    setStepValues(perTask(() => ({})));
    setDrafts(perTask(() => ""));
    setStepFeedback(perTask(() => ({})));
    setEvaluations(perTask(() => null));
    setFinalEvaluation(null);
    setFinalErrors(perTask(() => ""));
    setFinalStreaming(perTask(() => false));
    setError("");
    setExamTask("task1");
    setTimerActive(false);
    setExamDuration(EXAM_DURATION_SECONDS);
    examStartedAtRef.current = null;
  }, []);

  const startExamTimer = (startedAt: number) => {
    examStartedAtRef.current = startedAt;
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    setExamDuration(Math.max(0, EXAM_DURATION_SECONDS - elapsed));
    setTimerKey((prev) => prev + 1);
    setTimerActive(true);
  };

  const handleResumeWriting = () => {
    const record = loadExamProgress<WritingProgressState>("writing");
    if (!record) { setShowResumeDialog(false); return; }
    const { state } = record;
    const resumedMode: TcfWritingMode = state.mode ?? "exam";
    resetState();
    if (state.prompts?.length >= 3) {
      setPrompts({ task1: state.prompts[0], task2: state.prompts[1], task3: state.prompts[2] });
    }
    if (resumedMode === "practice" && state.stepValues?.length === 3) {
      setStepValues({ task1: state.stepValues[0], task2: state.stepValues[1], task3: state.stepValues[2] });
    } else {
      setDrafts({ task1: state.task1Text || "", task2: state.task2Text || "", task3: state.task3Text || "" });
    }
    setExamTask(state.currentTask === 1 ? "task1" : state.currentTask === 2 ? "task2" : "task3");
    sessionIdRef.current = state.sessionId ?? buildSessionId();
    setMode(resumedMode);
    setIsStarted(true);
    if (resumedMode === "exam") {
      startExamTimer(state.examStartedAt ?? Date.now());
    }
    setShowResumeDialog(false);
  };

  const handleStartNewWriting = () => {
    clearExamProgress("writing");
    setShowResumeDialog(false);
  };

  const startMode = async (targetMode: TcfWritingMode) => {
    clearExamProgress("writing");
    resetState();
    setMode(targetMode);
    setIsStarted(true);
    setLoadingPrompts(true);
    sessionIdRef.current = buildSessionId();

    try {
      setPrompts(promptsOf(await takeTasks()));
      if (targetMode === "exam") startExamTimer(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate writing prompts.");
      setIsStarted(false);
    } finally {
      setLoadingPrompts(false);
    }
  };

  const hasPracticeWork = TASKS.some((task) => combined[task].trim());

  const handleNewPrompts = async () => {
    if (hasPracticeWork && !window.confirm("Load new prompts? Your current practice answers will be cleared.")) return;
    setLoadingPrompts(true);
    setError("");
    try {
      const tasks = await takeTasks();
      setStepValues(perTask(() => ({})));
      setStepIndex(perTask(() => 0));
      setStepFeedback(perTask(() => ({})));
      setEvaluations(perTask(() => null));
      setFinalEvaluation(null);
      setFinalErrors(perTask(() => ""));
      setPrompts(promptsOf(tasks));
      sessionIdRef.current = buildSessionId();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate writing prompts.");
    } finally {
      setLoadingPrompts(false);
    }
  };

  const handleReset = () => {
    setMode(null);
    setIsStarted(false);
    resetState();
  };

  const requestStepFeedback = async (taskType: TcfWritingTaskType, step: WritingStep, text: string) => {
    if (!text.trim() || stepFeedbackLoading[taskType]) return;
    setError("");
    setStepFeedbackLoading((prev) => ({ ...prev, [taskType]: true }));
    const setFeedback = (value: TcfWritingStepFeedbackResponse | null) =>
      setStepFeedback((prev) => {
        const next = { ...prev[taskType] };
        if (value) next[step.key] = value;
        else delete next[step.key];
        return { ...prev, [taskType]: next };
      });

    let raw = "";
    let streamError = "";
    let received = false;
    try {
      await streamSSE(
        "/tcf/evaluate-writing-step/stream",
        { task_type: taskType, step: step.title, prompt: prompts[taskType], text },
        (event) => {
          if (typeof event.token === "string") {
            raw += event.token;
            received = true;
            setFeedback(parseStepFeedback(raw));
          } else if (event.feedback && typeof event.feedback === "object") {
            received = true;
            setFeedback(event.feedback as TcfWritingStepFeedbackResponse);
          } else if (typeof event.error === "string") {
            streamError = event.error;
          }
        }
      );
      if (!received) {
        setFeedback(null);
        setError(streamError || "Step feedback is unavailable right now. Please try again.");
      }
    } catch (err) {
      setFeedback(null);
      setError(err instanceof Error ? err.message : "Failed to get step feedback.");
    } finally {
      setStepFeedbackLoading((prev) => ({ ...prev, [taskType]: false }));
    }
  };

  const handleTaskStepChange = (taskType: TcfWritingTaskType, nextIndex: number) => {
    const currentIndex = stepIndex[taskType];
    if (nextIndex <= currentIndex || !decompositionMode) {
      setStepIndex((prev) => ({ ...prev, [taskType]: nextIndex }));
      return;
    }
    const currentStep = STEPS[taskType][currentIndex];
    const currentText = stepValues[taskType][currentStep.key] ?? "";
    if (!currentText.trim()) {
      setError("Please write something for the current step before moving on.");
      return;
    }
    setError("");
    // First "Next" streams feedback for this step; the next click moves on once the student has read it.
    if (!stepFeedback[taskType][currentStep.key]) {
      void requestStepFeedback(taskType, currentStep, currentText);
      return;
    }
    setStepIndex((prev) => ({ ...prev, [taskType]: nextIndex }));
  };

  /** Stream one task's evaluation into `apply`; resolves with the final evaluation or an error message. */
  const streamEvaluation = async (
    taskType: TcfWritingTaskType,
    responseText: string,
    apply: (value: PartialWritingEvaluation) => void
  ): Promise<{ evaluation: TcfWritingEvaluationResponse | null; error: string }> => {
    let raw = "";
    let evaluation: TcfWritingEvaluationResponse | null = null;
    let error = "";
    try {
      await streamSSE(
        "/tcf/evaluate-writing/stream",
        { task_type: taskType, prompt: prompts[taskType], response_text: responseText },
        (event) => {
          if (typeof event.token === "string") {
            raw += event.token;
            apply(parsePartialEvaluation(raw));
          } else if (event.evaluation && typeof event.evaluation === "object") {
            evaluation = event.evaluation as TcfWritingEvaluationResponse;
            apply(toPartial(evaluation));
          } else if (typeof event.error === "string") {
            error = event.error;
          }
        }
      );
    } catch (err) {
      error = err instanceof Error ? err.message : "Evaluation failed.";
    }
    if (!evaluation && !error) error = "The evaluation could not be completed. Please try again.";
    return { evaluation, error };
  };

  const handleEvaluateTask = async (taskType: TcfWritingTaskType) => {
    const responseText = combined[taskType];
    if (!responseText.trim() || evalLoading[taskType]) return;
    setError("");
    setEvalLoading((prev) => ({ ...prev, [taskType]: true }));
    setEvaluations((prev) => ({ ...prev, [taskType]: emptyPartial() }));
    const { evaluation, error: evalError } = await streamEvaluation(taskType, responseText, (value) =>
      setEvaluations((prev) => ({ ...prev, [taskType]: value }))
    );
    if (!evaluation) {
      setEvaluations((prev) => ({ ...prev, [taskType]: null }));
      setError(evalError);
    }
    setEvalLoading((prev) => ({ ...prev, [taskType]: false }));
  };

  const retryFinalTask = async (taskType: TcfWritingTaskType) => {
    setFinalErrors((prev) => ({ ...prev, [taskType]: "" }));
    setFinalStreaming((prev) => ({ ...prev, [taskType]: true }));
    setFinalEvaluation((prev) => (prev ? { ...prev, [taskType]: emptyPartial() } : prev));
    const { evaluation, error: evalError } = await streamEvaluation(taskType, textFor(taskType), (value) =>
      setFinalEvaluation((prev) => (prev ? { ...prev, [taskType]: value } : prev))
    );
    if (!evaluation) {
      setFinalErrors((prev) => ({ ...prev, [taskType]: evalError }));
      setFinalEvaluation((prev) => (prev ? { ...prev, [taskType]: null } : prev));
    }
    setFinalStreaming((prev) => ({ ...prev, [taskType]: false }));
  };

  const handleSubmitWriting = async (force = false) => {
    if (!mode || !isStarted || isSubmitting || finalEvaluation) return;
    if (!prompts.task1 || !prompts.task2 || !prompts.task3) {
      setError("Writing prompts are not ready yet.");
      return;
    }
    const texts = perTaskTexts();
    if (!force && TASKS.some((task) => !texts[task].trim())) {
      setError("Please complete all tasks before submitting.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setTimerActive(false);
    setFinalEvaluation(perTask(emptyPartial));
    setFinalErrors(perTask(() => ""));
    setFinalStreaming(perTask(() => true));

    const raw: PerTask<string> = perTask(() => "");
    let completed = 0;
    try {
      await streamSSE(
        "/tcf/writing/submit/stream",
        {
          session_id: sessionIdRef.current ?? buildSessionId(),
          mode,
          task1_prompt: prompts.task1,
          task2_prompt: prompts.task2,
          task3_prompt: prompts.task3,
          task1_text: texts.task1,
          task2_text: texts.task2,
          task3_text: texts.task3,
          task1_steps: mode === "practice" ? stepValues.task1 : undefined,
          task2_steps: mode === "practice" ? stepValues.task2 : undefined,
          task3_steps: mode === "practice" ? stepValues.task3 : undefined
        },
        (event) => {
          const task = event.task as TcfWritingTaskType | undefined;
          if (!task || !TASKS.includes(task)) return;
          if (typeof event.token === "string") {
            raw[task] += event.token;
            const partial = parsePartialEvaluation(raw[task]);
            setFinalEvaluation((prev) => (prev ? { ...prev, [task]: partial } : prev));
          } else if (event.evaluation && typeof event.evaluation === "object") {
            completed += 1;
            const finalValue = toPartial(event.evaluation as TcfWritingEvaluationResponse);
            setFinalEvaluation((prev) => (prev ? { ...prev, [task]: finalValue } : prev));
            setFinalStreaming((prev) => ({ ...prev, [task]: false }));
          } else if (typeof event.error === "string") {
            const message = event.error;
            setFinalErrors((prev) => ({ ...prev, [task]: message }));
            setFinalEvaluation((prev) => (prev ? { ...prev, [task]: null } : prev));
            setFinalStreaming((prev) => ({ ...prev, [task]: false }));
          }
        }
      );
      if (completed === TASKS.length) clearExamProgress("writing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit writing tasks.");
      setFinalEvaluation(null);
      if (mode === "exam" && examStartedAtRef.current) setTimerActive(true);
    } finally {
      setFinalStreaming(perTask(() => false));
      setIsSubmitting(false);
    }
  };

  function perTaskTexts(): PerTask<string> {
    return { task1: textFor("task1"), task2: textFor("task2"), task3: textFor("task3") };
  }

  const handleTimerExpire = () => {
    if (finalEvaluation || isSubmitting) return;
    void handleSubmitWriting(true);
  };

  // Persist practice steps / exam drafts to the server (debounced; only tasks that changed).
  const lastServerSaveRef = useRef<Partial<Record<TcfWritingTaskType, string>>>({});
  useEffect(() => {
    if (!isStarted || !mode || !sessionIdRef.current) return;
    const timeout = window.setTimeout(() => {
      for (const task of TASKS) {
        if (!prompts[task]) continue;
        const steps = mode === "practice" ? stepValues[task] : { draft: drafts[task] };
        const signature = `${sessionIdRef.current}|${prompts[task]}|${JSON.stringify(steps)}`;
        if (lastServerSaveRef.current[task] === signature) continue;
        lastServerSaveRef.current[task] = signature;
        void saveTcfWritingProgress({
          session_id: sessionIdRef.current as string,
          mode,
          task_type: task,
          steps,
          task_prompt: prompts[task]
        }).catch(() => undefined);
      }
    }, 1500);
    return () => window.clearTimeout(timeout);
  }, [stepValues, drafts, prompts, mode, isStarted]);

  const finalAllDone = Boolean(finalEvaluation) && !isSubmitting;
  const finalCards = finalEvaluation && (
    <div className="grid gap-6 lg:grid-cols-3">
      {TASKS.map((task, i) => {
        const value = finalEvaluation[task];
        if (finalErrors[task]) {
          return (
            <Card key={task} className="rounded-2xl border-rose-200 bg-rose-50 shadow-sm">
              <CardContent className="p-5 space-y-3 text-sm text-rose-700">
                <p className="font-semibold">Task {i + 1} evaluation</p>
                <p>{finalErrors[task]}</p>
                <Button variant="secondary" onClick={() => void retryFinalTask(task)}>Retry evaluation</Button>
              </CardContent>
            </Card>
          );
        }
        return value ? (
          <WritingEvaluationCard
            key={task}
            title={`Task ${i + 1} ${mode === "exam" ? "Evaluation" : "Final"}`}
            evaluation={value}
            streaming={finalStreaming[task]}
          />
        ) : null;
      })}
    </div>
  );

  const practiceHeader = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Practice Mode</h2>
        <p className="text-sm text-slate-500">
          Guided step-by-step writing with feedback after each part.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => void handleNewPrompts()} disabled={loadingPrompts || isSubmitting}>
          New prompts
        </Button>
        <Button variant="secondary" onClick={() => setDecompositionMode((prev) => !prev)}>
          Step feedback: {decompositionMode ? "On" : "Off"}
        </Button>
      </div>
    </div>
  );

  return (
    <TcfAppShell title="Writing Module" subtitle="Guided learning and exam simulation for TCF writing">
      {showResumeDialog && (
        <ExamResumeDialog
          moduleName="Writing"
          savedAt={resumeSavedAt}
          onResume={handleResumeWriting}
          onStartNew={handleStartNewWriting}
        />
      )}
      <div className="grid gap-6 lg:grid-cols-[2.2fr_1fr]">
        <div className="space-y-6 min-w-0">
          {!mode || !isStarted ? (
            <div className="grid gap-6 lg:grid-cols-2">
              {error && (
                <div className="lg:col-span-2 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
                  {error}
                </div>
              )}
              <Card className="border-slate-200 shadow-sm">
                <CardContent className="p-6 space-y-4">
                  <h2 className="text-2xl font-semibold text-slate-900">Practice Mode</h2>
                  <p className="text-sm text-slate-600">
                    Work through structured steps with guidance and feedback after each part.
                  </p>
                  <Button onClick={() => void startMode("practice")}>Start Practice</Button>
                </CardContent>
              </Card>
              <Card className="border-slate-200 shadow-sm">
                <CardContent className="p-6 space-y-4">
                  <h2 className="text-2xl font-semibold text-slate-900">Exam Mode</h2>
                  <p className="text-sm text-slate-600">
                    Simulate the full writing exam: three tasks in 60 minutes, as in the real TCF Canada.
                  </p>
                  <Button onClick={() => void startMode("exam")}>Start Exam</Button>
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900">TCF Writing Tasks</h2>
                  <p className="text-sm text-slate-500">
                    Task 1: message (60-120 words). Task 2: article or letter (120-150). Task 3: compare two viewpoints and give your opinion (120-180).
                  </p>
                </div>
                {mode === "exam" ? (
                  <TimerClock
                    durationSeconds={examDuration}
                    isActive={timerActive}
                    resetKey={timerKey}
                    onExpire={handleTimerExpire}
                  />
                ) : (
                  <Button variant="secondary" onClick={handleReset}>
                    Change Mode
                  </Button>
                )}
              </div>

              {error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
                  {error}
                </div>
              )}

              {loadingPrompts && (
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 flex flex-wrap items-center gap-3" role="status">
                  {promptsSlow ? (
                    <>
                      <span>{SLOW_MESSAGE}</span>
                      <Button size="sm" variant="outline" onClick={() => void startMode(mode)}>Retry</Button>
                    </>
                  ) : (
                    <>
                      <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping" aria-hidden />
                      Preparing your writing prompts…
                    </>
                  )}
                </div>
              )}

              {!loadingPrompts && mode === "practice" && (
                <div className="space-y-8">
                  {practiceHeader}

                  {TASKS.map((task, i) => (
                    <div key={task} className="space-y-6">
                      <Card className="border-slate-200 shadow-sm">
                        <CardHeader>
                          <CardTitle>{TASK_INFO[task].title}</CardTitle>
                          <TaskPrompt text={prompts[task]} />
                        </CardHeader>
                      </Card>

                      <WritingStepper
                        title={`Task ${i + 1} Step-by-step`}
                        steps={STEPS[task]}
                        currentStep={stepIndex[task]}
                        values={stepValues[task]}
                        onStepChange={(index) => handleTaskStepChange(task, index)}
                        onValueChange={(key, value) =>
                          setStepValues((prev) => ({ ...prev, [task]: { ...prev[task], [key]: value } }))
                        }
                        onRequestFeedback={(step, text) => void requestStepFeedback(task, step, text)}
                        feedback={stepFeedback[task]}
                        isFeedbackLoading={stepFeedbackLoading[task]}
                      />

                      <Card className="border-slate-200 shadow-sm">
                        <CardContent className="space-y-3 p-6">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <h3 className="text-lg font-semibold text-slate-900">Task {i + 1} Combined Draft</h3>
                            <WordCount task={task} count={wordCount(combined[task])} />
                          </div>
                          <p className="whitespace-pre-line text-sm text-slate-700">
                            {combined[task] || "Your combined draft will appear here."}
                          </p>
                          <Button
                            onClick={() => void handleEvaluateTask(task)}
                            disabled={evalLoading[task] || !combined[task].trim()}
                          >
                            {evalLoading[task] ? "Evaluating…" : `Evaluate Task ${i + 1}`}
                          </Button>
                        </CardContent>
                      </Card>

                      {evaluations[task] && (
                        <WritingEvaluationCard
                          title={`Task ${i + 1} Evaluation`}
                          evaluation={evaluations[task] as PartialWritingEvaluation}
                          streaming={evalLoading[task]}
                        />
                      )}
                    </div>
                  ))}

                  <div className="flex flex-wrap items-center gap-3">
                    <Button onClick={() => void handleSubmitWriting()} disabled={isSubmitting || Boolean(finalEvaluation)}>
                      {isSubmitting ? "Evaluating all tasks…" : "Submit All Tasks"}
                    </Button>
                    <Button variant="secondary" onClick={handleReset}>
                      Back to Mode Selection
                    </Button>
                  </div>

                  {finalCards}
                </div>
              )}

              {!loadingPrompts && mode === "exam" && (
                <div className="space-y-6">
                  <div className="flex flex-wrap gap-3">
                    {TASKS.map((task, i) => (
                      <Button
                        key={task}
                        variant={examTask === task ? "default" : "outline"}
                        onClick={() => setExamTask(task)}
                        disabled={Boolean(finalEvaluation)}
                      >
                        Task {i + 1}
                      </Button>
                    ))}
                  </div>

                  <Card className="border-slate-200 shadow-sm">
                    <CardContent className="p-6 space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="text-xl font-semibold text-slate-900">{TASK_INFO[examTask].title}</h3>
                        <span className="text-sm text-slate-500">
                          {TASK_INFO[examTask].min}-{TASK_INFO[examTask].max} words
                        </span>
                      </div>
                      <TaskPrompt text={prompts[examTask]} />
                      <textarea
                        className="min-h-[220px] w-full rounded-xl border border-slate-200 p-4 text-sm text-slate-800 shadow-sm focus:border-emerald-500 focus:outline-none"
                        placeholder="Write your response here..."
                        value={drafts[examTask]}
                        onChange={(event) => {
                          const value = event.target.value;
                          setDrafts((prev) => ({ ...prev, [examTask]: value }));
                        }}
                        disabled={Boolean(finalEvaluation)}
                      />
                      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
                        <WordCount task={examTask} count={wordCount(drafts[examTask])} />
                        <div className="flex gap-3">
                          {examTask !== "task1" && (
                            <Button
                              variant="secondary"
                              onClick={() => setExamTask(examTask === "task3" ? "task2" : "task1")}
                              disabled={Boolean(finalEvaluation)}
                            >
                              Back
                            </Button>
                          )}
                          {examTask === "task1" ? (
                            <Button onClick={() => setExamTask("task2")} disabled={Boolean(finalEvaluation)}>
                              Continue to Task 2
                            </Button>
                          ) : examTask === "task2" ? (
                            <Button onClick={() => setExamTask("task3")} disabled={Boolean(finalEvaluation)}>
                              Continue to Task 3
                            </Button>
                          ) : (
                            <Button onClick={() => void handleSubmitWriting()} disabled={isSubmitting || Boolean(finalEvaluation)}>
                              {isSubmitting ? "Evaluating…" : "Submit Exam"}
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  {finalEvaluation && (
                    <div className="space-y-4">
                      <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                        {finalAllDone ? "Exam submitted. Your results are below." : "Exam submitted. Your results are coming in…"}
                      </div>
                      {finalCards}
                      {finalAllDone && (
                        <Button variant="secondary" onClick={handleReset}>
                          Back to Mode Selection
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        <WritingAssistantPanel
          contextLabel={assistantContextLabel}
          contextText={assistantContext}
          draftText={assistantDraft}
        />
      </div>
    </TcfAppShell>
  );
}
