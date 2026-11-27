# The Hot Seat — Engineering Handoff

Last updated: 2026-11-27

Branch: `main`

Base: remote commit `c7b1e75` (five commits after `91a0fc0`)

Deployment: **not deployed yet**

## What this is

A dependency-free Python bridge (`hotseat_core/`) with a 3D SSE arena frontend
(`web/`). The room streams persona turns over Server-Sent Events and can run on a
local model, a cloud provider, or the deterministic demo provider. Production is
a long-lived Docker web service; `render.yaml` is the intended free-tier host.

## Where behavior lives

| Area | File |
| :--- | :--- |
| Provider specs, key rings, cooldowns, model/provider fallback | `hotseat_core/providers.py` |
| Per-turn retries and in-character house fallback | `hotseat_core/engines/base.py` |
| Session routing, metadata, persistence events | `hotseat_core/runtime.py` |
| HTTP/SSE adapters and scout-prompt compaction | `hotseat_core/bridge.py` |
| Final prose cleanup | `hotseat_core/tuning.py` |
| Role pools for the optional session router | `hotseat_core/moe_router.py` |
| Prompt compression | `hotseat_core/compact_wire.py` |
| Main 3D room | `web/table.js`, `web/table.html`, `web/table.css` |
| Mobile companion | `web/mobile.js`, `web/mobile.html` |
| War Room console | `web/app.js`, `web/index.html` |

## Current provider behavior

- A provider can hold a ring of keys:
  - `PROVIDER_API_KEY`
  - `PROVIDER_API_KEY_2` through `_9`
  - `PROVIDER_KEYS=key1,key2` (also newlines/semicolons)
  - `PROVIDER_API_KEYS=...`
- Successful turns rotate to the next key/provider instead of pinning all load
  to the first working key.
- A short `429` cools down only that key for its `Retry-After` window; a
  daily/billing limit parks it for the session.
- Model failures try the provider's default or `PROVIDER_FALLBACK_MODELS` before
  moving to the next provider.
- `HOTSEAT_SEAT_ROUTER=1` picks a starting provider/model per session from the
  active role pools. It is enabled in `render.yaml` and off by default locally.
- Auto mode with no cloud keys now opens with the demo provider instead of a
  credential error.

## Error and output contract (do not regress)

- A character turn retries quietly, then falls back to an in-character house
  reply. Never render a blank persona card or `[no response]`.
- Provider status codes, provider names, model names, and key labels stay in the
  server log and API metadata. They do not appear in room prose, speech, or
  downloaded transcripts.
- Provider/model labels are allowed only in the setup console where the operator
  must choose them.
- Separator lines (`===`, `---`, etc.), spaced equals signs, and trailing
  ellipses are stripped before display and read-aloud.
- The old demo footer and `VERDICT // FALLBACK` label are gone.
- `status` events mark the active speaker but must not be rendered as that
  persona's dialogue.

## Verification already run

```sh
python3 -m unittest discover -s tests -t .
# Ran 99 tests ... OK

python3 -m py_compile hotseat_core/providers.py hotseat_core/runtime.py \
  hotseat_core/bridge.py hotseat_core/engines/base.py hotseat_core/moe_router.py
node --check web/app.js
node --check web/table.js
node --check web/mobile.js
```

Preview was restarted successfully. Demo classic (3 turns) and arena (5 turns)
sessions completed with no `HTTP`, `ERROR`, `===`, `[no response]`, `Provider:`,
or `Model:` strings in the transcript.

## Known blockers and limitations

1. **Gemini key returns HTTP 401** (`API key not valid`) and **Mistral returns
   HTTP 402** (no API budget). They are handled by fallback, but should be
   replaced/activated or left blank in production.
2. **Render is not deployed.** There is no public service URL, so the
   cron-job.org keepalive has not been created.
3. Cooldowns are held by the process's provider client instances; they are not a
   shared cross-process registry. A restart forgets them.
4. The session router picks one starting route per session; it does not route
   every individual persona to a different provider.
5. The UI was checked through served assets and live demo sessions, not a
   full browser screenshot/e2e run.

## Next steps, in order

1. Deploy the Render Blueprint:
   `https://render.com/deploy?repo=https://github.com/BleakNarratives/a9-Hotseat-Too`
2. Set `HOTSEAT_TOKEN` (letters/digits only, because it travels in a query
   string), `HOTSEAT_PROVIDER=auto`, `HOTSEAT_SEAT_ROUTER=1`, and the working
   provider keys. Leave Gemini/Mistral blank until their accounts are fixed.
3. After the public URL exists, create the keepalive:

   ```sh
   python3 -m hotseat_core --cron-setup --cron-url https://<service>.onrender.com
   ```

   `CRONJOB_API_KEY` is only needed by the machine running that command; do not
   put it on Render. The keepalive is a GET to the public `/` every 10 minutes.
4. Add second keys for OpenRouter/Groq/Cerebras and verify rotation across two
   sessions; the ring parser already supports them.
5. Optional hardening: move key cooldowns into a small shared registry so a
   restart or a new session does not immediately hit a key that just returned
   429.
6. Optional UI verification: add a small browser/e2e check for the 3D arena,
   mobile error listener, and read-aloud cleanup.

## Deployment notes

- Render free sleeps after 15 minutes idle and uses nearly all 750 monthly
  instance hours when kept warm by the 10-minute cron.
- Netlify/Vercel are not suitable: this app needs one long-lived process for SSE,
  in-memory sessions, and SQLite.
- `render.yaml` prompts for provider keys at Blueprint creation. Additional
  ring keys can be added later in the Render dashboard.
- Never print or commit provider key values. Use the host's environment UI.

## Repository hygiene

- Preserve the current 3D arena layout; do not restore the older table markup.
- When remote adds a new mode, update the hardcoded mode-set assertions in
  `tests/test_bridge.py` and the roster count in `tests/test_personas.py`.
- Keep the provider/model cleanup behavior in both frontend and backend when
  adding a new transcript surface.
