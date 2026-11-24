# Hotseat-Too consolidation map (initial remote audit)

**Audit basis:** repository tree at commit `34f53dc3b928f048bdec4a17966560dd1218a0cc` on `main`.

**Safety:** This is an inventory and comparison only. No existing files were changed, moved, or deleted.

## Important digest note

The identifiers below are Git blob object IDs from the repository tree, **not SHA-256 digests**. Equal Git blob IDs prove byte-for-byte identical file contents, so they reliably identify exact duplicates; different IDs mean the contents differ (or at least that the blob is different). The remote repository tools available for this audit expose Git blob IDs and file text, but do not execute a SHA-256 pass over every checkout file. Therefore this initial map does not mislabel Git IDs as SHA-256. A local SHA-256 inventory remains a verification item before any consolidation decisions that depend on the requested digest report.

## Exact duplicate groups found

| Git blob ID | Identical paths |
| --- | --- |
| `119d829f385d8418b2fdbef90a26473a1a4ce02f` | `Hot-Seat/manifest.json`, `hotseat/MANIFEST.json`, `hotseat_v2/MANIFEST.json` |
| `ece378a9c1adf9f3c279920f63431c1ff7db5b71` | `hotseat_v2/Hotseat.txt`, `hotseat_v2/Hotseat_122005.txt`, `hotseat_v2/hotseat/archive/Hotseat.txt`, `incoming/Loosies/Hotseat.txt`, `incoming/projects_hotseat/docs/Hotseat.txt`, `incoming/projects_hotseat/hotseat/Mels/Hotseat.txt` |
| `1c680283dd33d3e9f99d0a1845ed153a669922d6` | `hotseat_v2/hotseat_handoff.md`, `incoming/Loosies/hotseat_handoff.md`, `incoming/projects_hotseat/docs/hotseat_handoff.md`, `incoming/projects_hotseat/hotseat/Mels/hotseat_handoff.md` |
| `d475afeae6ec9d7ed496d050df8ce3a1b7464ad4` | `Hot-Seat/runbook.txt`, `runbook.txt`, `incoming/projects_hotseat/hotseat/runbook.txt` |
| `840503043402646b913eda2eb17ec138b9b887df` | `incoming/bin/hotseat_v3.py`, `incoming/core_framework_bin/hotseat_v3.py` |
| `e1b8c42ddeb2a4a98a69ff0b3eadd059d74fb030` | `incoming/projects_hotseat/hotseat/hotseat/hotseat3.py`, `incoming/projects_hotseat/hotseat3.py` |
| `2f445125b4b72d5855f45207e39924e06c715556` | `hotseat_v2/hotseat/personas.py`, `incoming/projects_hotseat/hotseat/Mels/personas.py` |
| `ce4c201fa1562e86c3ae781ab796ea05ba9b7ee9` | `incoming/docs/hotseat_veetical_ai_ollama_ds_coder.txt`, `incoming/export/hotseat_veetical_ai_ollama_ds_coder.txt` |
| `c5a4ef773deb57a1a2eda79e4c286574e3156f0c` | `hotseat_v2/hotseat/archive/Hotseat.txt` (same content as the six-path group above; Git tree reports this path's blob as `ece378a9c1adf9f3c279920f63431c1ff7db5b71`; see correction below) |

**Correction:** the preceding row is intentionally called out as a tree-reading discrepancy: the recursive tree reports `hotseat_v2/hotseat/archive/Hotseat.txt` with blob `ece378a9c1adf9f3c279920f63431c1ff7db5b71`, while `c5a4ef...` belongs to the `hotseat_v2/hotseat` directory tree, not a file. It is not a separate duplicate group.

Other exact duplicate metadata/files visible in the tree:

| Git blob ID | Identical paths |
| --- | --- |
| `86536df229ecac7829b02b9096763dcec77adabc` | root `sessions.log` only |
| `90e095b0491b1995794c204781f3390a788c8483` | `hotseat/sessions.log` only |
| `a9e1f926f24ceef5976eab5c9faef57f964465cb` | `hotseat_v2/hotseat/sessions.log` only |
| `343176a54cb652f181348e0e6614c82bdf6d4213` | root `memory.db` only |
| `cd9fae295f8cd25fe8de5cc57b0aed4129eaf42f` | `hotseat/memory.db` only |
| `4838d0e358cb095c9ee8eb37b4a2d5bb3915ff10` | `hotseat_v2/hotseat/memory.db` only |
| `1122595841dad443623507eeede5c0a5105400a4` | `incoming/projects_hotseat/hotseat/memory.db` only |

“Only” means no other matching path is visible in the repository tree with that same blob ID; it does not imply the file has no equivalent elsewhere outside the repository.

## Requested core implementation comparison

| Implementation | What the inspected code does | Consolidation notes |
| --- | --- | --- |
| `hotseat_v2/app.py` | Gradio/OpenRouter debate UI; three skeptic calls followed by a volunteer response; JSON transcript saved under `~/hotseat_v2/logs`. | Depends on Gradio, Requests, and `vault_loader`; API key is loaded at import time. No HTTP timeout or explicit request exception handling in the inspected call. |
| `hotseat_v2/app_v2_maybe_idk.py` | Same Gradio/OpenRouter flow and model mapping as `app.py`. | Diverged sibling, not an exact duplicate. It adds `time.sleep(1)` between skeptics and has small prompt/UI/logging differences. Both should share a provider/client layer, while preserving their modes and UI behavior. |
| `hotseat_v2/hotseat/hotseat.py` | Local Ollama CLI with Audrey, Claib, Vertical AI; SQLite session/topic history; optional WebSocket server; synchronous streaming callbacks. | “Classic” engine candidate. WebSocket handler duplicates session orchestration instead of using the normal runner; hard-coded home paths and models should become configuration. |
| `hotseat_v2/hotseat/v3/app.py` | Minimal FastAPI endpoint that lists a caller-supplied directory. | Not a v3 conversational engine; it exposes filesystem listing and allows broad CORS. Do not treat it as the source for the agent runner or carry this endpoint forward without a deliberate security redesign. |
| `incoming/bin/hotseat_v3.py` | Five-role tribunal using a local Node `puter_bridge.js` subprocess, then a Fixer close. | Exact duplicate at `incoming/core_framework_bin/hotseat_v3.py`. Depends on an external, hard-coded bridge path and does not check subprocess return status. Distinct from the Ollama v3 persona-panel implementation. |
| `incoming/projects_hotseat/hotseat/hotseat/hotseat3.py` | Local Ollama Marlowe/Priya/Zero panel, duo and private sessions, SQLite memory, text logs, interactive CLI. | Exact duplicate at `incoming/projects_hotseat/hotseat3.py`. Distinct v3 flavor; uses hard-coded model names/home paths and catches some errors broadly. |
| `incoming/projects_hotseat/hotseat/Mels/hotseat.py` | Audrey/Claib/Vertical local Ollama CLI/WebSocket flow. | Diverged from `hotseat_v2/hotseat/hotseat.py`; main visible difference is Audrey model routing (`zane-preacher:latest` rather than `deepseek-r1:1.5b`). Same personas module is byte-identical to the v2 copy. |
| `incoming/projects_hotseat/hotseat_claude.sh` | Termux shell loop calling Groq’s chat completions endpoint. | Separate single-advisor workflow, not an Ollama runner. Requires `GROQ_API_KEY`, `curl`, `python3`, and network access. Preserve as a distinct v3 adapter if retained; do not silently merge its provider semantics into local Ollama. |

## Manifest, persona, database, and log inventory

| Path | Git blob ID | What can be established from this remote audit |
| --- | --- | --- |
| `manifest.json` | `6b39970e50ae02f65cdaaf49e469da4a92b4df00` | Root metadata manifest; `meta` and `runbook` objects, empty entrypoints/commands/env/notes. |
| `Hot-Seat/manifest.json`, `hotseat/MANIFEST.json`, `hotseat_v2/MANIFEST.json` | `119d829f385d8418b2fdbef90a26473a1a4ce02f` | Exact same small `type`/`status` schema across three differently cased/named locations. |
| `incoming/projects_hotseat/hotseat/manifest.json` | `64c0811df65c62f8d522bfdcbe3cea2c7ae582a1` | Diverged metadata manifest; has a Python language count and same general `meta`/`runbook` shape as root, but different values. |
| `hotseat_v2/hotseat/personas.py`, `incoming/projects_hotseat/hotseat/Mels/personas.py` | `2f445125b4b72d5855f45207e39924e06c715556` | Exact duplicate persona module: Audrey/Claib/Vertical prompts plus model, token, round, and speaker metadata. |
| `incoming/projects_hotseat/hotseat/hotseat/personas.py` | `1e992ecde0082b118f155da7752cfc7e88d6c81b` | Separate persona file, contents/schema not inspected in this pass. |
| `memory.db` | `343176a54cb652f181348e0e6614c82bdf6d4213` | Unique binary SQLite blob. Its actual tables/columns cannot be inferred safely from the Git tree. |
| `hotseat/memory.db` | `cd9fae295f8cd25fe8de5cc57b0aed4129eaf42f` | Unique binary SQLite blob; schema inspection still needed. |
| `hotseat_v2/hotseat/memory.db` | `4838d0e358cb095c9ee8eb37b4a2d5bb3915ff10` | Unique binary SQLite blob; schema inspection still needed. |
| `incoming/projects_hotseat/hotseat/memory.db` | `1122595841dad443623507eeede5c0a5105400a4` | Unique binary SQLite blob; schema inspection still needed. |
| `sessions.log` | `86536df229ecac7829b02b9096763dcec77adabc` | Unique root log blob; content/schema not inspected in this pass. |
| `hotseat/sessions.log` | `90e095b0491b1995794c204781f3390a788c8483` | Unique log blob; content/schema not inspected in this pass. |
| `hotseat_v2/hotseat/sessions.log` | `a9e1f926f24ceef5976eab5c9faef57f964465cb` | Unique log blob; content/schema not inspected in this pass. |

## Initial architecture recommendation

1. Keep the three materially different families separate behind a common dispatcher: classic Audrey/Claib/Vertical Ollama; v2 Gradio/OpenRouter; and v3 workflows (Marlowe/Priya/Zero Ollama, tribunal subprocess, and Groq shell adapter). Do not combine them merely because they share the “v3” label.
2. Make configuration explicit and optional-dependency-friendly. Local Ollama should remain usable without cloud credentials; OpenRouter and Groq keys must be read only when those adapters are selected.
3. Treat each existing SQLite database as read-only source material until its tables and rows are inspected and migration tests are written. Back up before any conversion. Preserve JSON/text logs unchanged.
4. Restrict any future bridge to loopback by default, avoid arbitrary path listing, and document authentication/origin behavior before exposing it beyond localhost.
5. Keep original trees in place during the first implementation and add tests around dispatcher, persona selection, storage compatibility, and event output before archiving anything.

## Items still required for the issue’s full requested audit

- Run actual SHA-256 over every tracked `.py`, `.sh`, `.json`, `.md`, and `.txt` file (the blob IDs above are exact-duplicate fingerprints, not the requested digest format).
- Inspect every persona/manifest and parse every JSONL/log file, recording field-level differences and malformed rows.
- Open each SQLite database read-only and record `sqlite_master` plus column layouts before proposing migrations.
- Review the full long source files and test dependencies/runtime assumptions; this pass is an initial implementation comparison, not a validated refactor plan.

No existing file was deleted, renamed, or overwritten in this audit.
