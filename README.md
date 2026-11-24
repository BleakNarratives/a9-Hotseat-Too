<p align="center">
  <img src="assets/hotseat-banner.svg" alt="Hotseat-Too Banner" width="100%" />
</p>

<h1 align="center">The Hot Seat</h1>
<p align="center"><b>One idea. A panel that doesn't flinch. A brief you can build today.</b></p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776AB" />
  <img alt="Core dependencies: none" src="https://img.shields.io/badge/core%20dependencies-none-2ea44f" />
  <a href="https://github.com/BleakNarratives/a9-Hotseat-Too/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/BleakNarratives/a9-Hotseat-Too/actions/workflows/tests.yml/badge.svg" /></a>
  <img alt="Local first" src="https://img.shields.io/badge/local--first-yes-8957e5" />
  <img alt="Release 0.5.0" src="https://img.shields.io/badge/release-0.5.0-2ea44f" />
</p>

**Hotseat-Too** is a local-first AI pressure cooker: a small cast of sharply drawn
personas interrogates an idea, a decision, or a build until something true falls
out. It runs on a phone in Termux with Ollama, on a laptop with zero dependencies,
or against any cloud model with your own key.

One session. Structured turns. A closer who speaks last and short. Persistent
memory. Structured events for your own frontend. No phases to schedule, no
document chain to carry between chats.

**Current release:** `0.5.0` — the first packaged build.

## Install

Build the wheel from a checkout and install it:

```bash
python -m pip install build
python -m build --wheel
python -m pip install dist/*.whl
hotseat --version   # hotseat 0.5.0
hotseat --provider demo "ship the smallest version this week"
```

The wheel bundles the desktop console and the `/m` companion under
`hotseat_core/web`, so `hotseat --serve` serves the same UI from an installed
package. A source checkout still runs with `python -m hotseat_core` without
installing anything.

---

## Twenty seconds, no key

```bash
git clone https://github.com/BleakNarratives/a9-Hotseat-Too
cd a9-Hotseat-Too
python -m hotseat_core --provider demo "ship the smallest version this week"
```

```text
==============================================================
  THE HOT SEAT — Classic — the idea audit
  ship the smallest version this week
==============================================================
I see. You want the version where nobody has to test it. Right then: this plan
assumes the hard part is the code, when it is the maintenance. Decide who owns
it on a rainy Tuesday, or stop calling it a product.
_(demo output — no model was called)_

Actually, you're solving the visible problem. The thing underneath it is
distribution — nobody can find the thing you built. Fix the front door before
you add another room.

The idea is sound. The timeline is the story you tell yourself to avoid
starting. Pick the smallest version and ship it this week.
```

The demo provider is canned and labeled on purpose: build the UI, demo the flow,
and test the contract before anyone buys a token.

## Modes

| Mode | Cast | Use it for |
| :--- | :--- | :--- |
| `arena` | Producer → Critic → Foreman → Architect → Coroner | Your idea vs three generated rivals |
| `classic` | Dame Audrey (auditor) → Claib (market) → Vertical AI (closer) | Ideas, pitches, “is this stupid?” |
| `v2` | Three skeptics → a volunteer defending the idea | Debate; `--statement` sets the defence |
| `v3 panel` | Marlowe (witness) → Priya (systems) → Zero (closer) | Personal decisions and life inventory |
| `v3 tribunal` | Adversary, Reason, Whistleblower, Evangelist → Fixer | Decisions that need three ranked actions |
| `bmad` | Analyst → PM → Architect → Builder → QA | A build brief in one pass |

```bash
python -m hotseat_core --list-modes
python -m hotseat_core --list-personas bmad
python -m hotseat_core --mode v3 --variant tribunal "hire or contract?"
```

## Your idea vs three rivals

The arena is the front door: your idea is contender zero, and the panel generates
three rivals for the same customer and job — cheaper, premium, and a niche wedge.
They are cross-examined, ranked, and one is voted off. The winner gets a build
brief; yours gets an autopsy either way.

```bash
python -m hotseat_core --mode arena "a CLI that turns a voice memo into tasks" \
  --constraint "budget $0" --constraint "one weekend"
```

1. **The Producer** builds four fair contenders, each with a bet, price, wedge,
   first ten customers, and the assumption it dies on.
2. **The Critic** cross-examines all four.
3. **The Foreman** ranks and eliminates one, with the deciding difference.
4. **The Architect** gives the survivor a vertical-slice build brief.
5. **The Coroner** writes the autopsy: what killed your idea, and the smallest
   change that would have saved it.

Five turns, one session, no scores out of 100. It is also the practical front door
to a Vertical AI boardroom: the same cast, memory, and event stream in one command.

## BMAD without the ceremony

BMAD's roles are useful. Its phase gates, PRD handoffs, story files, and agent
ceremonies are not — they cost sessions before any code exists. `bmad` mode keeps
the roles and the artifacts that matter, and compresses them into a **single
five-turn pass**:

```bash
python -m hotseat_core --mode bmad "a local-first CLI that turns a voice memo into a task list"
```

1. **Analyst** — user, evidence, assumptions, and the assumption that kills it.
2. **PM** — one-sentence product, three must-haves, non-goals, metric, smallest slice.
3. **Architect** — the vertical slice, interfaces, storage, risky dependency, deferrals.
4. **Builder** — first story: files, interfaces, first test, timebox, done today.
5. **QA** — three acceptance checks, two kill criteria, what to cut, GO/NO-GO.

Output is a Markdown transcript you can save as the brief. No interviews, no
templates, no second session to “generate the architecture document.” If the
brief is wrong, you learned it in five model turns instead of five hours.

## Real models

### Local (the original habitat)

```bash
ollama serve
ollama pull deepseek-r1:1.5b llama3.2:1b deepseek-coder:1.3b

python -m hotseat_core --provider ollama --mode classic "my idea"
python -m hotseat_core --provider ollama --mode bmad "the thing I want to build"
```

Defaults are 1–1.5B models on purpose — see
[the model routing notes](docs/LEGACY_NOTES.md#model-routing-learned-on-a-phone).

### Cloud

Keys resolve automatically from the environment, a repo-root `.env`, or
`~/.concierge/vault.json` via
[`hotseat_core/vault_loader.py`](hotseat_core/vault_loader.py) — no exports or
CLI prefixes required. The vault is searched recursively, provider/key matching
is case-insensitive, and aliases such as `OPENROUTER_KEY` work.

```bash
# ~/.concierge/vault.json can be nested in any of these shapes:
# {"keys": {"OPENROUTER_KEY": "..."}, "mistral": {"api_key": "..."}}
# {"providers": {"anthropic": {"token": "..."}}}
# {"secrets": [{"name": "GROQ_API_KEY", "value": "..."}]}

python3 -m hotseat_core --provider openrouter --mode arena "my idea"
python3 -m hotseat_core --provider mistral --mode bmad "the thing I want to build"
```

`.env` is ignored by Git. Nothing is hardcoded. Credential values resolve only
when a selected provider needs them; `GET /providers/status` checks which
credentials are present for every provider (never values) so the UI can mark the
keyed ones `CONFIGURED`.

Providers are resilient by default: a 429, 5xx, timeout, or connection failure
falls through to the next configured cloud key, and the backup becomes sticky for
the rest of the session. `GET /providers/status` reports credential presence, not
reachability: a local router or Ollama can still be down until a session starts.

Route models per role instead of forcing one model across the room:

```bash
python3 -m hotseat_core --mode arena \
  --role-model producer=fast-model \
  --role-model critic=fast-model \
  --role-model foreman=strong-reasoner \
  --role-model architect=strong-reasoner \
  --role-model coroner=strong-reasoner \
  "my idea"
```

The same map is accepted as `role_models` on `POST /sessions`; `manifest.json`
persona overrides continue to work for durable defaults, and role defaults can be
stored as `"role_models": {"arena": {"producer": "fast-model"}}` under
`hotseat_core`.

| Provider | Notes |
| :--- | :--- |
| `auto` | Probe local 9router → first configured cloud key → OpenRouter default |
| `ollama` | Local, no key; `OLLAMA_BASE_URL` to override |
| `9router`, `ai_gateway` | Local OpenAI-compatible routers |
| `openrouter`, `anthropic`, `mistral`, `cerebras`, `groq` | Cloud; env or vault |
| `demo` | Offline canned replies for frontends, docs, and tests |

## The live arena console

`--serve` hosts a zero-dependency retro terminal-arena UI at
**http://127.0.0.1:8765** — no static demo page, no build step:

```bash
python3 -m hotseat_core --serve --provider demo
# open http://127.0.0.1:8765
```

The console is wired to the bridge contract: mode and provider selectors, seed
prompt and constraint tags, push-to-talk dictation (Web Speech API with a text
fallback), a live four-contender bracket, critic feed, Foreman callout, build
brief, Coroner autopsy, and threaded follow-ups against the active session. It
reads the real time/token/persona event stream over SSE and reconnects with an
event offset instead of replaying duplicates.

**Scout Wire** runs across the top: live ChronoScouts signals, competitor price
points, and structured market anchors, with a drawer for source health and a
**Pull fresh intel** button. The FreeBuff-purple **Switchboard** theme is one
click away from the maroon terminal theme. Provider status badges show which
credentials the bridge discovered and label keyed providers `CONFIGURED` (not
live reachability), the role drawer routes models per persona, and **Export
brief** downloads the bracket, Architect slice, and Coroner autopsy as one
Markdown file.

Phones and tablets get a dedicated companion at **http://127.0.0.1:8765/m**.
It keeps the same bridge and SSE contract but replaces the dense war-room grid
with a three-state flow: setup, live, and verdict. Setup uses constraint chips and
a sticky Convene button; live has a speaker spotlight, five-step progress rail,
swipeable contenders, segmented detail tabs, and a Scout Intel bottom sheet; the
verdict starts with the winner and offers Share, Copy Markdown, and Download .md.
The `/` route auto-redirects below 768px unless `?desktop=1` is present, and both
headers link between War Room and Companion.

## Live ChronoScouts & market intel

Every arena run can carry real, timestamped market evidence into the Producer,
Critic, Foreman, Architect, and Coroner prompts:

```bash
# Local ChronoScouts export (dist/signals_export.json or scout_rag_store.db)
python3 -m hotseat_core --mode arena --scout-feed --scout-offline "my idea"

# Local + live Hacker News, RSS, and pricing scouts
CHRONOSCOUTS_DIR=~/ChronoScouts python3 -m hotseat_core --mode arena \
  --scout-feed "my idea" \
  --scout-url "https://example.com/feed.xml" \
  --pricing-url "https://competitor.example/pricing"
```

Local SQLite is opened with `?mode=ro`; nothing is written back. Signals carry a
temporal-decay weight (`0.5 ** (age_days / half_life)`). Live sources are
best-effort: a blocked feed is reported in the Scout Wire drawer, never allowed to
kill the session. `HOTSEAT_SCOUT_RSS` and `HOTSEAT_PRICING_URLS` add defaults.

Signals, SQLite rows, RSS entries, and pricing pages are parsed into a
`market_anchors` block: competitor, product, amount, currency, `monthly` /
`yearly` / `one_time` / `custom` period, and `freemium` / `paid` / `enterprise`
tier. The same structured block is returned by `/scouts/latest` and injected into
the Producer and Critic prompts.

## Bring your own frontend

A stdlib HTTP + SSE bridge, no scraping stdout, no Gradio:

```bash
python -m hotseat_core --serve --provider demo
curl -s -XPOST localhost:8765/sessions \
  -H 'Content-Type: application/json' \
  -d '{"mode":"bmad","topic":"ship it or bin it?"}'
curl -N localhost:8765/sessions/<session_id>/events
curl -s localhost:8765/scouts/latest
```

Modes, personas, providers, provider credential status, history, and scout reports are queryable; personas
are editable for the running process; operator notes can be injected between
turns; sessions can be stopped or continued with a threaded follow-up. Events:
`session_start`, `status`, `token_chunk`, `persona_turn`, `operator_message`,
`iteration_start`, `memory_saved`, `error`, `session_end`.

Full schemas and a working EventSource client:
**[FRONTEND_CONTRACT.md](FRONTEND_CONTRACT.md)**.

The CLI streams the same events:

```bash
python -m hotseat_core --mode bmad --json-stream "the thing" | jq -r 'select(.type=="persona_turn") | .content'
```

## Layout

```
pyproject.toml    package metadata, hotseat console entry point, bundled assets
LICENSE           MIT
CHANGELOG.md      release notes
hotseat_core/
  config.py       manifest + env resolution, no side effects on import
  personas.py     casts, routing, limits, overrides
  providers.py    urllib transport (OpenAI-compatible, Anthropic, Ollama) + demo
  vault_loader.py recursive vault + repo .env credential resolution
  scouts_feed.py  ChronoScouts JSON/SQLite + HN/RSS/pricing collectors
  tuning.py       composable style directives and sampling; filler cleanup
  storage.py      SQLite memory + JSONL log, in-place legacy migration
  engines/        classic · v2_web · v3_agent · bmad · arena · followup
  runtime.py      orchestration, events, persistence, threaded follow-ups
  cli.py          python -m hotseat_core
  bridge.py       HTTP/SSE/NDJSON adapter + packaged static console serving
  web/            zero-dependency war room + /m companion shell
vault_loader.py   compatibility shim for older imports
tests/            62 tests, stdlib only
docs/             extracted legacy context, decisions, and the unbuilt show concept
```

That is the whole tracked project. The old trees were read, their durable ideas
captured in [docs/LEGACY_NOTES.md](docs/LEGACY_NOTES.md), and removed from the
working tree. They remain in Git history (`git show e96909a:hotseat_v2/app.py`);
nothing was lost, and the repository is now one vertical slice instead of four
overlapping ones.

## Memory

* `~/hotseat/memory.db` — SQLite, normalized sessions; old persona-column rows are
  reconstructed automatically.
* `~/hotseat/sessions.log` — append-only JSONL; legacy `timestamp | topic` lines
  are still parsed.
* Override with `--data-dir`, `--db`, `HOTSEAT_DATA_DIR`, or `HOTSEAT_DB`.

```bash
python -m hotseat_core --history --limit 5
```

## Style

`--style nosyco,terse` composes prompt directives with sampling changes
(temperature, top-p, penalties, token caps). Personas can be overridden in
`manifest.json` or per run.

This is voice and structure control, not model surgery: no weight changes, no
guardrail removal, no provider-policy bypass. If a model refuses, that is the
model's policy — pick a model whose policy fits the job.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

Covered: manifest/env precedence, nested vault and `.env` resolution, per-role
model routing, 429/timeout fallback routing, provider-status credential presence
without secret values, persona resolution and overrides, legacy SQLite migration,
JSONL and legacy logs, every engine including `bmad` and `arena`, scout evidence
injection, ChronoScouts JSON/SQLite ingestion, live fetcher parsing, structured
market anchors, threaded follow-ups, NDJSON output, HTTP endpoints, static war
room and `/m` companion routes, token auth, and the loopback-binding guard. CI
runs on Python 3.10–3.12 and smoke-tests the installed wheel on 3.12.

## Termux

```bash
pkg install python
# Install Ollama for Termux/Android using its current instructions, then:
python -m hotseat_core --provider ollama --mode classic "my idea"
```

## Roadmap

- [x] One package: classic, v2, v3 panel/tribunal, BMAD-lite, and Arena
- [x] Zero-dependency core, provider layer, safe demo mode
- [x] Structured NDJSON + HTTP/SSE bridge and frontend contract
- [x] Extract legacy context, remove the bulk
- [x] Arena: seed vs three rivals, cross-exam, vote-off, brief, autopsy
- [x] Live retro web console, Scout Wire, threaded follow-ups
- [x] Live ChronoScouts + market/pricing evidence in arena prompts
- [x] Per-role model routing + automatic provider fallback
- [x] Provider status badges, role drawer, Markdown brief export
- [x] Phone/tablet companion shell at `/m`
- [ ] Full season: eight-character roster, user-built persona, escalation arc
- [ ] Private and duo sessions, and the cross-remark engine
- [ ] Optional embedding recall across sessions

## Why star it

Because the whole thing is a vertical slice: one developer, a phone, a real
problem, and a repo you can read in a sitting. If it kills one bad idea cheaply —
or briefs one good build in five turns — star it, open an issue with a transcript,
or send a PR against the contract.

Built by [@BleakNarratives](https://github.com/BleakNarratives) (Michael Talbert,
Wellington, Kansas). Originally written for Android/Termux with local Ollama.
