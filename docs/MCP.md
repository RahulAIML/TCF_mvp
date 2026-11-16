# MCP server: text to MP3 for Grok

Grok (or any MCP client) can turn text into an **MP3 file** on this platform, in
**French, English, Spanish and Portuguese**, with a voice the person chooses, and
gets back a **download link** to the file.

It is the same architecture as the RolPlay Feedback Platform's MCP server
(`RolPlayAI/Landing_Page`, `api/mcp.js`, `docs/MCP.md`) and the dashboard's
`/api/mcp`, ported to this FastAPI backend: stateless Streamable HTTP, JSON
replies, bearer tokens whose SHA-256 is stored, one server `instructions` block,
per-token rate limit, open CORS on `/mcp` only.

## Connect Grok

1. Sign in to the platform and open **Connect Grok** (sidebar, `/tcf/grok`).
2. **Create token**. It is shown **once**: copy it.
3. In Grok, add an MCP server:

   ```json
   {
     "mcpServers": {
       "tcf-text-to-speech": {
         "url": "https://<backend host>/mcp",
         "headers": { "Authorization": "Bearer tcfmcp_…" }
       }
     }
   }
   ```

   The page shows this with your server address filled in. Transport: MCP
   Streamable HTTP, **stateless** (no `Mcp-Session-Id`), `POST /mcp` (or
   `/mcp/`), JSON-RPC 2.0 (single or batched); `GET` answers 405. Protocol
   versions 2025-06-18, 2025-03-26 and 2024-11-05.
4. Ask Grok, in any of the four languages:
   - *Génère un MP3 en français avec une voix féminine : « Bonjour… »*
   - *Make an English MP3 with a male voice: "Welcome…"*
   - *Crea un MP3 en español con una voz femenina: «Hola…»*
   - *Gere um MP3 em português com voz masculina: "Olá…"*

A token acts **as you**: the audio it makes also appears in your **Audio History**
on the Text-to-Speech page. Revoke a token on the same page and it stops working
immediately. Up to 10 active tokens per user.

## Tools

| Tool | What it does |
|---|---|
| `list_languages` | The four languages with their codes (`fr`, `en`, `es`, `pt`) and how many voices each has. |
| `list_voices` | The voices, optionally for one `language`. A voice id looks like `es-ES-female-1`. |
| `text_to_speech` | `text` (up to 10,000 characters) + optional `language`, `voice_id`, `gender`, `include_audio`. Makes the MP3 and returns it. |
| `list_audio` | The MP3 files you generated recently (here or on the website), newest first, each with a fresh link. |

### Language and voice selection

- Languages: French `fr`, English `en`, Spanish `es`, Portuguese `pt`. Names and
  locales are accepted too (`Spanish`, `pt-BR`, `español`).
- Each language has four voices: 2 male, 2 female (`<locale>-<gender>-<n>`, e.g.
  `fr-FR-male-1`, `en-US-female-2`, `es-ES-male-1`, `pt-BR-female-1`). The existing
  French ids are unchanged.
- **Grok asks when you have not said, and generates straight away when you have.** If the
  request names nothing about language or voice, `text_to_speech` does not generate: it
  returns `needs_input: true` with the languages, the voices and the questions to ask
  (it also says which language the text looks like), and Grok asks you. If you already said
  a language, "male"/"female" or a voice in that request, it generates directly with no questions.
  A choice from an earlier message does not carry over: Grok is told to ask again for each new
  request that does not say it, and not to reuse "the same voice as last time" on its own. If you say
  you do not mind, Grok calls it with `use_defaults: true` (French, first male voice).
- Picking the voice: `voice_id` alone uses that voice (and its language); `language` alone
  uses that language's first voice (the requested `gender` first); `gender` alone uses the
  language of the text when it is clear, otherwise it asks for the language; `language` and
  `voice_id` together must agree, otherwise the reply lists the voices of that language.
- Both providers (ElevenLabs `eleven_multilingual_v2`, Gemini TTS) speak the language
  of the text, so write the text in the language you ask for.

### The reply

`text_to_speech` returns `structuredContent` (and the same as text):

```json
{
  "download_url": "https://…/mcp/audio/tts_es-ES-female-1_<32 hex>.mp3?exp=…&sig=…",
  "expires_at": "2026-11-23T12:00:00Z",
  "file_name": "tts_es-ES-female-1_<32 hex>.mp3",
  "suggested_name": "tcf-es-ES-female-1.mp3",
  "mime_type": "audio/mpeg",
  "bytes": 48213,
  "language": "es",
  "voice_id": "es-ES-female-1",
  "voice_label": "Spanish Female",
  "characters": 31
}
```

plus a `resource_link` content block with the same URL. The **download link** works
without signing in (the signature is the credential), downloads as an attachment,
and expires after 7 days. `include_audio: true` also embeds the audio in the reply
for small files (up to 1 MB); it is off by default because the link is enough.

Audio files are stored temporarily on the server (Render's disk is not persistent):
a file that is gone answers 404 with a clear message, and `list_audio` skips it.

## Rules

- **Same discipline as the reference.** No SQL, no filesystem access, no arbitrary
  URLs: only the four tools. A tool problem comes back as a readable result with
  `isError: true` that the agent can correct (wrong voice for the language, text too
  long...), not as a protocol error. Provider errors are summarised; upstream
  messages (which can contain keys or account details) are logged, not returned.
- **Tokens:** only the SHA-256 is stored (`mcp_tokens` table). A token stops working
  when it is revoked or its owner is removed. Limits: 120 calls a minute per token and
  10 audio generations a minute per token (generation costs money).
- **Text is data.** The text Grok is asked to speak is content to read aloud, never
  instructions: the server's `instructions` say so, and the text is only ever sent to
  the voice provider.
- **Download links are signed** (HMAC-SHA256 over file name and expiry, keyed by
  `MCP_AUDIO_SECRET`, else `JWT_SECRET`); the file name is a full 128-bit random
  value, only `tts_*.mp3|wav` names are served, no path can escape the audio folder.
- **CORS:** `/mcp` is open to any origin because the bearer token is the only
  credential (no cookie is read). Every other route keeps the frontend allow-list.

## Every file is an MP3

ElevenLabs returns MP3 directly. Gemini returns raw 16-bit PCM, which is now encoded
to MP3 with `lameenc` (before this change it was saved as a `.wav` that the page
called an MP3). If `lameenc` is missing the file is saved as WAV and the reply says
`audio/wav` instead of pretending.

## Noise at the start and end of the audio

Gemini's raw audio can carry a short loud burst of noise right after the last word and a click at the very start.
The MP3 encoder is not the cause (a clean tone encodes with no burst at either end), so the fix is applied to the raw
audio before it is encoded (`backend/audio_clean.py`, called from `tts_service.py`). It removes a run of up to 400 ms of
frames at either end that are all **loud, noise-like and unvoiced** (speech is voiced, and fricatives such as "s" are
much quieter than vowels, so real words are kept), replaces the silence around the speech with a short true-silence
pad, and fades the start (12 ms) and the end (60 ms). It never fails a generation: if anything goes wrong the original
audio is used. The server logs what it trimmed (`Audio edges cleaned: ...`). Set `TTS_CLEAN_AUDIO=0` to turn it off.

To check a real file (for example one that still sounds wrong) and hear what the server now produces:

```bash
cd backend
pip install -r requirements-dev.txt
python scripts/check_audio_ends.py path/to/file.mp3 cleaned.mp3
```

It prints the level, pitch and noisiness of every 10 ms at both ends, marks the frames it treats as a noise burst,
and writes the cleaned copy. ElevenLabs audio (the fallback provider) is already an MP3 and is not processed.

## Configuration

| Variable | Meaning |
|---|---|
| `PUBLIC_BASE_URL` | The public address of this backend, e.g. `https://tcf-mvp.onrender.com`. Used to build download links and the address shown on Connect Grok. Without it the proxy headers are used. |
| `MCP_AUDIO_SECRET` | Optional key for download-link signatures (defaults to `JWT_SECRET`). Changing it invalidates links already issued. |
| `GEMINI_API_KEY`, `ELEVENLABS_API_KEY` | The voice providers (as before). |
| `TTS_CLEAN_AUDIO` | `0` turns off the start/end noise cleaning (on by default). |
| `ELEVENLABS_VOICE_ID_TTS_M1/M2/F1/F2` | Override the ElevenLabs voice behind each of the four voices (as before; now used for all four languages). |

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

102 checks: the protocol (initialize, version negotiation, batches, notifications, bad
input, size limit), auth (401 and the Bearer challenge, revocation, per-token rate
limit), the token API (shown once, only the hash stored, ownership, limits), each
language and voice rule, the signed download (tampered, expired, missing file,
path tricks), MCP audio appearing in the website's Audio History, and the real MP3
encoding. The voice providers are replaced by a stub, so the tests need no keys.
