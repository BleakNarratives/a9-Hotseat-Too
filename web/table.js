/* THE TABLE — 3D Spatial Stage wired to hotseat_core/bridge.py */

(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const room = $("#room");
  const castBox = $("#cast");
  const caseForm = $("#case-file");
  const caseInput = $("#case-input");
  const followForm = $("#follow-up");
  const followInput = $("#follow-input");
  const strip = $("#strip");
  const stamp = $("#stamp");
  const note = $("#live-note");
  const gavel = $("#gavel");
  const plaque = $("#house-plaque");
  const formatTrigger = $("#format-trigger");
  const castDrawer = $("#cast-drawer");
  const drawerClose = $("#drawer-close");
  const programName = $("#program-name");
  const programList = $("#program-list");
  const callCount = $("#call-count");
  const callList = $("#call-list");
  const dial = $("#dial");
  const dialValue = $("#dial-value");
  const dialLabel = $("#dial-label");
  const dialRoll = $("#dial-roll");
  const voiceButton = $("#voice");
  const micButton = $("#case-mic");
  const caseHint = $("#case-hint");
  const wire = $("#wire");
  const wireDrawer = $("#wire-drawer");
  const wireClose = $("#wire-close");
  const wireCount = $("#wire-count");
  const wireNote = $("#wire-note");
  const wireList = $("#wire-list");
  const speechStage = $("#speech-stage");
  const activeSpeaker = $("#active-speaker");
  const activeRole = $("#active-role");
  const activeSpeech = $("#active-speech");
  const replayBtn = $("#replay-btn");

  const EVENT_TYPES = [
    "session_start",
    "status",
    "token_chunk",
    "persona_turn",
    "operator_message",
    "iteration_start",
    "memory_saved",
    "error",
    "session_end",
  ];

  const ROLES = {
    producer: "builds four fair contenders",
    critic: "cross-examines every bet",
    foreman: "ranks them and swings the axe",
    architect: "slices the winner into a build",
    coroner: "writes the autopsy",
  };

  const FALLBACK_CAST = [
    { key: "producer", name: "The Producer", emoji: "🎬", color: "#e63946" },
    { key: "critic", name: "The Critic", emoji: "🔪", color: "#f4a261" },
    { key: "foreman", name: "The Foreman", emoji: "🔔", color: "#e9c46a" },
    { key: "architect", name: "The Architect", emoji: "📐", color: "#2a9d8f" },
    { key: "coroner", name: "The Coroner", emoji: "🥼", color: "#4cc9f0" },
  ];

  const PROGRAM = [
    { key: "arena", mode: "arena", variant: null, name: "The Arena", blurb: "your idea vs three rivals" },
    { key: "classic", mode: "classic", variant: null, name: "The Audit", blurb: "auditor, market read, closer" },
    { key: "v2", mode: "v2", variant: null, name: "The Debate", blurb: "three skeptics, one defence" },
    { key: "v3:panel", mode: "v3", variant: "panel", name: "The Panel", blurb: "witness, systems, closer" },
    { key: "v3:tribunal", mode: "v3", variant: "tribunal", name: "The Tribunal", blurb: "four roles, three ranked actions" },
    { key: "bmad", mode: "bmad", variant: null, name: "The Brief", blurb: "one pass, a build you can start" },
    { key: "gemini", mode: "gemini", variant: null, name: "Gemini Pantheon", blurb: "Prime, Red-Team, Prism, Gavel" },
    { key: "custom", mode: "custom", variant: null, name: "The Call Sheet", blurb: "your own cast, one turn each" },
  ];

  const CAST_SOURCES = [
    { mode: "arena" },
    { mode: "classic" },
    { mode: "v2" },
    { mode: "v3", variant: "panel" },
    { mode: "v3", variant: "tribunal" },
    { mode: "bmad" },
    { mode: "gemini" },
  ];

  const MAX_CAST = 5;

  const state = {
    cast: [],
    sessionId: null,
    since: 0,
    source: null,
    lines: {},
    openKey: null,
    active: false,
    done: false,
    transcript: "",
    freshPass: false,
    passSpeakers: new Set(),
    retries: 0,
    format: PROGRAM[0],
    roster: [],
    custom: [],
    customCast: [],
    dial: 7,
    voice: false,
    listening: false,
    houseProvider: "",
    demoPacing: false,
    turnQueue: [],
    turnTimer: null,
    pendingEnd: null,
  };

  function token() {
    return new URLSearchParams(window.location.search).get("token") || "";
  }

  function withToken(path) {
    const value = token();
    if (!value) return path;
    return path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(value);
  }

  function syncLinks() {
    document.querySelectorAll("[data-view-link]").forEach((link) => {
      const href = link.getAttribute("href");
      if (href) link.href = withToken(href);
    });
  }

  async function api(path, options) {
    const headers = { "Content-Type": "application/json" };
    if (token()) headers.Authorization = "Bearer " + token();
    const response = await fetch(withToken(path), { ...options, headers });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("Locked — attach ?token= to this URL.");
      }
      throw new Error((payload && payload.error) || "Bridge error (" + response.status + ").");
    }
    return payload;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  // ── Drawers ────────────────────────────────────────────────────────────────

  formatTrigger.addEventListener("click", () => {
    const open = castDrawer.hidden;
    castDrawer.hidden = !open;
    wireDrawer.hidden = true;
    formatTrigger.setAttribute("aria-expanded", String(open));
  });

  drawerClose.addEventListener("click", () => {
    castDrawer.hidden = true;
    formatTrigger.setAttribute("aria-expanded", "false");
  });

  wire.addEventListener("click", () => {
    const open = wireDrawer.hidden;
    wireDrawer.hidden = !open;
    castDrawer.hidden = true;
    wire.setAttribute("aria-expanded", String(open));
  });

  wireClose.addEventListener("click", () => {
    wireDrawer.hidden = true;
    wire.setAttribute("aria-expanded", "false");
  });

  // ── Program & Call Sheet ───────────────────────────────────────────────────

  function renderProgram() {
    programList.textContent = "";
    PROGRAM.forEach((entry) => {
      const button = el("button");
      button.type = "button";
      button.appendChild(el("strong", "", entry.name));
      button.appendChild(
        el("span", "", entry.mode === "custom" ? state.custom.length + " called" : entry.blurb)
      );
      if (entry.key === state.format.key) button.setAttribute("aria-current", "true");
      button.disabled = state.active;
      button.addEventListener("click", () => chooseFormat(entry));
      programList.appendChild(button);
    });
  }

  function memberFor(id) {
    const member = state.roster.find((entry) => entry.id === id);
    return member ? member.persona : null;
  }

  function renderCallSheet() {
    callList.textContent = "";
    callCount.textContent =
      state.custom.length + (state.custom.length >= MAX_CAST ? " / 5 MAX" : " CALLED");
    if (!state.roster.length) {
      callList.appendChild(el("span", "", "Roster unavailable."));
      return;
    }
    const groups = new Map();
    state.roster.forEach((member) => {
      if (!groups.has(member.group)) groups.set(member.group, []);
      groups.get(member.group).push(member);
    });
    const full = state.custom.length >= MAX_CAST;
    groups.forEach((members, group) => {
      const box = el("div", "call-group");
      box.appendChild(el("h3", "", group));
      members.forEach((member) => {
        const checked = state.custom.includes(member.id);
        const label = el("label", "call-member");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = member.id;
        input.checked = checked;
        input.disabled = state.active || (!checked && full);
        input.addEventListener("change", () => toggleMember(member.id, input.checked));
        label.appendChild(input);
        const swatch = el("span", "swatch");
        swatch.style.setProperty("--tone", member.persona.color || "#e9c46a");
        label.appendChild(swatch);
        label.appendChild(el("span", "", member.persona.name));
        if (!checked && full) label.dataset.off = "true";
        box.appendChild(label);
      });
      callList.appendChild(box);
    });
  }

  function syncCallSheet(cast, entry) {
    if (entry.mode === "custom") return;
    const ids = cast.map((persona) => entry.mode + ":" + persona.key);
    if (!ids.every((id) => state.roster.some((member) => member.id === id))) return;
    state.custom = ids;
    state.customCast = ids.map(memberFor).filter(Boolean);
    renderCallSheet();
  }

  function toggleMember(id, checked) {
    if (state.active) return;
    if (checked && state.custom.length >= MAX_CAST) return;
    if (!checked && state.custom.length <= 1) return;
    if (state.done) resetRoom();
    state.custom = checked
      ? state.custom.concat([id])
      : state.custom.filter((member) => member !== id);
    state.customCast = state.custom.map(memberFor).filter(Boolean);
    state.format = PROGRAM.find((entry) => entry.key === "custom") || state.format;
    programName.textContent = state.format.name;
    stamp.hidden = true;
    renderCast(state.customCast);
    renderProgram();
    resetWire();
    renderCallSheet();
  }

  async function loadRoster() {
    const results = await Promise.all(
      CAST_SOURCES.map(async (source) => {
        const query =
          "?mode=" +
          encodeURIComponent(source.mode) +
          (source.variant ? "&variant=" + encodeURIComponent(source.variant) : "");
        try {
          const data = await api("/personas" + query);
          return {
            source,
            label: (data && data.label) || source.mode,
            personas: (data && data.personas) || [],
          };
        } catch (error) {
          return null;
        }
      })
    );
    const roster = [];
    const seen = new Set();
    results.forEach((result) => {
      if (!result) return;
      const group = String(result.label).split(" — ")[0];
      result.personas.forEach((persona) => {
        const id = result.source.mode + ":" + persona.key;
        if (seen.has(id)) return;
        seen.add(id);
        roster.push({ id, group, persona });
      });
    });
    if (!roster.length) {
      FALLBACK_CAST.forEach((persona) => {
        roster.push({ id: "arena:" + persona.key, group: "Arena", persona });
      });
    }
    state.roster = roster;
    const arena = roster
      .filter((member) => member.id.startsWith("arena:"))
      .map((member) => member.id);
    state.custom = arena.length ? arena : roster.slice(0, 3).map((member) => member.id);
    state.customCast = state.custom.map(memberFor).filter(Boolean);
    renderCallSheet();
  }

  // ── Heat Dial (0–11) ───────────────────────────────────────────────────────

  function dialProfile(value) {
    const v = Number(value);
    if (v <= 2) {
      return { temperature: 0.3 + v * 0.05, max_tokens: 220, top_p: 0.85, frequency_penalty: 0.25, presence_penalty: 0, styles: ["terse"], label: "clinical" };
    }
    if (v <= 5) {
      return { temperature: 0.5 + (v - 3) * 0.075, max_tokens: 320, top_p: 0.9, frequency_penalty: 0.18, presence_penalty: 0, styles: ["nosyco"], label: "measured" };
    }
    if (v <= 8) {
      return { temperature: 0.75 + (v - 6) * 0.075, max_tokens: 460, top_p: 0.92, frequency_penalty: 0.1, presence_penalty: 0.05, styles: [], label: "loose" };
    }
    return { temperature: 1.0 + (v - 9) * 0.075, max_tokens: 620, top_p: 0.96, frequency_penalty: 0.05, presence_penalty: 0.12, styles: [], label: "unhinged" };
  }

  function renderDial() {
    state.dial = Number(dial.value);
    const profile = dialProfile(state.dial);
    dialValue.textContent = String(state.dial);
    dialLabel.textContent = profile.label;
    const glow = (0.15 + (state.dial / 11) * 0.55).toFixed(2);
    document.documentElement.style.setProperty("--heat-glow", `rgba(230, 57, 70, ${glow})`);
  }

  dial.addEventListener("input", renderDial);

  dialRoll.addEventListener("click", () => {
    dial.value = String(Math.floor(Math.random() * 12));
    renderDial();
    setIdleStatus("Dial rolled to " + state.dial + " (" + dialProfile(state.dial).label + ").");
  });

  // ── Voice Synthesis & Dictation ────────────────────────────────────────────

  let speechVoices = [];
  function loadVoices() {
    if (window.speechSynthesis) speechVoices = window.speechSynthesis.getVoices() || [];
  }
  if (window.speechSynthesis) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  } else {
    voiceButton.disabled = true;
  }

  function voiceFor(key) {
    const pool = (speechVoices.length ? speechVoices : window.speechSynthesis.getVoices() || []).filter(
      (voice) => (voice.lang || "").toLowerCase().startsWith("en")
    );
    if (!pool.length) return null;
    let hash = 0;
    for (const character of key) hash = (hash * 31 + character.charCodeAt(0)) % 100000;
    return {
      voice: pool[hash % pool.length],
      pitch: 0.78 + ((hash >> 3) % 5) * 0.09,
      rate: 0.94 + ((hash >> 5) % 3) * 0.06,
    };
  }

  function readAloud(key, text, interrupt) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance || !text) return;
    const spoken = String(text).replace(/[*_#`>]/g, "").replace(/\s+/g, " ").trim();
    if (!spoken) return;
    if (interrupt) window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(spoken.slice(0, 1400));
    const picked = voiceFor(key);
    if (picked) {
      utterance.voice = picked.voice;
      utterance.lang = picked.voice.lang;
      utterance.pitch = picked.pitch;
      utterance.rate = picked.rate;
    }
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeech() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  voiceButton.addEventListener("click", () => {
    if (!window.speechSynthesis) return;
    state.voice = !state.voice;
    voiceButton.setAttribute("aria-pressed", String(state.voice));
    voiceButton.textContent = state.voice ? "🔊" : "🔇";
    if (state.voice && window.SpeechSynthesisUtterance) {
      const primer = new SpeechSynthesisUtterance(" ");
      primer.volume = 0;
      window.speechSynthesis.speak(primer);
    }
    if (!state.voice) stopSpeech();
  });

  replayBtn.addEventListener("click", () => {
    if (state.openKey && state.lines[state.openKey]) {
      readAloud(state.openKey, state.lines[state.openKey], true);
    }
  });

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  if (!SpeechRecognition) {
    micButton.disabled = true;
  } else {
    micButton.addEventListener("click", () => {
      if (state.listening) {
        if (recognition) recognition.stop();
        return;
      }
      recognition = new SpeechRecognition();
      recognition.lang = navigator.language || "en-US";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.onstart = () => {
        state.listening = true;
        micButton.setAttribute("aria-pressed", "true");
        setIdleStatus("Listening… speak your directive.");
      };
      recognition.onresult = (event) => {
        let heard = "";
        for (let i = 0; i < event.results.length; i += 1) {
          heard += event.results[i][0].transcript;
        }
        caseInput.value = heard.trim();
      };
      recognition.onerror = () => {
        setIdleStatus("Mic unavailable — type your directive below.");
      };
      recognition.onend = () => {
        state.listening = false;
        micButton.setAttribute("aria-pressed", "false");
        if (caseInput.value.trim()) caseInput.focus();
      };
      try {
        recognition.start();
      } catch (error) {
        /* ignore double start */
      }
    });
  }

  // ── Scout Wire ─────────────────────────────────────────────────────────────

  function resetWire() {
    wire.hidden = true;
    wireDrawer.hidden = true;
    wireCount.textContent = "0";
    wireList.textContent = "";
  }

  function renderWire(scouts) {
    wire.hidden = false;
    wireList.textContent = "";
    if (!scouts) {
      wireCount.textContent = "0";
      wireNote.textContent = "SCOUT WIRE // NO REPORT";
      return;
    }
    const signals = Array.isArray(scouts.signals) ? scouts.signals : [];
    const anchors = Array.isArray(scouts.market_anchors) ? scouts.market_anchors : [];
    wireCount.textContent = String(signals.length + anchors.length);
    wireNote.textContent = `SCOUT WIRE // ${signals.length} SIGNALS · ${anchors.length} ANCHORS`;
    signals.slice(0, 4).forEach((s) => {
      wireList.appendChild(el("div", "wire-item", `[${s.source || "wire"}] ${s.title || "signal"}`));
    });
    anchors.slice(0, 4).forEach((a) => {
      wireList.appendChild(el("div", "wire-item", `PRICE ${a.competitor || "market"} — ${a.price || "unknown"}`));
    });
    if (!wireList.childElementCount) {
      wireList.appendChild(el("div", "wire-item", "Wire quiet for this query."));
    }
  }

  // ── 3D Elliptical Orbit Cast & Focus Spotlight ─────────────────────────────

  async function castFor(entry) {
    if (entry.mode === "custom") return state.customCast;
    const query =
      "?mode=" +
      encodeURIComponent(entry.mode) +
      (entry.variant ? "&variant=" + encodeURIComponent(entry.variant) : "");
    const data = await api("/personas" + query);
    return (data && data.personas) || [];
  }

  async function chooseFormat(entry) {
    castDrawer.hidden = true;
    formatTrigger.setAttribute("aria-expanded", "false");
    if (state.active) return;
    if (entry.key === state.format.key) {
      if (state.done) resetRoom();
      return;
    }
    if (state.done) resetRoom();
    let cast = null;
    try {
      cast = await castFor(entry);
    } catch (error) {
      setIdleStatus(error.message);
      return;
    }
    if (!cast || !cast.length) return;
    state.format = entry;
    programName.textContent = entry.name;
    stamp.hidden = true;
    renderCast(cast);
    renderProgram();
    resetWire();
    if (entry.mode !== "custom") syncCallSheet(cast, entry);
    setIdleStatus(entry.name + " seated. Pitch the pit.");
  }

  function renderCast(cast) {
    state.cast = cast;
    castBox.textContent = "";
    castBox.classList.remove("has-speaker");
    const count = cast.length;
    cast.forEach((persona, index) => {
      // Distribute in a 3D perspective arc (front-left, back-arc, front-right)
      const angle = ((index + 0.5) / count) * Math.PI * 1.35 + Math.PI * 0.825;
      const x = 50 + Math.cos(angle) * 38;
      const y = 48 + Math.sin(angle) * 26;
      const depthNorm = (Math.sin(angle) + 1) / 2; // 0 = far back, 1 = front
      const depthScale = (0.84 + depthNorm * 0.24).toFixed(2);
      const z = Math.round(10 + depthNorm * 15);

      const actor = el("article", "actor");
      actor.dataset.key = persona.key;
      actor.style.left = x.toFixed(1) + "%";
      actor.style.top = y.toFixed(1) + "%";
      actor.style.setProperty("--depth-scale", depthScale);
      actor.style.setProperty("--z", String(z));
      actor.style.setProperty("--tone", persona.color || "#e9c46a");
      actor.style.setProperty("--delay", (index * 0.45).toFixed(2) + "s");

      const figure = el("button", "figure");
      figure.type = "button";
      figure.setAttribute("aria-label", persona.name);

      figure.appendChild(el("span", "bust-halo"));
      const head = el("span", "bust-head");
      head.appendChild(el("span", "visor"));
      figure.appendChild(head);
      figure.appendChild(el("span", "bust-shoulders"));

      const prop = el("span", "prop", persona.emoji || "●");
      prop.setAttribute("aria-hidden", "true");
      figure.appendChild(prop);

      figure.addEventListener("click", () => {
        const line = state.lines[persona.key];
        focusPersona(persona.key, line || `${persona.name} (${roleFor(persona.key)}) — waiting for the pitch.`);
      });

      const rail = el("div", "heat-rail");
      rail.appendChild(el("div", "heat-fill"));

      actor.appendChild(figure);
      actor.appendChild(el("span", "nametag", persona.name));
      actor.appendChild(rail);
      castBox.appendChild(actor);
    });
  }

  function roleFor(key) {
    return ROLES[key] || "panelist";
  }

  function actorFor(key) {
    return castBox.querySelector('.actor[data-key="' + key + '"]');
  }

  function setIdleStatus(text) {
    castBox.classList.remove("has-speaker");
    castBox.querySelectorAll(".actor").forEach((a) => a.classList.remove("is-focused", "speaking"));
    activeSpeaker.textContent = "STANDBY";
    activeRole.textContent = state.format.name.toLowerCase();
    speechStage.style.removeProperty("--active-tone");
    replayBtn.hidden = true;
    activeSpeech.textContent = "";
    activeSpeech.appendChild(el("p", "idle-prompt", text));
  }

  function focusPersona(key, text, isLiveStream) {
    if (!key) return;
    const persona = state.cast.find((item) => item.key === key);
    const tone = (persona && persona.color) || "#e9c46a";

    castBox.classList.add("has-speaker");
    castBox.querySelectorAll(".actor").forEach((node) => {
      const match = node.dataset.key === key;
      node.classList.toggle("is-focused", match);
      if (!match) node.classList.remove("speaking");
      else if (isLiveStream) node.classList.add("speaking");
    });

    state.openKey = key;
    activeSpeaker.textContent = persona ? persona.name : key;
    activeRole.textContent = roleFor(key);
    speechStage.style.setProperty("--active-tone", tone);
    replayBtn.hidden = !state.lines[key];

    activeSpeech.textContent = text || "";
    activeSpeech.scrollTop = activeSpeech.scrollHeight;
  }

  // ── Session Execution & SSE ────────────────────────────────────────────────

  async function begin(topic) {
    if (state.active) return;
    castDrawer.hidden = true;
    wireDrawer.hidden = true;
    state.active = true;
    state.done = false;
    state.since = 0;
    state.lines = {};
    state.openKey = null;
    state.transcript = "";
    state.freshPass = false;
    state.passSpeakers.clear();
    state.retries = 0;
    state.turnQueue = [];
    state.pendingEnd = null;
    if (state.turnTimer) {
      window.clearTimeout(state.turnTimer);
      state.turnTimer = null;
    }
    state.demoPacing = String(state.houseProvider).toLowerCase() === "demo";
    stopSpeech();
    stamp.hidden = true;
    strip.hidden = true;
    followForm.hidden = true;
    renderCallSheet();
    resetWire();
    room.dataset.phase = "live";
    setIdleStatus("Convening the room…");

    try {
      const profile = dialProfile(state.dial);
      const body = {
        mode: state.format.mode,
        variant: state.format.variant || undefined,
        topic: topic,
        styles: profile.styles,
        sampling: {
          sampling_overrides: {
            temperature: profile.temperature,
            max_tokens: profile.max_tokens,
            top_p: profile.top_p,
            frequency_penalty: profile.frequency_penalty,
            presence_penalty: profile.presence_penalty,
          },
        },
        scout_context: {
          live: state.format.mode === "arena" || state.format.mode === "bmad",
        },
      };
      if (state.format.mode === "custom") body.cast = state.custom.slice();
      const created = await api("/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      });
      state.sessionId = created.session_id;
      try {
        const snapshot = await api("/sessions/" + state.sessionId);
        renderWire(snapshot.scouts);
      } catch (error) {
        renderWire(null);
      }
      openStream();
    } catch (error) {
      fail(error.message);
    }
  }

  function openStream() {
    closeStream();
    const source = new EventSource(
      withToken("/sessions/" + state.sessionId + "/events?since=" + state.since)
    );
    state.source = source;
    EVENT_TYPES.forEach((type) => {
      source.addEventListener(type, (message) => {
        let payload = null;
        try {
          payload = JSON.parse(message.data);
        } catch (error) {
          return;
        }
        state.retries = 0;
        state.since += 1;
        handle(type, payload);
      });
    });
    source.onerror = () => {
      if (state.done) {
        source.close();
        return;
      }
      source.close();
      state.retries += 1;
      if (state.retries > 4) {
        fail("Connection dropped. Reload to wake the host.");
        return;
      }
      window.setTimeout(() => {
        if (!state.done && state.sessionId) openStream();
      }, 1200);
    };
  }

  function closeStream() {
    if (state.source) {
      state.source.close();
      state.source = null;
    }
  }

  function handle(type, payload) {
    switch (type) {
      case "session_start":
        if (Array.isArray(payload.personas) && payload.personas.length) renderCast(payload.personas);
        room.dataset.phase = "live";
        break;
      case "status":
        if (state.demoPacing) break;
        if (payload.persona) focusPersona(payload.persona, payload.message || "Thinking…", false);
        break;
      case "token_chunk": {
        if (state.demoPacing) break;
        const key = payload.persona;
        if (!key) break;
        if (state.freshPass && !state.passSpeakers.has(key)) {
          state.lines[key] = "";
          state.passSpeakers.add(key);
        }
        state.lines[key] = (state.lines[key] || "") + (payload.text || "");
        focusPersona(key, state.lines[key], true);
        break;
      }
      case "persona_turn":
        if (state.demoPacing) {
          state.turnQueue.push(payload);
          drainTurns();
        } else {
          presentTurn(payload);
        }
        break;
      case "iteration_start":
        state.freshPass = true;
        state.passSpeakers.clear();
        break;
      case "error":
        fail(payload.message || "Session error.");
        break;
      case "session_end":
        state.done = true;
        closeStream();
        if (state.demoPacing && (state.turnQueue.length || state.turnTimer)) {
          state.pendingEnd = payload;
          drainTurns();
        } else {
          finish(payload);
        }
        break;
      default:
        break;
    }
  }

  function presentTurn(payload) {
    const key = payload.persona;
    state.lines[key] = payload.content || state.lines[key] || "";
    const actor = actorFor(key);
    if (actor) actor.classList.remove("speaking");
    focusPersona(key, state.lines[key], false);
    if (state.voice) readAloud(key, state.lines[key], false);
  }

  function drainTurns() {
    if (state.turnTimer) return;
    if (state.turnQueue.length) {
      const payload = state.turnQueue.shift();
      presentTurn(payload);
      const words = String(state.lines[payload.persona] || "").split(/\s+/).filter(Boolean).length;
      const beat = Math.min(6500, Math.max(2800, words * 75));
      state.turnTimer = window.setTimeout(() => {
        state.turnTimer = null;
        drainTurns();
      }, beat);
      return;
    }
    if (state.pendingEnd) {
      const payload = state.pendingEnd;
      state.pendingEnd = null;
      state.turnTimer = window.setTimeout(() => {
        state.turnTimer = null;
        finish(payload);
      }, 800);
    }
  }

  function finish(payload) {
    state.done = true;
    state.active = false;
    state.transcript = payload.transcript || "";
    closeStream();
    room.dataset.phase = "verdict";
    castBox.querySelectorAll(".actor.speaking").forEach((actor) => actor.classList.remove("speaking"));
    stamp.dataset.tone = "verdict";
    stamp.textContent = "VERDICT IN — TAP ANY CHARACTER TO INSPECT OR PUSH BACK BELOW";
    stamp.hidden = false;
    strip.hidden = !state.transcript;
    followForm.hidden = false;
    followInput.value = "";
    renderProgram();
    renderCallSheet();
  }

  function fail(message) {
    state.done = true;
    state.active = false;
    state.turnQueue = [];
    state.pendingEnd = null;
    if (state.turnTimer) {
      window.clearTimeout(state.turnTimer);
      state.turnTimer = null;
    }
    closeStream();
    room.dataset.phase = "lobby";
    stopSpeech();
    stamp.dataset.tone = "fault";
    stamp.textContent = message || "FAULT";
    stamp.hidden = false;
    renderProgram();
    renderCallSheet();
  }

  caseForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const topic = caseInput.value.trim();
    if (!topic) return;
    if (recognition) recognition.stop();
    begin(topic);
  });

  followForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = followInput.value.trim();
    if (!message || !state.sessionId || state.active) return;
    state.done = false;
    state.active = true;
    stamp.hidden = true;
    strip.hidden = true;
    followForm.hidden = true;
    room.dataset.phase = "live";
    try {
      await api("/sessions/" + state.sessionId + "/messages", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      openStream();
    } catch (error) {
      fail(error.message);
    }
  });

  function resetRoom() {
    closeStream();
    stopSpeech();
    state.turnQueue = [];
    state.pendingEnd = null;
    if (state.turnTimer) {
      window.clearTimeout(state.turnTimer);
      state.turnTimer = null;
    }
    state.sessionId = null;
    state.since = 0;
    state.done = false;
    state.active = false;
    state.lines = {};
    state.openKey = null;
    state.transcript = "";
    state.freshPass = false;
    state.passSpeakers.clear();
    state.retries = 0;
    stamp.hidden = true;
    strip.hidden = true;
    followForm.hidden = true;
    resetWire();
    caseInput.value = "";
    renderCallSheet();
    room.dataset.phase = "lobby";
    setIdleStatus("Arena cleared. Pitch the next case.");
    renderProgram();
  }

  gavel.addEventListener("click", async () => {
    if (state.pendingEnd) {
      if (state.turnTimer) {
        window.clearTimeout(state.turnTimer);
        state.turnTimer = null;
      }
      const payload = state.pendingEnd;
      state.pendingEnd = null;
      state.turnQueue = [];
      finish(payload);
      return;
    }
    if (state.done && !state.active) {
      resetRoom();
      return;
    }
    if (!state.sessionId || state.done) return;
    try {
      await api("/sessions/" + state.sessionId + "/stop", {
        method: "POST",
        body: "{}",
      });
    } catch (error) {
      /* ignore */
    }
  });

  strip.addEventListener("click", () => {
    if (!state.transcript) return;
    const blob = new Blob([state.transcript], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "hotseat-" + (state.sessionId || "session") + ".md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });

  async function loadHouse() {
    try {
      const data = await api("/providers/status");
      const rows = data.providers || [];
      const active = String(data.active || "").trim().toLowerCase();
      state.houseProvider = active || "auto";
      const cloud = rows.find((row) => row.configured && !row.local && !row.offline);
      const demo = rows.find((row) => row.name === "demo" && row.configured);
      const house =
        active && active !== "auto"
          ? active.toUpperCase()
          : cloud
            ? cloud.name.toUpperCase()
            : demo
              ? "DEMO"
              : "UNSET";
      plaque.textContent = "HOUSE · " + house;
    } catch (error) {
      plaque.textContent = "HOUSE · OFFLINE";
    }
  }

  async function boot() {
    syncLinks();
    await loadRoster();
    programName.textContent = state.format.name;
    renderProgram();
    let cast = state.customCast.length ? state.customCast : FALLBACK_CAST;
    try {
      const fetched = await castFor(state.format);
      if (fetched && fetched.length) cast = fetched;
    } catch (error) {
      /* fallback cast */
    }
    renderCast(cast);
    syncCallSheet(cast, state.format);
    renderDial();
    loadHouse();
  }

  boot();
})();
