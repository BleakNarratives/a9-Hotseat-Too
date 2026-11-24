/* The Hot Seat — live ChronoScouts arena console.
   Zero dependencies. All content is rendered with text nodes; scout data is untrusted. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const state = {
    sessionId: null,
    eventCount: 0,
    active: false,
    done: false,
    source: null,
    mode: "arena",
    scout: null,
    names: {},
    streams: new Map(),
    turns: [],
  };

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

  function token() {
    return new URLSearchParams(window.location.search).get("token") || "";
  }

  function withToken(path) {
    const value = token();
    if (!value) return path;
    return path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(value);
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
      throw new Error((payload && payload.error) || "Request failed (" + response.status + ")");
    }
    return payload;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function showError(message) {
    const line = $("#error-line");
    if (!message) {
      line.hidden = true;
      line.textContent = "";
      return;
    }
    line.hidden = false;
    line.textContent = String(message);
  }

  function setStatus(text, ledState) {
    $("#stage-status").textContent = String(text || "IDLE").toUpperCase();
    const led = $("#conn-led");
    const label = $("#conn-label");
    const map = {
      live: ["LIVE", "live"],
      done: ["VERDICT IN", "done"],
      error: ["FAULT", "error"],
      idle: ["STANDING BY", "idle"],
    };
    if (ledState) {
      led.dataset.state = ledState;
      label.textContent = (map[ledState] || map.idle)[0];
    }
  }

  function setLiveFlag(visible) {
    $("#live-flag").hidden = !visible;
  }

  // ── metadata ───────────────────────────────────────────────────────────────
  function fillSelect(select, entries, preferred) {
    clear(select);
    entries.forEach((entry) => {
      const option = document.createElement("option");
      option.value = entry.value;
      option.textContent = entry.label;
      if (entry.title) option.title = entry.title;
      select.appendChild(option);
    });
    if (preferred && entries.some((entry) => entry.value === preferred)) {
      select.value = preferred;
    }
  }

  async function loadMetadata() {
    let modes = [];
    let providers = [];
    try {
      const [modeData, providerData] = await Promise.all([api("/modes"), api("/providers")]);
      modes = modeData.modes || [];
      providers = providerData.providers || [];
    } catch (error) {
      showError("Could not load bridge metadata: " + error.message);
    }

    if (!modes.length) {
      modes = [
        { mode: "arena", label: "The Arena", description: "Four contenders, one verdict." },
        { mode: "bmad", label: "BMAD Brief", description: "One pass to a build brief." },
        { mode: "classic", label: "Classic Panel", description: "Three voices, straight answer." },
        { mode: "v2", label: "The Debate", description: "A volunteer faces the room." },
        { mode: "v3", label: "The Tribunal", description: "A panel and a closer." },
      ];
    }
    fillSelect(
      $("#mode-select"),
      modes.map((item) => ({
        value: item.mode,
        label: (item.label || item.mode).toUpperCase(),
        title: item.description || "",
      })),
      "arena"
    );
    if (!$("#mode-select").value) $("#mode-select").value = "arena";

    const providerEntries = [
      { value: "auto", label: "AUTO // SERVER CONFIG", title: "Use the server's configured provider (auto probes 9router, then cloud keys)." },
    ].concat(
      (providers.length ? providers : [
        { name: "openrouter", requires_key: true },
        { name: "mistral", requires_key: true },
        { name: "anthropic", requires_key: true },
        { name: "cerebras", requires_key: true },
        { name: "groq", requires_key: true },
        { name: "9router", requires_key: false },
        { name: "demo", requires_key: false },
      ]).map((item) => ({
        value: item.name,
        label: item.name.toUpperCase() + (item.offline ? " // OFFLINE" : item.requires_key ? " // KEY" : ""),
        title: item.requires_key ? "Credential resolved from env, .env, or the Concierge vault." : "",
      }))
    );
    fillSelect($("#provider-select"), providerEntries, "auto");
    updateProviderHint();
  }

  function updateProviderHint() {
    const select = $("#provider-select");
    const selected = select.options[select.selectedIndex];
    $("#provider-hint").textContent =
      (selected && selected.title) || "Credentials resolve automatically from env, .env, or vault.";
  }

  // ── scout wire ─────────────────────────────────────────────────────────────
  function scoutTime(value) {
    if (!value) return "undated";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function safeUrl(value) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : "";
    } catch (error) {
      return "";
    }
  }

  function safeWeight(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(1, number)).toFixed(2) : "—";
  }

  function tickerItem(kind, item) {
    const node = el("span", "ticker-item");
    node.appendChild(el("span", "tag", kind === "price" ? "PRICE" : String(item.kind || "SIGNAL").toUpperCase()));
    const text =
      kind === "price"
        ? String(item.competitor || "market") + " · " + String(item.product || "pricing") + " · " + String(item.price || "—")
        : String(item.title || "(untitled signal)");
    node.appendChild(el("span", "title", text));
    node.appendChild(el("span", "w", "W " + safeWeight(item.weight)));
    node.title = kind === "price" ? String(item.url || "") : String(item.detail || "");
    return node;
  }

  function renderScout(report) {
    if (!report) return;
    state.scout = report;
    const counts = report.counts || {};
    const signals = Array.isArray(report.signals) ? report.signals : [];
    const prices = Array.isArray(report.prices) ? report.prices : [];
    $("#scout-meta").textContent =
      String(counts.signals || signals.length) +
      " signals // " +
      String(counts.prices || prices.length) +
      " price points // " +
      scoutTime(report.generated_at);

    const track = $("#ticker-track");
    clear(track);
    if (!signals.length && !prices.length) {
      track.appendChild(el("span", "ticker-empty", "SCOUT SWEEP RETURNED EMPTY // sources may be quiet, offline, or blocked."));
    } else {
      const items = [];
      signals.slice(0, 10).forEach((item) => items.push(tickerItem("signal", item)));
      prices.slice(0, 5).forEach((item) => items.push(tickerItem("price", item)));
      items.forEach((item) => track.appendChild(item));
      items.forEach((item) => track.appendChild(item.cloneNode(true)));
    }

    const strip = $("#market-strip");
    clear(strip);
    strip.appendChild(el("span", "market-label", "MARKET BENCHMARKS"));
    if (!prices.length) {
      strip.appendChild(el("span", "market-empty", "no price points extracted"));
    } else {
      prices.slice(0, 5).forEach((price) => {
        const chip = el("span", "price-chip");
        chip.appendChild(el("strong", "", String(price.price || "—")));
        chip.appendChild(el("span", "", String(price.competitor || "market")));
        chip.title = String(price.product || "") + " // observed " + scoutTime(price.observed_at);
        strip.appendChild(chip);
      });
    }

    renderDrawer(report, signals, prices);
    applyMarketFoot(prices);
  }

  function renderDrawer(report, signals, prices) {
    const signalBox = $("#scout-signals");
    clear(signalBox);
    if (!signals.length) signalBox.appendChild(el("p", "muted", "No signals in the last sweep."));
    signals.slice(0, 24).forEach((signal) => {
      const row = el("div", "scout-row");
      const link = safeUrl(signal.url);
      const title = link ? el("a", "", signal.title || "(untitled)") : el("span", "", signal.title || "(untitled)");
      if (link) {
        title.href = link;
        title.target = "_blank";
        title.rel = "noopener noreferrer";
      }
      row.appendChild(title);
      row.appendChild(
        el(
          "span",
          "meta",
          String(signal.source || "scout") +
            " // " +
            scoutTime(signal.published_at) +
            " // weight " +
            safeWeight(signal.weight)
        )
      );
      signalBox.appendChild(row);
    });

    const priceBox = $("#scout-prices");
    clear(priceBox);
    if (!prices.length) priceBox.appendChild(el("p", "muted", "No competitor pricing found in the last sweep."));
    prices.slice(0, 20).forEach((price) => {
      const row = el("div", "scout-row");
      row.appendChild(el("span", "", String(price.product || "pricing") + " — "));
      row.appendChild(el("em", "", String(price.price || "—")));
      row.appendChild(
        el(
          "span",
          "meta",
          String(price.competitor || "market") +
            " // " +
            scoutTime(price.observed_at) +
            " // weight " +
            safeWeight(price.weight)
        )
      );
      priceBox.appendChild(row);
    });

    const health = $("#scout-health");
    clear(health);
    const sources = Array.isArray(report.sources) ? report.sources : [];
    const errors = Array.isArray(report.errors) ? report.errors : [];
    if (!sources.length && !errors.length) health.appendChild(el("p", "muted", "No sources recorded."));
    sources.forEach((source) => health.appendChild(el("div", "scout-row", source)));
    errors.forEach((error) => {
      const row = el("div", "scout-row error-text", error);
      health.appendChild(row);
    });
    if (report.root) health.appendChild(el("p", "meta", "chronoscouts root: " + report.root));
  }

  function applyMarketFoot(prices) {
    const cards = document.querySelectorAll(".contender[data-slot]");
    cards.forEach((card) => {
      const old = card.querySelector(".market-foot");
      if (old) old.remove();
      if (!prices.length || card.classList.contains("empty")) return;
      const price = prices[0];
      const foot = el("div", "market-foot", "MARKET REF // " + String(price.competitor || "market") + " @ " + String(price.price || "—"));
      card.appendChild(foot);
    });
  }

  async function loadScouts() {
    try {
      const data = await api("/scouts/latest");
      if (data.report) renderScout(data.report);
    } catch (error) {
      $("#scout-meta").textContent = "wire unavailable";
    }
  }

  async function refreshScouts() {
    const button = $("#scout-refresh");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "SWEEPING…";
    try {
      const data = await api("/scouts/refresh", {
        method: "POST",
        body: JSON.stringify({ seed: $("#seed-input").value.trim(), live: true }),
      });
      renderScout(data.report);
      showError("");
    } catch (error) {
      showError("Scout sweep failed: " + error.message);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  // ── stage rendering ────────────────────────────────────────────────────────
  function resetStage() {
    state.turns = [];
    state.streams.clear();
    const turns = $("#turns");
    clear(turns);
    turns.appendChild(el("p", "muted", "Session opening. The room is taking its seats."));
    ["#critic-body", "#foreman-body", "#architect-body", "#coroner-body"].forEach((selector) => {
      const node = $(selector);
      clear(node);
      node.appendChild(el("p", "muted", "Awaiting the room."));
    });
    resetBracket();
    $("#followup-input").disabled = true;
    $("#followup-button").disabled = true;
    setLiveFlag(true);
  }

  function resetBracket() {
    const bracket = $("#bracket");
    clear(bracket);
    const copy = [
      "The seed takes the first chair. Three rivals are built on the spot.",
      "The cheaper model is still in the hallway.",
      "The premium model is polishing its invoice.",
      "The niche wedge is hiding behind a trade magazine.",
    ];
    for (let index = 0; index < 4; index += 1) {
      const card = el("article", "contender empty");
      card.dataset.slot = String(index);
      card.appendChild(el("span", "contender-no", "CONTENDER " + String(index).padStart(2, "0")));
      card.appendChild(el("h3", "", "AWAITING"));
      card.appendChild(el("p", "", copy[index]));
      bracket.appendChild(card);
    }
    if (state.scout && Array.isArray(state.scout.prices)) applyMarketFoot(state.scout.prices);
  }

  function setPanel(selector, text) {
    const node = $(selector);
    clear(node);
    const paragraphs = String(text || "").split(/\n{2,}/).filter((part) => part.trim());
    if (!paragraphs.length) {
      node.appendChild(el("p", "muted", "No output."));
      return;
    }
    paragraphs.forEach((part) => node.appendChild(el("p", "", part.trim())));
  }

  function parseContenders(text) {
    const source = String(text || "");
    const pattern = /CONTENDER\s*(\d+)\s*[—–-]\s*([^\n:]{1,90}):\s*/gi;
    const matches = [];
    let match;
    while ((match = pattern.exec(source)) !== null) {
      matches.push({ index: match.index, end: pattern.lastIndex, number: match[1], name: match[2].trim() });
    }
    if (matches.length < 2) return [];
    return matches.map((item, index) => ({
      number: item.number,
      name: item.name,
      body: source
        .slice(item.end, index + 1 < matches.length ? matches[index + 1].index : source.length)
        .trim(),
    }));
  }

  function renderContenders(text) {
    const parsed = parseContenders(text);
    const bracket = $("#bracket");
    clear(bracket);
    if (!parsed.length) {
      const card = el("article", "contender");
      card.dataset.slot = "0";
      card.appendChild(el("span", "contender-no", "PRODUCER'S MEMO"));
      card.appendChild(el("h3", "", "THE FOUR CONTENDERS"));
      card.appendChild(el("p", "", text));
      bracket.appendChild(card);
      if (state.scout && state.scout.prices) applyMarketFoot(state.scout.prices);
      return;
    }
    parsed.slice(0, 4).forEach((item, index) => {
      const card = el("article", "contender");
      card.dataset.slot = String(index);
      card.dataset.name = item.name.toLowerCase();
      card.appendChild(el("span", "contender-no", "CONTENDER " + String(item.number).padStart(2, "0")));
      card.appendChild(el("h3", "", item.name));
      card.appendChild(el("p", "", item.body || "No card text."));
      bracket.appendChild(card);
    });
    if (state.scout && state.scout.prices) applyMarketFoot(state.scout.prices);
  }

  function markVerdict(text) {
    const winnerMatch = String(text).match(/winner\s*[:\-]\s*([^\n.]+)/i);
    const eliminatedMatch = String(text).match(/eliminated\s*[:\-]\s*([^\n.]+)/i);
    const cards = document.querySelectorAll(".contender[data-slot]");
    cards.forEach((card) => {
      const name = String(card.dataset.name || "").toLowerCase();
      const heading = card.querySelector("h3");
      const candidate = (name || (heading ? heading.textContent.toLowerCase() : "")).trim();
      if (!candidate) return;
      if (winnerMatch && (winnerMatch[1].toLowerCase().includes(candidate) || candidate.includes(winnerMatch[1].toLowerCase().trim()))) {
        card.classList.add("winner");
        card.classList.remove("eliminated");
        card.appendChild(el("span", "verdict-tag", "WINNER"));
      } else if (
        eliminatedMatch &&
        (eliminatedMatch[1].toLowerCase().includes(candidate) || candidate.includes(eliminatedMatch[1].toLowerCase().trim()))
      ) {
        card.classList.add("eliminated");
        card.appendChild(el("span", "verdict-tag", "OUT"));
      }
    });
  }

  function streamingTurn(persona, speaker) {
    if (state.streams.has(persona)) return state.streams.get(persona);
    const wrapper = el("div", "turn streaming");
    wrapper.appendChild(el("div", "speaker", String(speaker || persona || "speaker")));
    const body = el("div", "body", "");
    wrapper.appendChild(body);
    $("#turns").appendChild(wrapper);
    state.streams.set(persona, { wrapper, body });
    return state.streams.get(persona);
  }

  function removeStream(persona) {
    const stream = state.streams.get(persona);
    if (stream && stream.wrapper.parentNode) stream.wrapper.remove();
    state.streams.delete(persona);
  }

  function addTurn(turn) {
    const persona = String(turn.persona || "unknown");
    const speaker = String(turn.speaker || state.names[persona] || persona);
    const content = String(turn.content || "");
    if (!content) return;
    removeStream(persona);

    const node = el("div", "turn " + persona);
    const speakerNode = el("div", "speaker", speaker);
    if (turn.round) speakerNode.appendChild(el("small", "", "R" + turn.round));
    node.appendChild(speakerNode);
    node.appendChild(el("div", "body", content));
    $("#turns").appendChild(node);
    if (persona === "producer" || /producer/i.test(speaker)) renderContenders(content);
    if (persona === "critic" || /critic/i.test(speaker)) setPanel("#critic-body", content);
    if (persona === "foreman" || /foreman/i.test(speaker)) {
      setPanel("#foreman-body", content);
      markVerdict(content);
    }
    if (persona === "architect" || /architect/i.test(speaker)) setPanel("#architect-body", content);
    if (persona === "coroner" || /coroner/i.test(speaker)) setPanel("#coroner-body", content);
    state.turns.push(turn);
    const turns = $("#turns");
    turns.scrollTop = turns.scrollHeight;
  }

  function addOperator(message) {
    const node = el("div", "turn operator");
    node.appendChild(el("div", "speaker", "OPERATOR // FOLLOW-UP"));
    node.appendChild(el("div", "body", String(message || "")));
    $("#turns").appendChild(node);
    $("#turns").scrollTop = $("#turns").scrollHeight;
  }

  // ── session flow ───────────────────────────────────────────────────────────
  async function launch() {
    const topic = $("#seed-input").value.trim();
    if (!topic) {
      showError("The seed is empty. Give the room something to argue about.");
      $("#seed-input").focus();
      return;
    }
    showError("");
    const button = $("#launch-button");
    button.disabled = true;
    button.textContent = "CONVENING…";
    resetStage();
    setStatus("OPENING", "live");
    state.active = true;
    state.done = false;
    state.eventCount = 0;
    state.mode = $("#mode-select").value || "arena";
    document.body.dataset.mode = state.mode;
    $("#stage-title").textContent = ($("#mode-select").selectedOptions[0]?.textContent || state.mode) + " // FLOOR";

    const constraints = $("#constraint-input").value.trim();
    const body = {
      mode: state.mode,
      provider: $("#provider-select").value === "auto" ? undefined : $("#provider-select").value,
      topic,
      options: constraints ? { constraints } : undefined,
      scout_context: $("#attach-scouts").checked ? { live: true } : undefined,
    };

    try {
      const data = await api("/sessions", { method: "POST", body: JSON.stringify(body) });
      state.sessionId = data.session_id;
      $("#session-line").textContent = "SESSION // " + data.session_id + " // " + String(data.mode).toUpperCase();
      connect(0);
      loadScouts();
    } catch (error) {
      state.active = false;
      setStatus("FAULT", "error");
      showError("Could not open the room: " + error.message);
    } finally {
      button.disabled = false;
      button.textContent = "CONVENE THE ROOM";
    }
  }

  function connect(since) {
    if (!state.sessionId) return;
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    const source = new EventSource(withToken("/sessions/" + state.sessionId + "/events?since=" + Math.max(0, since)));
    state.source = source;
    source.onopen = () => {
      if (state.active) {
        setStatus("LIVE", "live");
        setLiveFlag(true);
      }
    };
    source.onerror = () => {
      if (state.source !== source) return;
      if (!state.active) return;
      source.close();
      window.setTimeout(() => {
        if (state.active && state.sessionId) connect(state.eventCount);
      }, 1600);
    };
    EVENT_TYPES.forEach((type) => {
      source.addEventListener(type, (event) => {
        if (state.source !== source) return;
        state.eventCount += 1;
        let payload = {};
        try {
          payload = JSON.parse(event.data);
        } catch (error) {
          return;
        }
        handle(type, payload);
      });
    });
  }

  function closeSource() {
    if (state.source) {
      state.source.close();
      state.source = null;
    }
  }

  function handle(type, data) {
    if (type === "session_start") {
      state.mode = data.mode || state.mode;
      document.body.dataset.mode = state.mode;
      state.names = {};
      (data.personas || []).forEach((persona) => {
        state.names[persona.key] = persona.name;
      });
      $("#stage-title").textContent = String(data.label || state.mode).toUpperCase() + " // FLOOR";
      setStatus("IN SESSION", "live");
      setLiveFlag(true);
      return;
    }
    if (type === "status") {
      setStatus(data.message || "IN SESSION");
      return;
    }
    if (type === "token_chunk") {
      const persona = String(data.persona || "speaker");
      const stream = streamingTurn(persona, state.names[persona] || persona);
      stream.body.textContent += String(data.text || "");
      const turns = $("#turns");
      turns.scrollTop = turns.scrollHeight;
      return;
    }
    if (type === "persona_turn") {
      addTurn(data);
      return;
    }
    if (type === "operator_message") {
      addOperator(data.message);
      return;
    }
    if (type === "iteration_start") {
      setStatus("REVISION", "live");
      setLiveFlag(true);
      return;
    }
    if (type === "memory_saved") {
      $("#session-line").textContent =
        "SESSION // " + state.sessionId + " // MEMORY #" + String(data.memory_id || "?");
      return;
    }
    if (type === "error") {
      state.active = false;
      showError(String(data.message || "The session failed."));
      setStatus("FAULT", "error");
      closeSource();
      return;
    }
    if (type === "session_end") {
      state.active = false;
      state.done = true;
      closeSource();
      $("#turns").innerHTML = "";
      (data.turns || []).forEach((turn) => addTurn(turn));
      if (!(data.turns || []).length) $("#turns").appendChild(el("p", "muted", "Session ended without turns."));
      $("#followup-input").disabled = false;
      $("#followup-button").disabled = false;
      setLiveFlag(false);
      setStatus("VERDICT IN", "done");
      if (data.memory_id) {
        $("#session-line").textContent =
          "SESSION // " + state.sessionId + " // MEMORY #" + String(data.memory_id);
      }
    }
  }

  async function followUp(event) {
    event.preventDefault();
    if (!state.sessionId || state.active) return;
    const input = $("#followup-input");
    const message = input.value.trim();
    if (!message) return;
    const button = $("#followup-button");
    button.disabled = true;
    try {
      await api("/sessions/" + state.sessionId + "/messages", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      input.value = "";
      state.active = true;
      state.done = false;
      showError("");
      setStatus("REVISION", "live");
      connect(state.eventCount);
    } catch (error) {
      showError("Follow-up rejected: " + error.message);
      button.disabled = false;
    }
  }

  // ── microphone ─────────────────────────────────────────────────────────────
  function setupMicrophone() {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    const button = $("#mic-button");
    const status = $("#mic-status");
    if (!Speech) {
      button.disabled = true;
      status.textContent = "speech unavailable — type instead";
      button.title = "This browser has no Web Speech API. Type the seed instead.";
      return;
    }
    let recognition = null;
    let base = "";
    button.addEventListener("click", () => {
      if (recognition) {
        recognition.stop();
        return;
      }
      recognition = new Speech();
      recognition.lang = "en-US";
      recognition.continuous = false;
      recognition.interimResults = true;
      base = $("#seed-input").value.trim();
      let finalText = "";
      recognition.onresult = (event) => {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const transcript = event.results[index][0].transcript;
          if (event.results[index].isFinal) finalText += transcript + " ";
          else interim += transcript;
        }
        $("#seed-input").value = (base + " " + finalText + interim).trim();
      };
      recognition.onstart = () => {
        button.setAttribute("aria-pressed", "true");
        status.textContent = "listening…";
      };
      recognition.onerror = (event) => {
        status.textContent = event.error === "not-allowed" ? "mic blocked" : "mic error";
      };
      recognition.onend = () => {
        button.setAttribute("aria-pressed", "false");
        status.textContent = finalText ? "captured" : "or type it";
        recognition = null;
      };
      try {
        recognition.start();
      } catch (error) {
        recognition = null;
        status.textContent = "mic unavailable";
      }
    });
  }

  // ── chrome ─────────────────────────────────────────────────────────────────
  function setupTheme() {
    const button = $("#theme-toggle");
    let saved = "";
    try {
      saved = window.localStorage.getItem("hotseat-theme") || "";
    } catch (error) {
      saved = "";
    }
    if (saved === "switchboard") {
      document.documentElement.dataset.theme = "switchboard";
      button.setAttribute("aria-pressed", "true");
      button.lastChild.textContent = " TERMINAL";
    }
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "switchboard" ? "terminal" : "switchboard";
      document.documentElement.dataset.theme = next;
      button.setAttribute("aria-pressed", next === "switchboard" ? "true" : "false");
      button.lastChild.textContent = next === "switchboard" ? " TERMINAL" : " SWITCHBOARD";
      try {
        window.localStorage.setItem("hotseat-theme", next);
      } catch (error) {
        /* storage is optional */
      }
    });
  }

  function setupDrawer() {
    const toggle = $("#scout-drawer-toggle");
    toggle.addEventListener("click", () => {
      const drawer = $("#scout-drawer");
      const open = drawer.hidden;
      drawer.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "CLOSE DRAWER" : "OPEN DRAWER";
    });
  }

  function init() {
    setupTheme();
    setupDrawer();
    setupMicrophone();
    $("#scout-refresh").addEventListener("click", refreshScouts);
    $("#launch-button").addEventListener("click", launch);
    $("#provider-select").addEventListener("change", updateProviderHint);
    $("#mode-select").addEventListener("change", () => {
      if (state.active) return;
      state.mode = $("#mode-select").value || "arena";
      document.body.dataset.mode = state.mode;
      $("#stage-title").textContent =
        ($("#mode-select").selectedOptions[0]?.textContent || state.mode) + " // FLOOR";
    });
    document.body.dataset.mode = state.mode;
    $("#followup-form").addEventListener("submit", followUp);
    $("#seed-input").addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") launch();
    });
    loadMetadata().then(loadScouts);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
