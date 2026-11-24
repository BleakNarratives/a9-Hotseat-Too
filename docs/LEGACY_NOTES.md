# Legacy notes

The repository used to carry four overlapping trees: `Hot-Seat/`, `hotseat/`,
`hotseat_v2/`, and `incoming/`. They were read on 2026-11-24, the durable ideas
were extracted into `hotseat_core/` and this note, and the trees were removed
from the working tree. They remain in Git history — nothing is lost.

## Recovering an original

```bash
git ls-tree -r --name-only e96909a | grep -E 'hotseat_v2|incoming|Hot-Seat'
git show e96909a:hotseat_v2/app.py
git show e96909a:incoming/projects_hotseat/hotseat/hotseat/hotseat3.py
```

`406bb2c` and `e96909a` both contain the pre-prune layout.

## What each tree actually was

| Tree | Content | Verdict |
| :--- | :--- | :--- |
| `Hot-Seat/` | Three-line metadata manifest and a joke runbook | No code; dropped |
| `hotseat/` | Metadata, three SQLite DBs, three session logs | Data only; new store migrates such DBs |
| `hotseat_v2/` | Gradio/OpenRouter debate, Ollama CLI, personas, an early FastAPI directory lister, a 383-line text dump of `hotseat.py` | Debate + classic casts kept; lister dropped |
| `incoming/` | `hotseat3.py` personal panel with cross-remarks and private/duo sessions, `hotseat_v3.py` five-role tribunal over a Node bridge, a Groq `curl` shell advisor, persona drafts, terminal logs | Panel/tribunal kept; transport replaced |

Most of the code had hard-coded Termux paths, duplicated itself several times,
and swallowed exceptions. The value was in the casts and the session shapes, not
the implementations.

## Voices that were worth keeping

Now tightened in `hotseat_core/personas.py`:

* **Classic** — Dame Audrey (auditor), Claib (market), Vertical AI (closer).
* **v2** — three skeptics and a volunteer defending the idea.
* **v3 panel** — Marlowe (witness), Priya (systems), Zero (closer, under 80 words).
* **v3 tribunal** — Adversary, Voice of Reason, Whistleblower, Evangelist, Fixer.

The old prompts addressed “Michael” directly and repeated the same biography in
every system message. The new ones speak to “the person in the hot seat”, which
makes the tool usable by anyone without losing the voice.

## The show concept

From `hotseat_handoff.md`: **Drawn Together meets Survivor** — a cast with
backstories, chemistry, an escalation arc, a vote-off, and a closing dismissal
that is also the most useful line in the session.

Eight-character roster (all original, no IP):

| Character | Hook |
| :--- | :--- |
| Wendell | Wrong analogy, technically correct, overly serious |
| Gloria | Eastern European, words slightly wrong, wiser than the room |
| Carl | Catastrophizes, walks it back, lands on the right answer |
| Barb | Warm, maternal, will help you move a body |
| General Vance | Incompetent megalomaniac; the plan is terrible |
| Dale | Quiet, methodical, asks the one question that matters |
| Felix | Agent of chaos; accelerates the collapse on purpose |
| User-built | Four-question Madlibs persona |

Escalation arc: help → bicker → fight → someone walks out → silence → “you’re
gonna be fine, stop making everything about yourself.”

Pairing chemistry (Wendell+Carl, Gloria+Wendell, Barb+Felix, Vance+Dale, Carl+Barb)
and a `temperature` per character were specified. The arena format now ships as
`arena` mode (four contenders, cross-exam, vote-off, brief, autopsy). The
eight-character roster, escalation arc, and user-built persona remain the
persona-pack backlog; they should stay optional rather than bloat the default
session.

## Session shapes worth reviving

* **Cross-remark** — after a turn, the next persona replies to the previous
  speaker in 1–2 sentences before giving its own take. Prevents three monologues.
* **Private session** — one persona, direct back-and-forth, own log.
* **Duo session** — two personas, one reacts to the other.
* **Menu** — a text menu instead of flags. The current CLI uses flags and a REPL;
  a frontend covers the menu case.

Panel, tribunal, brief, and arena turn structures exist today; private and duo
sessions and the cross-remark engine are roadmap.

## Model routing learned on a phone

From the Termux logs (`ollama list` on a Motorola):

| Model | Size | Use |
| :--- | :--- | :--- |
| `deepseek-r1:1.5b` | ~1.1 GB | reasoning, precise |
| `qwen2.5-coder:1.5b` | ~1.0 GB | systems, code |
| `deepseek-coder:1.3b` | ~776 MB | short, code |
| `llama3.2:1b` | ~1.3 GB | general voice |
| `tinyllama:latest` | ~637 MB | closers, hard token caps |

Avoid 3B+ models on low-RAM phones; they were the source of OOM kills. The
defaults in `personas.py` follow this table.

## Failures already paid for

* `sqlite3.OperationalError: table sessions has no column named mode` — fixed by
  the migration in `storage.py` (adds missing columns, never drops tables).
* Hard-coded `~/hotseat`, model names, and ports — now config + manifest + env.
* WebSocket server bound to `0.0.0.0` with no auth — bridge is loopback-only and
  requires a token off-loopback.
* FastAPI `/list/{dir}` with `allow_origins=["*"]` — arbitrary filesystem listing
  and wildcard CORS were dropped, not ported.
* Node `puter_bridge.js` subprocess with an unverified return code — replaced by a
  provider layer; any HTTP bridge can be pointed at instead.
* Groq `curl` shell advisor — covered by the `groq` provider.
* Gradio duplicate app (`app.py` / `app_v2_maybe_idk.py`) — one `v2` engine.
* Bare `except: pass` around model calls and logging — provider errors surface as
  `error` events; logging failures stay silent by design.

## Removed on purpose

The ZIP archive, four legacy SQLite files, duplicate `Hotseat.txt`/handoff copies,
the 383-line source dump, and the terminal transcript. All recoverable from Git;
none were needed by the new runtime.
