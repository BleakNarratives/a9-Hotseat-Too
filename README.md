<p align="center">
  <img src="assets/hotseat-banner.svg" alt="Hotseat-Too Banner" width="100%" />
</p>

# Hotseat-Too

**Hotseat-Too** is a multi-persona AI pressure-cooker, debate arena, and agentic orchestration runtime built by [@BleakNarratives](https://github.com/BleakNarratives). Put ideas, code, or live prompts into the hot seat against specialized personas, persistent SQLite memory (`memory.db`), and local/cloud model backends.

---

## Architecture & Engines

Hotseat-Too unifies three evolutionary tracks into one modular runtime:

| Engine Mode | Heritage | Role |
| :--- | :--- | :--- |
| **`classic`** | `hotseat.py` + `Mels/` | Rapid terminal pressure-testing & multi-persona cross-examination |
| **`v2`** | `hotseat_v2/app.py` | Interactive web/HTML arena with live persona switching & session logs |
| **`v3`** | `hotseat_v3.py` + `hotseat_claude.sh` | Agentic runner with Vertical AI, Ollama / DeepSeek-Coder, and CLI orchestration |

---

## Security & Secret Management

* **Zero Hardcoded Secrets:** All provider keys (`OPENROUTER_API_KEY`, etc.) are resolved at runtime via `vault_loader.py` from `~/.concierge/vault.json` or injected environment variables.
* **Persistent State:** Session transcripts and entity recall are stored locally in `memory.db` (SQLite) and `sessions.log`.

---

## Roadmap

- [x] Consolidate Classic, v2 Web, and v3 Agent implementations
- [x] Route all API credentials through `~/.concierge/vault.json`
- [ ] Unify `hotseat_core/` engine dispatcher & schema migrations (Copilot Coding Agent)
- [ ] Expose NDJSON / HTTP event bridge (`hotseat_core/bridge.py`)
- [ ] Spin up **FreeBuff** purple-screen CLI/Web frontend
