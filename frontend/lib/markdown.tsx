import React from "react";

const SUBSCRIPT: Record<string, string> = {
  "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
  "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
};
const SUPERSCRIPT: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
  "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾", n: "ⁿ",
};
const SYMBOLS: Record<string, string> = {
  rightarrow: "→", to: "→", leftarrow: "←", leftrightarrow: "↔", Rightarrow: "⇒", cdot: "·", times: "×",
  div: "÷", pm: "±", leq: "≤", le: "≤", geq: "≥", ge: "≥", neq: "≠", approx: "≈", infty: "∞", degree: "°",
  circ: "°", alpha: "α", beta: "β", gamma: "γ", delta: "δ", Delta: "Δ", mu: "μ", pi: "π", sigma: "σ",
  lambda: "λ", theta: "θ", omega: "ω", Omega: "Ω",
};

const mapChars = (value: string, table: Record<string, string>) =>
  value.split("").map((c) => table[c] ?? c).join("");

/** Convert the inside of a LaTeX math span to readable Unicode (CO_2 → CO₂, \text{CO}_{2} → CO₂). */
function latexToUnicode(math: string): string {
  return math
    .replace(/\\(?:text|mathrm|mathbf|mathit|operatorname)\{([^}]*)\}/g, "$1")
    .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, "$1/$2")
    .replace(/\\sqrt\{([^}]*)\}/g, "√($1)")
    .replace(/_\{([^}]*)\}/g, (_m, sub: string) => mapChars(sub, SUBSCRIPT))
    .replace(/_([0-9+\-=()])/g, (_m, sub: string) => mapChars(sub, SUBSCRIPT))
    .replace(/\^\{([^}]*)\}/g, (_m, sup: string) => mapChars(sup, SUPERSCRIPT))
    .replace(/\^([0-9+\-=()n])/g, (_m, sup: string) => mapChars(sup, SUPERSCRIPT))
    .replace(/\\([A-Za-z]+)/g, (m, name: string) => SYMBOLS[name] ?? m.slice(1))
    .replace(/\\([%$&#_{}])/g, "$1")
    .replace(/[{}]/g, "");
}

/**
 * Strip LaTeX math delimiters the model may still emit, without touching money amounts.
 * A `$…$` span is treated as math only when it hugs its content (no inner edge spaces)
 * and contains a backslash, `_` or `^` — so "5 $ ou 10 $" is left alone.
 */
export function cleanLatex(text: string): string {
  return text
    .replace(/\$\$([\s\S]+?)\$\$/g, (m, inner: string) => (/[\\_^]/.test(inner) ? latexToUnicode(inner.trim()) : m))
    .replace(/\\\(([\s\S]+?)\\\)/g, (_m, inner: string) => latexToUnicode(inner))
    .replace(/\\\[([\s\S]+?)\\\]/g, (_m, inner: string) => latexToUnicode(inner))
    .replace(/\$(?!\s)([^$\n]*?[^\s$])\$/g, (m, inner: string) => (/[\\_^]/.test(inner) ? latexToUnicode(inner) : m));
}

const INLINE_RE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^\s*][^*\n]*?\*)/g;

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split(INLINE_RE).filter((part) => part !== "").map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if ((part.startsWith("**") && part.endsWith("**") && part.length > 4) || (part.startsWith("__") && part.endsWith("__") && part.length > 4)) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key} className="rounded bg-black/5 px-1 py-0.5 text-[0.92em]">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

/** Render the small Markdown subset the AI uses: headings, bold/italic/code, bullet and numbered lists. */
export function renderMarkdown(source: string): React.ReactNode {
  const lines = cleanLatex(source).split("\n");
  const nodes: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flush = () => {
    if (!list) return;
    const key = `list-${nodes.length}`;
    const items = list.items.map((item, i) => <li key={`${key}-${i}`}>{renderInline(item, `${key}-${i}`)}</li>);
    nodes.push(
      list.ordered ? (
        <ol key={key} className="my-1 ml-5 list-decimal space-y-0.5">{items}</ol>
      ) : (
        <ul key={key} className="my-1 ml-5 list-disc space-y-0.5">{items}</ul>
      )
    );
    list = null;
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(trimmed);
    const numbered = /^\d{1,2}[.)]\s+(.*)$/.exec(trimmed);
    if (bullet || numbered) {
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
      return;
    }
    flush();
    if (!trimmed) {
      if (nodes.length) nodes.push(<div key={`sp-${index}`} className="h-1.5" />);
      return;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      const size = heading[1].length <= 2 ? "text-[1.05em]" : "text-[1em]";
      nodes.push(
        <p key={index} className={`mt-1 font-semibold ${size}`}>{renderInline(heading[2].replace(/#+$/, "").trim(), `h-${index}`)}</p>
      );
      return;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      nodes.push(<hr key={index} className="my-2 border-current opacity-20" />);
      return;
    }
    nodes.push(<p key={index}>{renderInline(trimmed, `p-${index}`)}</p>);
  });
  flush();
  return <>{nodes}</>;
}

export function MarkdownText({ text, className }: { text: string; className?: string }) {
  return <div className={`space-y-1 break-words leading-relaxed ${className ?? ""}`}>{renderMarkdown(text)}</div>;
}
