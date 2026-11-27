/* THE TABLE — the room is the interface.
   One case file, five characters, speech bubbles. Zero dependencies. */

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
  const program = $("#program");
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
  const wireCount = $("#wire-count");
  const wireNote = $("#wire-note");
  const wireList = $("#wire-list");

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
    { key: "producer", name: "The Producer", emoji: "🎬", color: "#b8292f" },
    { key: "critic", name: "The Critic", emoji: "🔪", color: "#e3a857" },
    { key: "foreman", name: "The Foreman", emoji: "🔔", color: "#f5e6cc" },
    { key: "architect", name: "The Architect", emoji: "📐", color: "#219ebc" },
    { key: "coroner", name: "The Coroner", emoji: "🥼", color: "#8ecae6" },
  ];

  const SEATS = {
    2: [
      { left: 31, top: 56, side: "left", row: "middle" },
      { left: 69, top: 56, side: "right", row: "middle" },
    ],
    1: [
      { left: 50, top: 52, side: "center", row: "middle" },
    ],
    5: [
      { left: 7, top: 47, side: "left", row: "middle" },
      { left: 28, top: 72, side: "left", row: "bottom" },
      { left: 50, top: 16, side: "center", row: "top" },
      { left: 72, top: 72, side: "right", row: "bottom" },
      { left: 93, top: 47, side: "right", row: "middle" },
    ],
    4: [
      { left: 12, top: 50, side: "left", row: "middle" },
      { left: 37, top: 72, side: "left", row: "bottom" },
      { left: 63, top: 72, side: "right", row: "bottom" },
      { left: 88, top: 50, side: "right", row: "middle" },
    ],
    3: [
      { left: 17, top: 58, side: "left", row: "bottom" },
      { left: 50, top: 16, side: "center", row: "top" },
      { left: 83, top: 58, side: "right", row: "bottom" },
    ],
  };

  const PROGRAM = [
    { key: "arena", mode: "arena", variant: null, name: "The Arena", blurb: "your idea vs three rivals" },
    { key: "classic", mode: "classic", variant: null, name: "The Audit", blurb: "auditor, market read, closer" },
    { key: "v2", mode: "v2", variant: null, name: "The Debate", blurb: "three skeptics, one defence" },
    { key: "v3:panel", mode: "v3", variant: "panel", name: "The Panel", blurb: "witness, systems, closer" },
    { key: "v3:tribunal", mode: "v3", variant: "tribunal", name: "The Tribunal", blurb: "four roles, three ranked actions" },
    { key: "bmad", mode: "bmad", variant: null, name: "The Brief", blurb: "one pass, a build you can start" },
    { key: "custom", mode: "custom", variant: null, name: "The Call Sheet", blurb: "your own cast, one turn each" },
  ];

  const CAST_SOURCES = [
    { mode: "arena" },
    { mode: "classic" },
    { mode: "v2" },
    { mode: "v3", variant: "panel" },
    { mode: "v3", variant: "tribunal" },
    { mode: "bmad" },
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

  // ── transport ──────────────────────────────────────────────────────────────

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
        throw new Error("The door is locked — this link needs its ?token=.");
      }
      throw new Error((payload && payload.error) || "The room did not answer (" + response.status + ").");
    }
    return payload;
  }

  // ── build the room ─────────────────────────────────────────────────────────

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  // ── the program ────────────────────────────────────────────────────────────

  function renderProgram() {
    programList.textContent = "";
    PROGRAM.forEach((entry) => {
      const item = document.createElement("li");
      const button = el("button");
      button.type = "button";
      button.appendChild(el("strong", "", entry.name));
      button.appendChild(
        el("span", "", entry.mode === "custom" ? state.custom.length + " called, one turn each" : entry.blurb)
      );
      if (entry.key === state.format.key) button.setAttribute("aria-current", "true");
      button.disabled = state.active;
      button.addEventListener("click", () => chooseFormat(entry));
      item.appendChild(button);
      programList.appendChild(item);
    });
  }

  // ── the call sheet: choose who sits down ──────────────────────────────────

  function memberFor(id) {
    const member = state.roster.find((entry) => entry.id === id);
    return member ? member.persona : null;
  }

  function renderCallSheet() {
    callList.textContent = "";
    callCount.textContent =
      state.custom.length + (state.custom.length >= MAX_CAST ? " called · max" : " called");
    if (!state.roster.length) {
      callList.appendChild(el("span", "call-empty", "the call sheet did not load."));
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
        swatch.style.setProperty("--tone", member.persona.color || "#8a6a2f");
        label.appendChild(swatch);
        label.appendChild(el("span", "", member.persona.name));
        if (!checked && full) {
          label.dataset.off = "true";
          label.title = "five is the table's limit";
        }
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
    if (checked && state.custom.length >= MAX_CAST) {
      note.textContent = "five is the table's limit. uncheck someone first.";
      renderCallSheet();
      return;
    }
    if (!checked && state.custom.length <= 1) {
      note.textContent = "someone has to sit down.";
      renderCallSheet();
      return;
    }
    if (state.done) resetRoom();
    state.custom = checked
      ? state.custom.concat([id])
      : state.custom.filter((member) => member !== id);
    state.customCast = state.custom.map(memberFor).filter(Boolean);
    state.format = PROGRAM.find((entry) => entry.key === "custom") || state.format;
    programName.textContent = state.format.name;
    caseHint.textContent = formatHint();
    stamp.hidden = true;
    renderCast(state.customCast);
    renderProgram();
    resetWire();
    renderCallSheet();
    note.textContent = state.custom.length + " on the call sheet.";
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

  // ── the dial: clinical at 0, unhinged at 11 ────────────────────────────────

  function dialProfile(value) {
    const v = Number(value);
    if (v <= 2) {
      return {
        temperature: 0.3 + v * 0.05,
        max_tokens: 220,
        top_p: 0.85,
        frequency_penalty: 0.25,
        presence_penalty: 0,
        styles: ["terse"],
        label: "clinical",
      };
    }
    if (v <= 5) {
      return {
        temperature: 0.5 + (v - 3) * 0.075,
        max_tokens: 320,
        top_p: 0.9,
        frequency_penalty: 0.18,
        presence_penalty: 0,
        styles: ["nosyco"],
        label: "measured",
      };
    }
    if (v <= 8) {
      return {
        temperature: 0.75 + (v - 6) * 0.075,
        max_tokens: 460,
        top_p: 0.92,
        frequency_penalty: 0.1,
        presence_penalty: 0.05,
        styles: [],
        label: "loose",
      };
    }
    return {
      temperature: 1.0 + (v - 9) * 0.075,
      max_tokens: 620,
      top_p: 0.96,
      frequency_penalty: 0.05,
      presence_penalty: 0.12,
      styles: [],
      label: "unhinged",
    };
  }

  function renderDial() {
    state.dial = Number(dial.value);
    const profile = dialProfile(state.dial);
    dialValue.textContent = String(state.dial);
    dialLabel.textContent = profile.label;
  }

  dial.addEventListener("input", renderDial);

  dialRoll.addEventListener("click", () => {
    dial.value = String(Math.floor(Math.random() * 12));
    renderDial();
    note.textContent = "the dial landed on " + state.dial + ".";
  });

  // ── read aloud: one house voice per character, mapped by key ───────────────

  let speechVoices = [];

  function loadVoices() {
    if (!window.speechSynthesis) return;
    speechVoices = window.speechSynthesis.getVoices() || [];
  }

  if (window.speechSynthesis) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  } else {
    voiceButton.disabled = true;
    voiceButton.textContent = "VOICE UNAVAILABLE";
    voiceButton.title = "This browser has no speech synthesis.";
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
      rate: 0.92 + ((hash >> 5) % 3) * 0.06,
    };
  }

  function readAloud(key, text, interrupt) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance || !text) return;
    const spoken = String(text)
      .replace(/[*_#`>]/g, "")
      .replace(/\s+/g, " ")
      .trim();
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
    voiceButton.textContent = state.voice ? "🔊 VOICE ON" : "🔇 VOICE OFF";
    if (state.voice && window.SpeechSynthesisUtterance) {
      // Unlock speech inside the click gesture; iOS will not start it later.
      const primer = new SpeechSynthesisUtterance(" ");
      primer.volume = 0;
      window.speechSynthesis.speak(primer);
    }
    if (!state.voice) stopSpeech();
    note.textContent = state.voice ? "the room will read its turns aloud." : "the room goes quiet.";
  });

  // ── dictation: the case, spoken ────────────────────────────────────────────

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;

  if (!SpeechRecognition) {
    micButton.disabled = true;
    micButton.title = "This browser has no speech recognition. Chrome, Edge, or Safari can dictate.";
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
        note.textContent = "listening — speak the case.";
      };
      recognition.onresult = (event) => {
        let heard = "";
        for (let i = 0; i < event.results.length; i += 1) {
          heard += event.results[i][0].transcript;
        }
        caseInput.value = heard.trim();
      };
      recognition.onerror = (event) => {
        note.textContent =
          event.error === "not-allowed"
            ? "the mic is blocked. allow it in the browser."
            : "the mic dropped. type it instead.";
      };
      recognition.onend = () => {
        state.listening = false;
        micButton.setAttribute("aria-pressed", "false");
        if (caseInput.value.trim()) caseInput.focus();
      };
      try {
        recognition.start();
      } catch (error) {
        note.textContent = "the mic is already listening.";
      }
    });
  }

  // ── the wire ───────────────────────────────────────────────────────────────

  wire.addEventListener("click", () => {
    const open = !wire.classList.contains("open");
    wire.classList.toggle("open", open);
    wire.setAttribute("aria-expanded", String(open));
  });

  function resetWire() {
    wire.hidden = true;
    wire.classList.remove("open");
    wire.setAttribute("aria-expanded", "false");
    wireCount.textContent = "sweeping…";
    wireNote.textContent = "scouts on the case";
    wireList.textContent = "";
  }

  function timeLabel(value) {
    try {
      return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (error) {
      return "just now";
    }
  }

  function renderWire(scouts) {
    wire.hidden = false;
    wireList.textContent = "";
    if (!scouts) {
      wireCount.textContent = "no sweep";
      wireNote.textContent = "the bridge returned no scout report";
      return;
    }
    const counts = scouts.counts || {};
    const signals = Array.isArray(scouts.signals) ? scouts.signals : [];
    const anchors = Array.isArray(scouts.market_anchors) ? scouts.market_anchors : [];
    const signalCount = counts.signals === undefined ? signals.length : counts.signals;
    const priceCount =
      counts.prices === undefined ? (Array.isArray(scouts.prices) ? scouts.prices.length : 0) : counts.prices;
    wireCount.textContent =
      signalCount + " signal" + (signalCount === 1 ? "" : "s") +
      " · " + priceCount + " price" + (priceCount === 1 ? "" : "s");
    wireNote.textContent = scouts.generated_at
      ? "swept " + timeLabel(scouts.generated_at)
      : "scouts on the case";

    signals.slice(0, 3).forEach((signal) => {
      wireList.appendChild(
        el("span", "wire-item", "[" + (signal.source || "wire") + "] " + (signal.title || "untitled"))
      );
    });
    anchors.slice(0, 3).forEach((anchor) => {
      wireList.appendChild(
        el("span", "wire-item", "PRICE " + (anchor.competitor || "market") + " — " + (anchor.price || "unknown"))
      );
    });
    if (!wireList.childElementCount) {
      wireList.appendChild(el("span", "wire-item", "The wire is quiet for this case."));
    }
  }

  function formatHint() {
    if (state.format.mode === "custom") {
      return "your call — " + state.custom.length + " taking a seat";
    }
    return state.format.blurb;
  }

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
    program.open = false;
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
      note.textContent = error.message;
      return;
    }
    if (!cast || !cast.length) {
      if (entry.mode === "custom") {
        program.open = true;
        note.textContent = "the call sheet is blank. pick at least one name.";
      } else {
        note.textContent = "that room did not answer.";
      }
      return;
    }
    state.format = entry;
    programName.textContent = entry.name;
    caseHint.textContent = formatHint();
    stamp.hidden = true;
    renderCast(cast);
    renderProgram();
    resetWire();
    if (entry.mode !== "custom") syncCallSheet(cast, entry);
    note.textContent = entry.name + " is seated.";
  }

  function renderCast(cast) {
    state.cast = cast;
    castBox.textContent = "";
    const seats = SEATS[cast.length] || SEATS[5];
    cast.forEach((persona, index) => {
      const seat = seats[index] || seats[seats.length - 1];
      castBox.appendChild(buildActor(persona, index, seat));
    });
  }

  function buildActor(persona, index, seat) {
    const actor = el("article", "actor");
    actor.dataset.key = persona.key;
    actor.style.left = seat.left + "%";
    actor.style.top = seat.top + "%";
    actor.dataset.side = seat.side;
    actor.dataset.row = seat.row;
    actor.style.setProperty("--tone", persona.color || "#31795a");
    actor.style.setProperty("--delay", (index * 0.6).toFixed(2) + "s");

    const figure = el("button", "figure");
    figure.type = "button";
    figure.setAttribute("aria-label", persona.name + " — " + roleFor(persona.key));
    figure.setAttribute("aria-expanded", "false");
    figure.setAttribute("aria-controls", "dossier-" + persona.key);

    const head = el("span", "head");
    head.appendChild(el("span", "eye left"));
    head.appendChild(el("span", "eye right"));
    head.appendChild(el("span", "mouth"));
    figure.appendChild(head);
    figure.appendChild(el("span", "torso"));

    const prop = el("span", "prop", persona.emoji || "●");
    prop.setAttribute("aria-hidden", "true");
    figure.appendChild(prop);

    const bubble = el("div", "bubble");
    bubble.appendChild(el("p", "bubble-text"));
    bubble.title = "Click to hear this turn";
    bubble.addEventListener("click", () =>
      readAloud(persona.key, state.lines[persona.key] || "", true)
    );

    const said = el("button", "said");
    said.type = "button";
    said.setAttribute("aria-label", "Show " + persona.name + "’s last turn");

    const dossier = el("div", "dossier");
    dossier.id = "dossier-" + persona.key;
    dossier.appendChild(el("span", "dossier-role", roleFor(persona.key)));
    dossier.appendChild(el("h2", "dossier-name", persona.name));
    dossier.appendChild(el("span", "dossier-model", persona.model || "house model"));
    dossier.appendChild(el("p", "dossier-line", "Hasn’t spoken yet."));

    figure.addEventListener("click", () => toggleDossier(actor, figure, dossier));
    said.addEventListener("click", () => speak(persona.key, state.lines[persona.key] || ""));

    actor.appendChild(figure);
    actor.appendChild(el("span", "nametag", persona.name));
    actor.appendChild(bubble);
    actor.appendChild(said);
    actor.appendChild(dossier);
    return actor;
  }

  function roleFor(key) {
    return ROLES[key] || "sits on the panel";
  }

  function actorFor(key) {
    return castBox.querySelector('.actor[data-key="' + key + '"]');
  }

  function toggleDossier(actor, figure, dossier) {
    const open = !dossier.classList.contains("open");
    castBox.querySelectorAll(".dossier.open").forEach((node) => node.classList.remove("open"));
    castBox.querySelectorAll('.figure[aria-expanded="true"]').forEach((node) => {
      node.setAttribute("aria-expanded", "false");
    });
    if (!open) return;
    dossier.classList.add("open");
    figure.setAttribute("aria-expanded", "true");
    const key = actor.dataset.key;
    const line = dossier.querySelector(".dossier-line");
    line.textContent = (state.lines[key] || "").trim() || "Hasn’t spoken yet.";
  }

  // ── speech ─────────────────────────────────────────────────────────────────

  function speak(key, text) {
    if (!key) return;
    if (state.openKey && state.openKey !== key) collapse(state.openKey);
    const actor = actorFor(key);
    if (!actor) return;
    castBox.querySelectorAll(".actor.speaking").forEach((node) => {
      if (node.dataset.key !== key) node.classList.remove("speaking");
    });
    state.openKey = key;
    actor.classList.add("open");
    actor.classList.remove("thinking");
    actor.querySelector(".bubble-text").textContent = text || "";
    actor.querySelector(".said").textContent = "";
  }

  function collapse(key) {
    const actor = actorFor(key);
    if (!actor) return;
    actor.classList.remove("open");
    const text = (state.lines[key] || "").trim();
    const said = actor.querySelector(".said");
    if (text) {
      said.textContent = "“" + (text.length > 70 ? text.slice(0, 70).trim() + "…" : text) + "”";
    }
    if (state.openKey === key) state.openKey = null;
  }

  function setThinking(key) {
    castBox.querySelectorAll(".actor.thinking").forEach((node) => node.classList.remove("thinking"));
    if (!key) return;
    const actor = actorFor(key);
    if (!actor) return;
    actor.classList.add("thinking");
    const persona = state.cast.find((item) => item.key === key);
    note.textContent = (persona ? persona.name : key) + " is thinking";
  }

  // ── the session ────────────────────────────────────────────────────────────

  async function begin(topic) {
    if (state.active) return;
    program.open = false;
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
    castBox.querySelectorAll(".actor").forEach((actor) => {
      actor.classList.remove("open", "speaking", "thinking");
      actor.querySelector(".said").textContent = "";
      actor.querySelector(".dossier").classList.remove("open");
      const figure = actor.querySelector(".figure");
      if (figure) figure.setAttribute("aria-expanded", "false");
    });
    note.textContent = "seating the room…";
    renderProgram();
    resetWire();
    wire.hidden = false;
    wireCount.textContent = "sweeping…";
    wireNote.textContent = "scouts on the case";
    room.dataset.phase = "live";
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
        fail("The room went dark. On a free host it may have gone to sleep — reload to wake it.");
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
        note.textContent = payload.topic ? "the case: " + payload.topic : "the room is seated";
        break;
      case "status":
        if (state.demoPacing) break;
        setThinking(payload.persona || null);
        if (payload.message) note.textContent = payload.message;
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
        const actor = actorFor(key);
        if (actor) {
          actor.classList.add("speaking");
          actor.classList.remove("thinking");
        }
        speak(key, state.lines[key]);
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
      case "operator_message":
        note.textContent = "a note slides across the table.";
        break;
      case "iteration_start":
        state.freshPass = true;
        state.passSpeakers.clear();
        note.textContent = "the room leans back in.";
        break;
      case "memory_saved":
        break;
      case "error":
        fail(payload.message || "The room hit a fault.");
        break;
      case "session_end":
        // The job is over even if the demo is still revealing its turns.
        // Close the stream now so EventSource does not reconnect and trip the
        // "room went dark" fallback while the last beats play out.
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
    speak(key, state.lines[key]);
    if (state.voice) readAloud(key, state.lines[key], false);
    setThinking(null);
    if (state.demoPacing) {
      const persona = state.cast.find((item) => item.key === key);
      if (persona) note.textContent = persona.name + " has the floor.";
    }
  }

  // The demo provider answers instantly. Give each turn a beat so the room is
  // watchable instead of flashing the whole transcript at once.
  function drainTurns() {
    if (state.turnTimer) return;
    if (state.turnQueue.length) {
      const payload = state.turnQueue.shift();
      presentTurn(payload);
      const words = String(state.lines[payload.persona] || "")
        .split(/\s+/)
        .filter(Boolean).length;
      const beat = Math.min(7000, Math.max(3000, words * 80));
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
      }, 900);
    }
  }

  function finish(payload) {
    state.done = true;
    state.active = false;
    state.transcript = payload.transcript || "";
    setThinking(null);
    closeStream();
    room.dataset.phase = "verdict";
    castBox.querySelectorAll(".actor.speaking").forEach((actor) => actor.classList.remove("speaking"));
    stamp.dataset.tone = "verdict";
    stamp.textContent = payload.follow_up
      ? "second opinion filed"
      : state.format.mode === "custom"
        ? "the call is filed"
        : "autopsy filed";
    stamp.hidden = false;
    strip.hidden = !state.transcript;
    wire.classList.remove("open");
    wire.setAttribute("aria-expanded", "false");
    followForm.hidden = false;
    followInput.value = "";
    gavel.setAttribute("aria-label", "Clear the table for a new case");
    gavel.title = "Clear the table for a new case";
    note.textContent = payload.stopped ? "the gavel came down." : "the room is done. ask again, or tear off the transcript.";
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
    setThinking(null);
    room.dataset.phase = "lobby";
    stopSpeech();
    stamp.dataset.tone = "fault";
    stamp.textContent = message || "fault";
    stamp.hidden = false;
    note.textContent = "the room reset. pull the case file back over when ready.";
    renderProgram();
    renderCallSheet();
  }

  // ── objects that do things ─────────────────────────────────────────────────

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
    note.textContent = "the room leans back in.";
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
    castBox.querySelectorAll(".actor").forEach((actor) => {
      actor.classList.remove("open", "speaking", "thinking");
      actor.querySelector(".bubble-text").textContent = "";
      actor.querySelector(".said").textContent = "";
      actor.querySelector(".dossier").classList.remove("open");
      const figure = actor.querySelector(".figure");
      if (figure) figure.setAttribute("aria-expanded", "false");
    });
    stamp.hidden = true;
    strip.hidden = true;
    followForm.hidden = true;
    resetWire();
    caseInput.value = "";
    caseHint.textContent = formatHint();
    renderCallSheet();
    gavel.setAttribute("aria-label", "Stop the session");
    gavel.title = "Stop the session";
    room.dataset.phase = "lobby";
    note.textContent = "the table is clear. bring the next case.";
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
      if (window.innerWidth > 1240) caseInput.focus({ preventScroll: true });
      return;
    }
    if (!state.sessionId || state.done) return;
    note.textContent = "the gavel falls at the end of this turn.";
    try {
      await api("/sessions/" + state.sessionId + "/stop", {
        method: "POST",
        body: "{}",
      });
    } catch (error) {
      note.textContent = error.message;
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

  // ── boot ───────────────────────────────────────────────────────────────────

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
      plaque.textContent = "HOUSE MODEL · " + house;
    } catch (error) {
      plaque.textContent = "HOUSE MODEL · UNKNOWN";
    }
  }

  async function boot() {
    syncLinks();
    await loadRoster();
    programName.textContent = state.format.name;
    caseHint.textContent = formatHint();
    renderProgram();
    let cast = state.customCast.length ? state.customCast : FALLBACK_CAST;
    try {
      const fetched = await castFor(state.format);
      if (fetched && fetched.length) cast = fetched;
    } catch (error) {
      // The fallback cast keeps the room visible when the door is locked.
    }
    renderCast(cast);
    syncCallSheet(cast, state.format);
    renderDial();
    loadHouse();
    note.textContent = "one idea, one room. pick a cast or press return when ready.";
    if (window.innerWidth > 1240) caseInput.focus({ preventScroll: true });
  }

  boot();
})();
