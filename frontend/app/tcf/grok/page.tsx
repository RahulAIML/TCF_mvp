"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Copy, KeyRound, Loader2, Plug, Trash2 } from "lucide-react";
import TcfAppShell from "@/components/TcfAppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createMcpToken, getMcpInfo, listMcpTokens, revokeMcpToken } from "@/services/api";
import type { McpInfo, McpTokenRecord } from "@/types/mcp";

// What to say to Grok, in each supported language.
const EXAMPLES = [
  { code: "FR", text: "Génère un MP3 en français avec une voix féminine : « Bonjour, bienvenue à votre cours de TCF. »" },
  { code: "EN", text: "Make an English MP3 with a male voice: “Welcome to your TCF practice session.”" },
  { code: "ES", text: "Crea un MP3 en español con una voz femenina: «Hola, bienvenido a tu práctica del TCF.»" },
  { code: "PT", text: "Gere um MP3 em português com voz masculina: “Olá, bem-vindo à sua prática do TCF.”" },
];

function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1800);
        } catch {}
      }}
      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
    >
      {done ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      {done ? "Copied" : label}
    </button>
  );
}

export default function ConnectGrokPage() {
  const [info, setInfo] = useState<McpInfo | null>(null);
  const [tokens, setTokens] = useState<McpTokenRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const [name, setName] = useState("Grok");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  // The full token exists only here, right after it is created: the server keeps just its hash.
  const [newToken, setNewToken] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [i, t] = await Promise.all([getMcpInfo(), listMcpTokens()]);
      setInfo(i);
      setTokens(t);
      setLoadError("");
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : "Could not load the connection details.");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreate = useCallback(async () => {
    setCreating(true); setCreateError("");
    try {
      const made = await createMcpToken(name.trim() || "Grok");
      setNewToken(made.token);
      await refresh();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Could not create the token.");
    } finally { setCreating(false); }
  }, [name, refresh]);

  const handleRevoke = useCallback(async (t: McpTokenRecord) => {
    if (!window.confirm(`Revoke "${t.name}"? Anything using this token stops working immediately.`)) return;
    try {
      await revokeMcpToken(t.id);
      await refresh();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Could not revoke the token.");
    }
  }, [refresh]);

  const mcpUrl = info?.mcp_url ?? "";
  const config = JSON.stringify(
    { mcpServers: { "tcf-text-to-speech": { url: mcpUrl, headers: { Authorization: `Bearer ${newToken ?? "<your token>"}` } } } },
    null, 2
  );
  const active = tokens.filter((t) => !t.revoked_at);

  return (
    <TcfAppShell
      title="Connect Grok"
      subtitle="Let Grok turn text into MP3 audio for you, in French, English, Spanish or Portuguese"
      backHref="/tcf"
    >
      <div className="max-w-2xl space-y-5">
        {loadError && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-600 text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" /> {loadError}
          </div>
        )}

        {/* 1. token */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-indigo-500" /> 1. Create an access token
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-3">
            <p className="text-xs text-slate-500">
              The token lets Grok act as you: the audio it makes shows up in your Audio History. You can have up to{" "}
              {info?.max_active_tokens ?? 10} active tokens and revoke any of them at any time.
            </p>
            <div className="flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value.slice(0, 80))}
                aria-label="Token name"
                placeholder="Grok"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                onClick={handleCreate}
                disabled={creating}
                className="rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 flex items-center gap-2 transition-colors"
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                Create token
              </button>
            </div>
            {createError && (
              <p role="alert" className="text-xs text-red-500 flex items-center gap-1">
                <AlertCircle className="h-3 w-3 shrink-0" /> {createError}
              </p>
            )}

            {newToken && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 space-y-2" data-testid="new-token">
                <p className="text-xs font-semibold text-amber-700">
                  Copy it now. It is shown only once; if you lose it, create another.
                </p>
                <code className="block break-all rounded-lg bg-white border border-amber-200 px-2.5 py-2 text-xs text-slate-800">{newToken}</code>
                <div className="flex gap-2">
                  <CopyButton value={newToken} label="Copy token" />
                  <button onClick={() => setNewToken(null)} className="text-xs text-slate-500 hover:text-slate-700">
                    I saved it
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 2. connect */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700 flex items-center gap-2">
              <Plug className="h-4 w-4 text-indigo-500" /> 2. Add the server to Grok
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-3">
            <p className="text-xs text-slate-500">
              In Grok, add an MCP server with this address and send the token as a Bearer header. Transport: MCP Streamable HTTP.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 break-all rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-2 text-xs text-slate-800">{mcpUrl || "…"}</code>
              {mcpUrl && <CopyButton value={mcpUrl} label="Copy URL" />}
            </div>
            <p className="text-xs text-slate-500">Or paste this configuration:</p>
            <div className="relative">
              <pre className="overflow-x-auto rounded-lg bg-slate-900 text-slate-100 p-3 text-xs leading-relaxed">{config}</pre>
              <div className="absolute right-2 top-2"><CopyButton value={config} label="Copy" /></div>
            </div>
          </CardContent>
        </Card>

        {/* tokens */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700">Your tokens ({active.length} active)</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-2">
            {tokens.length === 0 && <p className="text-xs text-slate-400">No tokens yet.</p>}
            {tokens.map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-700 truncate">
                    {t.name}{" "}
                    {t.revoked_at && <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-500">revoked</span>}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    <code>{t.hint}</code> · created {fmtDate(t.created_at)} · last used {fmtDate(t.last_used_at)}
                  </p>
                </div>
                {!t.revoked_at && (
                  <button
                    onClick={() => handleRevoke(t)}
                    aria-label={`Revoke ${t.name}`}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        {/* what Grok can do */}
        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm text-slate-700">What Grok can do</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-3">
            <ul className="space-y-1.5">
              {(info?.tools ?? []).map((t) => (
                <li key={t.name} className="text-xs text-slate-600">
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-800">{t.name}</code> {t.description}
                </li>
              ))}
            </ul>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide pt-1">Try asking</p>
            <ul className="space-y-1.5">
              {EXAMPLES.map((e) => (
                <li key={e.code} className="text-xs text-slate-600 flex gap-2">
                  <span className="shrink-0 rounded bg-indigo-50 px-1.5 py-0.5 font-semibold text-indigo-600">{e.code}</span>
                  <span>{e.text}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-slate-400">
              Grok replies with a download link to the MP3 (valid for 7 days). Files are also saved in your Audio History on the Text-to-Speech page.
            </p>
          </CardContent>
        </Card>
      </div>
    </TcfAppShell>
  );
}
