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
</p>

**Hotseat-Too** is a local-first AI pressure cooker: a small cast of sharply drawn
personas interrogates an idea, a decision, or a build until something true falls
out. It runs on a phone in Termux with Ollama, on a laptop with zero dependencies,
or against any cloud model with your own key.

One session. Structured turns. A closer who speaks last and short. Persistent
memory. Structured events for your own frontend. No phases to schedule, no
document chain to carry between chats.

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

Keys come from the environment or `~/.concierge/vault.json` via
[`vault_loader.py`](vault_loader.py). Nothing is hardcoded, and no key is read for
a provider you did not select.

```bash
export OPENROUTER_API_KEY="..."
python -m hotseat_core --provider openrouter --mode v2 "my idea" \
  --statement "four weeks, no budget."
```

| Provider | Notes |
| :--- | :--- |
| `auto` | Probe local 9router → first configured cloud key → OpenRouter default |
| `ollama` | Local, no key; `OLLAMA_BASE_URL` to override |
| `9router`, `ai_gateway` | Local OpenAI-compatible routers |
| `openrouter`, `anthropic`, `mistral`, `cerebras`, `groq` | Cloud; env or vault |
| `demo` | Offline canned replies for frontends, docs, and tests |

## Bring your own frontend

A stdlib HTTP + SSE bridge, no scraping stdout, no Gradio:

```bash
python -m hotseat_core --serve --provider demo
curl -s -XPOST localhost:8765/sessions \
  -H 'Content-Type: application/json' \
  -d '{"mode":"bmad","topic":"ship it or bin it?"}'
curl -N localhost:8765/sessions/<session_id>/events
```

Modes, personas, providers, and history are queryable; personas are editable for
the running process; operator notes can be injected between turns; sessions can
be stopped. Events: `session_start`, `status`, `token_chunk`, `persona_turn`,
`memory_saved`, `error`, `session_end`.

Full schemas and a working EventSource client:
**[FRONTEND_CONTRACT.md](FRONTEND_CONTRACT.md)**.

The CLI streams the same events:

```bash
python -m hotseat_core --mode bmad --json-stream "the thing" | jq -r 'select(.type=="persona_turn") | .content'
```

## Layout

```
hotseat_core/
  config.py      manifest + env resolution, no side effects on import
  personas.py    casts, routing, limits, overrides
  providers.py   urllib transport (OpenAI-compatible, Anthropic, Ollama) + demo
  tuning.py      composable style directives and sampling; filler cleanup
  storage.py     SQLite memory + JSONL log, in-place legacy migration
  engines/       classic · v2_web · v3_agent · bmad
  runtime.py     orchestration, events, persistence
  cli.py         python -m hotseat_core
  bridge.py      HTTP/SSE/NDJSON adapter
tests/           33 tests, stdlib only
docs/            extracted legacy context, decisions, and the unbuilt show concept
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

Covered: manifest/env precedence, persona resolution and overrides, legacy SQLite
migration, JSONL and legacy logs, every engine including `bmad`, stop and
injection semantics, NDJSON output, HTTP endpoints, token auth, and the
loopback-binding guard. CI runs on Python 3.10–3.12.

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
- [ ] FreeBuff / web frontend built against the contract
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
