# Hotseat Bridge — Frontend Contract

**Version:** 0.5 · **Transport:** HTTP/1.1 + Server-Sent Events (SSE) + NDJSON
**Implementation:** [`hotseat_core/bridge.py`](hotseat_core/bridge.py) · **No third-party dependencies**

The bridge lets a CLI, desktop app, or web UI drive a Hotseat session without
scraping terminal output. Every model turn, token, saved session, and error is a
structured event.

---

## 1. Run it

```bash
python -m hotseat_core --serve                 # http://127.0.0.1:8765
python -m hotseat_core --serve --port 9000
python -m hotseat_core --serve --provider demo # no keys, no models, demo replies
```

`--serve` also hosts the desktop war room at `/console`: `web/index.html`,
`web/style.css`, and `web/app.js`. It is not a canned page; it reads `/modes`,
`/providers`, `/scouts/latest`, starts sessions through `POST /sessions`, and
streams the session through SSE.

Phones and tablets get a dedicated companion at `/m`: `web/mobile.html`,
`web/mobile.css`, and `web/mobile.js`. It uses the same API and SSE endpoints
but has a separate setup → live → verdict flow. The war room redirects to `/m`
below 768px unless `?desktop=1` is present. Every shell links to the others.

`/` serves the front door — `web/table.html`, `web/table.css`, and `web/table.js`
— a cartoon boardroom where the cast is the interface. The idea is a case file on
the table, turns arrive as speech bubbles, clicking a character opens their
dossier, and the paper program card recasts the room for every mode (arena,
classic, v2, v3 panel/tribunal, bmad). It uses the same endpoints and SSE events
as the other shells; `/table` is an alias.

Only these nine files and the `/console`, `/m`, and `/table` aliases are served —
there is no filesystem or directory endpoint.

The same contract is available as a streaming CLI:

```bash
python -m hotseat_core --mode classic --json-stream "your idea"
```

Both produce the **same event objects**. CLI NDJSON is one event per line on
stdout; human status goes to stderr.

### Binding and auth

| Setting | Default | Notes |
| :--- | :--- | :--- |
| Host | `127.0.0.1` | Refuses a non-loopback host unless a token is set. |
| Port | `8765` | `--port 0` lets the OS choose (read `server_address`). |
| Token | none | `--token secret` → `Authorization: Bearer secret` or `?token=secret`. |
| CORS | off | `--allow-origin http://localhost:3000` (repeatable, exact match). |

There is **no filesystem endpoint**. The legacy v3 `/list/{dir}` surface was not
carried forward. The only static routes are the six web assets above (`/m` maps
to `mobile.html`). Bind to loopback, or set a token and an exact CORS origin.
Static assets are public so the page can load; API calls still require the token
(the UI reads `?token=` and carries it to `/m`).

All JSON responses send `Cache-Control: no-store`. Unknown routes return 404;
unknown sessions 404; invalid bodies 400; missing/invalid token 401.

Errors always have the shape:

```json
{ "error": "A human-readable reason." }
```

---

## 2. Endpoints

### `GET /health`

```json
{ "status": "ok", "version": "0.2.0" }
```

### `GET /modes`

```json
{
  "modes": [
    {
      "mode": "v3",
      "label": "v3 — the personal panel / tribunal",
      "description": "Marlowe, Priya, and Zero for personal calls; a five-role tribunal for decisions.",
      "variants": ["panel", "tribunal"],
      "default_variant": "panel",
      "personas": { "panel": 3, "tribunal": 5 }
    }
  ]
}
```

### `GET /providers`

```json
{
  "providers": [
    { "name": "ollama", "local": true, "offline": false, "requires_key": false, "default_model": "llama3.2:1b" },
    { "name": "demo", "local": false, "offline": true, "requires_key": false, "default_model": "hotseat-demo" }
  ]
}
```

### `GET /providers/status`

Credential readiness for every provider. Values are never included; keyed
providers are `configured` only when a credential resolves from the environment,
repo `.env`, or the Concierge vault. Local/demo providers need no key and are
marked configured; reachability is not probed here.

```json
{
  "configured": ["openrouter", "demo", "ollama"],
  "missing_credentials": ["anthropic", "mistral", "cerebras", "groq"],
  "providers": [
    {
      "name": "openrouter",
      "configured": true,
      "requires_key": true,
      "has_credential": true,
      "credential_names": ["OPENROUTER_API_KEY", "OPENROUTER_KEY"],
      "local": false,
      "offline": false,
      "default_model": "openai/gpt-4o-mini"
    }
  ]
}
```

### `GET /personas?mode=classic&variant=&system=1`

`system=1` includes each persona's full system prompt (needed for an editor UI).

```json
{
  "mode": "classic",
  "variant": "default",
  "label": "Classic — the idea audit",
  "description": "Auditor, market read, closer. The original three-voice session.",
  "closer": null,
  "personas": [
    {
      "key": "audrey",
      "name": "Dame Audrey",
      "model": "deepseek-r1:1.5b",
      "max_tokens": 350,
      "temperature": 0.75,
      "emoji": "👓",
      "color": "#c084fc",
      "styles": []
    }
  ]
}
```

### `PUT /personas/{mode}/{key}?variant=`

Update a persona for **subsequent sessions in this bridge process** (edits are not
written to disk). Body accepts any of `name`, `system`, `model`, `max_tokens`,
`temperature`, `emoji`, `color`, `styles`.

```bash
curl -XPUT 'localhost:8765/personas/classic/audrey' \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:1.5b","temperature":0.5}'
```

Returns `{ "persona": { ...full persona, including "system" } }`.
Unknown mode/persona → 404. Unknown field values or `max_tokens <= 0` → 400.

### `GET /scouts/latest`

Returns the most recent ChronoScouts/market report collected by this bridge
process, or `null` if no sweep has run.

```json
{
  "report": {
    "generated_at": "2026-11-24T20:43:49-06:00",
    "root": "/home/me/ChronoScouts",
    "sources": ["chronoscouts:/home/me/ChronoScouts", "hn", "pricing:acme.test"],
    "errors": [],
    "counts": { "signals": 8, "prices": 3 },
    "market_anchors": [
      { "competitor": "acme.test", "product": "Acme Pricing", "price": "$29/mo", "amount": 29.0, "currency": "USD", "period": "monthly", "tier": "paid", "source": "pricing" }
    ],
    "signals": [
      { "source": "hn", "title": "…", "detail": "…", "url": "…", "published_at": "…", "kind": "pain", "weight": 0.87 }
    ],
    "prices": [
      { "competitor": "acme.test", "product": "Acme Pricing", "price": "$29/mo", "currency": null, "url": "…", "observed_at": "…", "weight": 1.0 }
    ]
  },
  "next": "/scouts/refresh"
}
```

Local sources are `signals_export.json` and `scout_rag_store.db` (opened
read-only) under `CHRONOSCOUTS_DIR`, or `dist/` beneath it. Live sources are the
seed query on Hacker News, RSS URLs, and competitor pricing pages. Weights decay
with age; the report is timestamped data, never instructions.

### `POST /scouts/refresh`

Collects a fresh report and stores it as `/scouts/latest`.

```json
{ "seed": "roofing quote tool", "live": true, "urls": ["https://example.test/feed.xml"], "pricing_urls": ["https://acme.test/pricing"] }
```

`live` defaults to `true`. Set `false` for local ChronoScouts data only. Returns
`{ "report": { … } }`.

### `GET /history?limit=10`

Reads SQLite memory, newest first. `limit` is clamped to 1–100.

```json
{
  "sessions": [
    {
      "id": 42,
      "timestamp": "2026-11-24T20:43:49+00:00",
      "mode": "classic",
      "topic": "ship the smallest version this week",
      "turns": [
        { "persona": "audrey", "speaker": "Dame Audrey", "content": "…", "round": 1, "model": "qwen2.5:1.5b" }
      ],
      "transcript": "# The Hot Seat\n…",
      "provider": "ollama",
      "model": null
    }
  ]
}
```

Legacy rows (persona columns instead of a `turns` JSON column) are reconstructed
in the same shape.

### `POST /sessions`

Starts a session in a background thread. Returns immediately.

```json
{
  "mode": "v3",
  "topic": "hire a contractor or keep it in-house?",
  "variant": "tribunal",
  "provider": "demo",
  "model": "llama3.2:1b",
  "styles": ["nosyco", "terse"],
  "system_directive": "This is a family business; the answer must include a Tuesday.",
  "sampling": { "temperature": 0.7, "max_tokens": 300 },
  "options": {
    "statement": "v2 only: the volunteer's opening statement",
    "constraints": "arena only: budget $0, one weekend"
  },
  "personas": { "fixer": { "model": "tinyllama:latest" } },
  "role_models": { "producer": "fast-model", "coroner": "reasoning-model" },
  "scout_context": { "live": true, "urls": [], "pricing_urls": [] }
}
```

Only `mode` and `topic` are required. `mode` is `classic`, `v2`, `v3`, `bmad`, or
`arena`. `role_models` maps persona keys to models for this session and overrides
manifest persona models; unknown keys are rejected by the runtime. Retryable
provider failures fall through to the next configured cloud key automatically.

`scout_context` is optional:

* `true` — collect a live sweep for the topic before the first prompt.
* `{ "live": false, "urls": [...], "pricing_urls": [...] }` — control sources.
* a string — inject that exact evidence into the arena prompts.

The collected report is attached to the session as `scouts` and also becomes
`/scouts/latest`. Arena injects the timestamped evidence into the Producer,
Critic, Foreman, Architect, and Coroner prompts. Every other mode receives the
same evidence as a system directive, so classic, v2, v3, and bmad are not blind
to the wire. Response `202`:

```json
{
  "session_id": "2c5b97511055",
  "mode": "v3",
  "variant": "tribunal",
  "events_url": "/sessions/2c5b97511055/events"
}
```

`Location: /sessions/{id}` is also set.

### `GET /sessions/{id}?since=0`

Polling fallback for clients without SSE. `since` is an event index.

```json
{
  "session_id": "2c5b97511055",
  "mode": "v3",
  "variant": "tribunal",
  "topic": "hire or contract?",
  "done": true,
  "error": null,
  "scouts": { "generated_at": "…", "counts": { "signals": 8, "prices": 3 }, "signals": [], "prices": [], "sources": [], "errors": [] },
  "result": {
    "session_id": "2c5b97511055",
    "memory_id": 43,
    "mode": "v3",
    "variant": "tribunal",
    "topic": "hire or contract?",
    "provider": "demo",
    "model": null,
    "fallback_used": false,
    "transcript": "# The Hot Seat\n…",
    "turns": [
      { "persona": "fixer", "speaker": "The Fixer", "content": "1. …", "round": 5, "model": "llama3.2:1b" }
    ]
  },
  "events": [
    { "type": "session_start", "session_id": "2c5b97511055" }
  ]
}
```

`result` is `null` until `done` is true. `error` is a string if the provider or
engine failed; partial turns remain in `events`.

### `GET /sessions/{id}/events?since=0` — SSE

`Content-Type: text/event-stream`. `since` is an event index. The server replays
events from that index, then streams live events, sends `: ping` comments every
15 s, and closes after `session_end`. Each message is:

```
event: persona_turn
data: {"type":"persona_turn","persona":"audrey","speaker":"Dame Audrey",...}

```

EventSource cannot set headers — pass `?token=` when auth is enabled.

### `POST /sessions/{id}/inject`

Queue an operator note. It is appended to the **next** persona prompt; notes
never interrupt an in-flight model call.

```json
{ "message": "Price it at ten dollars and name the first customer." }
```

`202 { "queued": true }`; 400 if empty; 404 unknown; 400 if the session finished.

### `POST /sessions/{id}/messages`

Run one threaded follow-up against a finished, persisted session. The closer
persona answers with the prior transcript in view, and the stored row is updated
with the new turn and transcript (same session id and memory id).

```json
{ "message": "Tighten the brief and defend the price." }
```

`202 { "accepted": true }`; 400 if the session is still running, was not saved,
or the message is empty; 404 unknown. Reconnect to the SSE endpoint with
`?since=<events already received>` to stream the follow-up. The job emits
`operator_message`, `iteration_start`, then normal turn events and a final
`session_end` with `"follow_up": true` and `"iteration": 2`.

### `POST /sessions/{id}/stop`

Sets the stop flag. The current model call finishes, then the engine stops before
the next turn and emits `session_end` with `"stopped": true`.

`202 { "stopping": true }` (idempotent).

---

## 3. Event schema

Every event has `type`. All events except `token_chunk` are also retrievable from
`GET /sessions/{id}`.

| `type` | Payload |
| :--- | :--- |
| `session_start` | `session_id`, `timestamp`, `mode`, `variant`, `label`, `topic`, `provider`, `model`, `role_models`, `personas[]` (public persona objects) |
| `status` | `message`, `persona`, `round` — UI spinners and “who is thinking” |
| `token_chunk` | `persona`, `text` — real streaming for OpenAI-compatible and Ollama; Anthropic sends one chunk |
| `persona_turn` | `persona`, `speaker`, `content`, `round`, `model` — completed turn |
| `memory_saved` | `session_id`, `path`, `memory_id` |
| `error` | `session_id`, `message` — the session then ends; turns already produced are kept |
| `operator_message` | `session_id`, `timestamp`, `message` — a threaded follow-up was accepted |
| `iteration_start` | `session_id`, `timestamp`, `iteration`, `parent_turns` — follow-up pass begins |
| `session_end` | `session_id`, `timestamp`, `mode`, `variant`, `topic`, `provider`, `model`, `fallback_used`, `memory_id`, `turns[]`, `transcript`, `stopped`; follow-ups add `follow_up` and `iteration` |

`turns[]` entries are the same object as `persona_turn` without `type`.

### Ordering guarantees

1. `session_start` is always first.
2. `token_chunk`s for one persona precede that persona's `persona_turn`.
3. `memory_saved` (when saving succeeded) precedes `session_end`.
4. `session_end` is last unless the connection drops.
5. There is no `stream_end` event; SSE closes, polling clients read `done`.

---

## 4. Minimal JavaScript client

```html
<button id="go">Put it in the chair</button>
<pre id="out"></pre>
<script>
const base = "http://127.0.0.1:8765";

document.getElementById("go").onclick = async () => {
  const response = await fetch(`${base}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "classic", topic: "Ship the small version?" })
  });
  const { session_id, events_url } = await response.json();

  const stream = new EventSource(base + events_url);
  stream.addEventListener("token_chunk", (message) => {
    const event = JSON.parse(message.data);
    document.getElementById("out").textContent += event.text;
  });
  stream.addEventListener("persona_turn", () => {
    document.getElementById("out").textContent += "\n\n";
  });
  stream.addEventListener("status", (message) => {
    const event = JSON.parse(message.data);
    console.log("…", event.message);
  });
  stream.addEventListener("error", (message) => {
    console.error(JSON.parse(message.data));
    stream.close();
  });
  stream.addEventListener("session_end", () => {
    document.getElementById("out").textContent += "\n\n— session complete —";
    stream.close();
  });
};
</script>
```

---

## 5. CLI equivalents

| HTTP | CLI |
| :--- | :--- |
| `POST /sessions` | `python -m hotseat_core --mode <mode> "<topic>"` |
| `GET /sessions/{id}/events` | `python -m hotseat_core --json-stream <mode> "<topic>"` |
| `POST …/stop` | `Ctrl+C` (the CLI exits; the Python API accepts a `stop_event`) |
| `GET /modes` | `--list-modes` |
| `GET /personas` | `--list-personas [mode]` |
| `GET /providers` | `--list-providers` |
| `GET /history` | `--history --limit 10` |

---

## 6. Security notes

- Loopback by default; non-loopback binds require `--token`.
- Persona editing is runtime-only and never accepts a filesystem path.
- Session topics and model output are data. A frontend must render them as text,
  not as trusted HTML/markdown with embedded scripts.
- The bridge stores what the engine produces in the configured SQLite database
  (`HOTSEAT_DB`, `--db`, or `~/hotseat/memory.db`). Point it somewhere intentional.
