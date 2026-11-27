<div align="center">
  <a href="[https://bleaknarratives.github.io/a9-Hotseat-Too/](https://bleaknarratives.github.io/a9-Hotseat-Too/)">
    <img src="assets/hotseat-banner.svg" alt="The Hot Seat — Live Adversarial Boardroom" width="100%" />
  </a>

  <p>
    <a href="[https://github.com/sponsors/BleakNarratives](https://github.com/sponsors/BleakNarratives)">
      <img src="[https://img.shields.io/badge/Sponsor-Buy%20the%20Dev%20a%20Hot%20Meal-e63946?style=for-the-badge&logo=githubsponsors&logoColor=white](https://img.shields.io/badge/Sponsor-Buy%20the%20Dev%20a%20Hot%20Meal-e63946?style=for-the-badge&logo=githubsponsors&logoColor=white)" alt="Sponsor BleakNarratives" />
    </a>
    <img src="[https://img.shields.io/badge/Runtime-Local%20Ollama%20%7C%20Gemini%20%7C%20Cloud-e9c46a?style=for-the-badge](https://img.shields.io/badge/Runtime-Local%20Ollama%20%7C%20Gemini%20%7C%20Cloud-e9c46a?style=for-the-badge)" alt="Runtime" />
    <img src="[https://img.shields.io/badge/UI-3D%20Spatial%20SSE%20Arena-4cc9f0?style=for-the-badge](https://img.shields.io/badge/UI-3D%20Spatial%20SSE%20Arena-4cc9f0?style=for-the-badge)" alt="UI" />
  </p>

  <h3>One idea. Five adversarial voices. Zero sycophancy.</h3>
  <p>
    A local-first multi-agent stress-testing arena built for phones, tablets, Chromebooks, and desktops.
    Pitch an idea, dial the heat from <strong>0 (clinical)</strong> to <strong>11 (unhinged)</strong>, and watch distinct personas cross-examine it live in a 3D spatial pit.
  </p>
</div>

---

> **Working on this next?** Read [HANDOFF.md](HANDOFF.md) for the current
> architecture, verified state, known blockers, and deployment/cron steps.

## Casts & Arena Modes

<details open>
<summary><strong>Gemini Pantheon (Native Multi-Lens Reasoning)</strong></summary>
<br/>

* **Gemini Prime:** Systems & leverage — finds the second-order wedge that turns a toy into an indispensable tool.
* **Gemini Red-Team:** Adversarial stress-test — exposes token burn, latency traps, and distribution dead-ends.
* **Gemini Prism:** Lateral synthesis — spots adjacent markets and 10x simpler UX loops.
* **Gemini Gavel:** The closer — distills the room into three ranked moves for the next 48 hours.
</details>

<details>
<summary><strong>The Arena (Your Idea vs. Three Rivals)</strong></summary>
<br/>

* **The Producer:** Builds four fair contenders (your seed + cheaper, premium, and niche-wedge rivals).
* **The Critic:** Cross-examines every contender for missing evidence and fatal assumptions.
* **The Foreman:** Ranks on desirability, viability, defensibility, and speed—no ties allowed.
* **The Architect:** Slices the winning contender into a concrete vertical build.
* **The Coroner:** Writes the sub-150-word autopsy on why the seed lived or died.
</details>

<details>
<summary><strong>Classic Audit · Debate · Personal Panel · Tribunal · BMAD-Lite · Custom Call Sheet</strong></summary>
<br/>

* **Classic:** Dame Audrey (retired British auditor), Claib, and Vertical AI.
* **v2 Debate:** Three ruthless skeptics vs. one honest volunteer defender.
* **v3 Personal Panel & Tribunal:** Marlowe, Priya Nair, and Zero — or a 5-seat decision tribunal ending with The Fixer.
* **BMAD-Lite:** Analyst -> PM -> Architect -> Builder -> QA in a single pass.
* **Custom Call Sheet:** Mix and match up to 5 personas from any cast in your own turn order.
</details>

---

## Quickstart

    git clone [https://github.com/BleakNarratives/a9-Hotseat-Too.git](https://github.com/BleakNarratives/a9-Hotseat-Too.git)
    cd a9-Hotseat-Too
    pip install -r requirements.txt
    hotseat --serve --port 8000

Open `http://localhost:8000` in your browser (attach `?token=YOUR_TOKEN` if auth is enabled).

---

## Provider Key Rings & Quiet Fallback

Put as many free-tier keys as you have in `.env` (or the host's environment). The
server reads a ring per provider and never prints a key value:

```sh
OPENROUTER_API_KEY=first-key
OPENROUTER_API_KEY_2=second-key
OPENROUTER_API_KEY_3=third-key
OPENROUTER_KEYS=fourth-key,fifth-key
```

The same pattern works for every provider (`GROQ_API_KEY_2`, `CEREBRAS_KEYS`,
etc.). Short rate limits cool down only that key; daily or billing limits park it
for the session. Successful turns rotate through the ring, and failures move to
the next key, model, or provider without putting a status code in the room.

Optional controls:

* `HOTSEAT_SEAT_ROUTER=1` rotates the session's starting provider across the
  active pools. It is on in `render.yaml` and off by default elsewhere.
* `OPENROUTER_MODEL` (or the matching `GROQ_MODEL`, `CEREBRAS_MODEL`, etc.)
  sets that provider's primary model.
* `OPENROUTER_FALLBACK_MODELS` accepts a comma-separated model ring.

Technical failures are logged on the server. The room waits, retries, and keeps
each character seat filled instead of rendering `ERROR 4xx`, a blank turn, or a
provider/model label in the spoken transcript.

## Support the Project

Building offline-resilient, low-RAM multi-agent tools solo. If **The Hot Seat** saved you from building the wrong feature—or roasted your pitch into a better product—consider sponsoring the repo or fueling the next build:

* **GitHub Sponsors:** [github.com/sponsors/BleakNarratives](https://github.com/sponsors/BleakNarratives)
