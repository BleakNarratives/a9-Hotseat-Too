/* The Hot Seat — mobile/tablet companion.
   One API surface, a three-state flow, zero dependencies. */
(function () {
  "use strict";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

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

  const STEPS = [
    ["producer", "PRODUCER"],
    ["critic", "CRITIC"],
    ["foreman", "FOREMAN"],
    ["architect", "ARCHITECT"],
    ["coroner", "CORONER"],
  ];

  const state = {
    screen: "setup",
    sessionId: null,
    eventCount: 0,
    active: false,
    done: false,
    source: null,
    mode: "arena",
    provider: "",
    topic: "",
    constraints: new Set(),
    constraintsText: "",
    roles: [],
    providerStatus: [],
    providers: [],
    names: {},
    turns: [],
    panels: {},
    contenders: [],
    winner: "",
    scout: null,
    sessionScout: null,
    streams: new Map(),
    recognition: null,
  };

  function token() {
    return new URLSearchParams(window.location.search).get("token") || "";
  }

  function withToken(path) {
    const value = token();
    if (!value) return path;
    return path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(value);
  }

  function syncViewLinks() {
    $$("[data-view-link]").forEach((link) => {
      const href = link.getAttribute("href");
      if (href) link.href = withToken(href);
    });
  }

  async function api(path, options) {
    const headers = { "Content-Type": "application/json" };
    if (token()) headers.Authorization = "Bearer " + token();
    const response = await fetch(withToken(path), { ...(options || {}), headers });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("This room needs its access link. Reopen the shared URL with ?token=.");
      }
      throw new Error("The room didn't answer. Give it a moment and try again.");
    }
    return payload;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function cleanText(value) {
    let text = String(value || "").replace(/\r\n/g, "\n");
    text = text
      .split("\n")
      .filter((line) => !/^\s*[=\-_*~•·—–]{3,}\s*$/.test(line))
      .join("\n")
      .replace(/[ \t]+={1,}[ \t]+/g, " — ")
      .replace(/(?:\s*(?:\.{2,}|…))+\s*$/g, "");
    return text.replace(/\n{3,}/g, "\n\n").trim();
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

  function setStatus(text, tone) {
    const value = String(text || "IDLE").toUpperCase();
    const stage = $("#stage-status");
    const bar = $("#bar-status");
    const conn = $("#conn-pill");
    [stage, bar, conn].forEach((node) => {
      if (!node) return;
      node.textContent = value;
      if (tone) node.dataset.state = tone;
    });
    if (conn) {
      if (tone === "live") conn.textContent = "LIVE";
      else if (tone === "done") conn.textContent = "READY";
      else if (tone === "error") conn.textContent = "FAULT";
      else conn.textContent = "READY";
    }
  }

  function setScreen(name) {
    state.screen = name;
    document.body.dataset.screen = name;
    $("#setup-screen").hidden = name !== "setup";
    $("#live-screen").hidden = name !== "live";
    $("#verdict-screen").hidden = name !== "verdict";
    $("#live-bar").hidden = name === "setup";
    updateStagePlaceholder();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function isTablet() {
    return window.matchMedia("(min-width: 601px) and (max-width: 1024px)").matches;
  }

  function updateStagePlaceholder() {
    const placeholder = $("#stage-placeholder");
    if (!placeholder) return;
    placeholder.hidden = !(state.screen === "setup" && isTablet());
  }

  // ── setup metadata ─────────────────────────────────────────────────────────
  function fillSelect(select, entries, preferred) {
    clear(select);
    entries.forEach((entry) => {
      const option = document.createElement("option");
      option.value = entry.value;
      option.textContent = entry.label;
      if (entry.title) option.title = entry.title;
      if (entry.disabled) option.disabled = true;
      if (entry.configured !== undefined) option.dataset.configured = entry.configured ? "1" : "0";
      select.appendChild(option);
    });
    const target =
      entries.find((entry) => entry.value === preferred && !entry.disabled) ||
      entries.find((entry) => !entry.disabled);
    if (target) select.value = target.value;
  }

  async function loadMetadata() {
    let modes = [];
    let providers = [];
    let statusRows = [];
    try {
      const [modeData, providerData] = await Promise.all([api("/modes"), api("/providers")]);
      modes = modeData.modes || [];
      providers = providerData.providers || [];
    } catch (error) {
      showError("The room is still waking up. Try again in a moment.");
    }
    try {
      const statusData = await api("/providers/status");
      statusRows = statusData.providers || [];
    } catch (error) {
      statusRows = [];
    }
    state.providerStatus = statusRows;
    state.providers = providers;

    if (!modes.length) {
      modes = [
        { mode: "arena", label: "The Arena", description: "Four contenders, one verdict." },
        { mode: "bmad", label: "BMAD Brief", description: "One pass to a build brief." },
        { mode: "classic", label: "Classic Panel", description: "Three voices, straight answer." },
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

    const statusMap = new Map(statusRows.map((item) => [item.name, item]));
    const fallbackProviders = [
      { name: "openrouter", requires_key: true },
      { name: "mistral", requires_key: true },
      { name: "anthropic", requires_key: true },
      { name: "cerebras", requires_key: true },
      { name: "groq", requires_key: true },
      { name: "9router", requires_key: false },
      { name: "demo", requires_key: false },
    ];
    const source = providers.length ? providers : statusRows.length ? statusRows : fallbackProviders;
    const entries = [
      {
        value: "auto",
        label: "AUTO // SERVER CONFIG",
        title: "Use the server's configured provider (auto probes local runtimes, then cloud keys).",
        configured: true,
      },
    ].concat(
      source.map((item) => {
        const status = statusMap.get(item.name);
        const configured = status ? status.configured : true;
        const missing = item.requires_key && !configured;
        return {
          value: item.name,
          label:
            item.name.toUpperCase() +
            (item.offline ? " // OFFLINE" : item.requires_key ? (missing ? " // NO KEY" : " // READY") : " // LOCAL"),
          title: missing
            ? "No credential found in env, repo .env, or ~/.concierge/vault.json."
            : item.requires_key
              ? "Credential found. Retryable failures fall back to other configured providers."
              : "No key required; reachability is checked when a session starts.",
          configured,
          disabled: missing,
        };
      })
    );
    fillSelect($("#provider-select"), entries, "auto");
    updateProviderHint();
    renderProviderSummary(statusRows);
    renderProviderList(statusRows);
  }

  function renderProviderSummary(rows) {
    const summary = $("#provider-summary");
    const detail = $("#provider-summary-detail");
    if (!rows.length) {
      summary.textContent = "STATUS UNAVAILABLE";
      detail.textContent = "session can still use auto";
      return;
    }
    const ready = rows.filter((row) => row.configured);
    const missing = rows.filter((row) => row.requires_key && !row.configured);
    summary.textContent = ready.length + " READY · " + missing.length + " MISSING";
    detail.textContent = ready.length
      ? ready.slice(0, 4).map((row) => row.name).join(" · ")
      : "add a key in .env or the vault";
  }

  function renderProviderList(rows) {
    const box = $("#provider-list");
    clear(box);
    if (!rows.length) {
      box.appendChild(el("p", "field-help", "Status unavailable; auto will resolve at session start."));
      return;
    }
    rows.forEach((row) => {
      const item = el("div", "provider-row");
      item.dataset.ready = row.configured ? "true" : "false";
      item.appendChild(el("strong", "", row.name.toUpperCase()));
      item.appendChild(
        el("span", "", row.configured ? (row.requires_key ? "READY" : "LOCAL") : "MISSING KEY")
      );
      box.appendChild(item);
    });
  }

  function updateProviderHint() {
    const select = $("#provider-select");
    const selected = select.options[select.selectedIndex];
    if (!selected) return;
    $("#provider-hint").textContent =
      selected.title || "Credentials resolve automatically from env, .env, or vault.";
  }

  async function loadRoleModels() {
    const mode = $("#mode-select").value || "arena";
    try {
      const data = await api("/personas?mode=" + encodeURIComponent(mode));
      state.roles = Array.isArray(data.personas) ? data.personas : [];
    } catch (error) {
      state.roles = [];
    }
    renderRoleModels();
  }

  function renderRoleModels() {
    const box = $("#roles-list");
    clear(box);
    if (!state.roles.length) {
      box.appendChild(el("p", "field-help", "No roles loaded for this mode."));
      return;
    }
    state.roles.forEach((role) => {
      const label = el("label", "role-row");
      const heading = el("span", "role-label");
      heading.appendChild(el("strong", "", role.name || role.key));
      heading.appendChild(el("span", "", role.key));
      label.appendChild(heading);
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.role = role.key;
      input.dataset.defaultModel = role.model || "";
      input.value = role.model || "";
      input.placeholder = "default model";
      input.autocomplete = "off";
      input.spellcheck = false;
      label.appendChild(input);
      box.appendChild(label);
    });
  }

  function roleModels() {
    const values = {};
    $$("#roles-list input[data-role]").forEach((input) => {
      const value = input.value.trim();
      if (value && value !== input.dataset.defaultModel) values[input.dataset.role] = value;
    });
    return Object.keys(values).length ? values : undefined;
  }

  function constraintsString() {
    const values = Array.from(state.constraints);
    const custom = $("#constraint-input").value.trim();
    if (custom) {
      custom.split(",").forEach((part) => {
        const value = part.trim();
        if (value) values.push(value);
      });
    }
    return Array.from(new Set(values.filter(Boolean))).join(", ");
  }

  // ── scout intel ────────────────────────────────────────────────────────────
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

  function anchorLabel(anchor) {
    return String(anchor.competitor || "market") + " — " + String(anchor.price || "—");
  }

  function renderEvidenceList(box, report) {
    clear(box);
    const anchors = Array.isArray(report.market_anchors) ? report.market_anchors : [];
    const prices = Array.isArray(report.prices) ? report.prices : [];
    const items = anchors.length ? anchors : prices;
    if (!items.length) {
      box.appendChild(el("p", "field-help", "No structured anchors in the last sweep."));
      return;
    }
    items.slice(0, 4).forEach((item) => {
      const row = el("div", "anchor-row");
      row.appendChild(el("strong", "", anchorLabel(item)));
      row.appendChild(
        el(
          "span",
          "",
          [item.tier, item.period, item.product].filter(Boolean).join(" // ")
        )
      );
      box.appendChild(row);
    });
  }

  function renderScout(report) {
    if (!report) return;
    state.scout = report;
    const counts = report.counts || {};
    const signals = Array.isArray(report.signals) ? report.signals : [];
    const prices = Array.isArray(report.prices) ? report.prices : [];
    const anchors = Array.isArray(report.market_anchors) ? report.market_anchors : [];
    $("#evidence-summary").textContent =
      String(counts.signals || signals.length) +
      " signals · " +
      String(anchors.length || prices.length) +
      " anchors · " +
      scoutTime(report.generated_at);
    renderEvidenceList($("#evidence-anchors"), report);

    $("#intel-meta").textContent =
      "GENERATED " +
      scoutTime(report.generated_at) +
      " · " +
      String(counts.signals || signals.length) +
      " SIGNALS · " +
      String(counts.prices || prices.length) +
      " PRICE POINTS";
    const body = $("#intel-body");
    clear(body);

    const anchorsSection = el("section", "intel-section");
    anchorsSection.appendChild(el("h3", "", "MARKET ANCHORS"));
    if (!anchors.length) anchorsSection.appendChild(el("p", "field-help", "No structured anchors."));
    anchors.slice(0, 16).forEach((anchor) => {
      const row = el("div", "anchor-row");
      row.appendChild(el("strong", "", anchorLabel(anchor)));
      row.appendChild(
        el(
          "span",
          "",
          [anchor.tier, anchor.period, anchor.product, anchor.source].filter(Boolean).join(" // ")
        )
      );
      anchorsSection.appendChild(row);
    });
    body.appendChild(anchorsSection);

    const pricesSection = el("section", "intel-section");
    pricesSection.appendChild(el("h3", "", "COMPETITOR PRICING"));
    if (!prices.length) pricesSection.appendChild(el("p", "field-help", "No price points."));
    prices.slice(0, 12).forEach((price) => {
      const row = el("div", "anchor-row");
      row.appendChild(el("strong", "", String(price.product || "pricing") + " — " + String(price.price || "—")));
      row.appendChild(el("span", "", String(price.competitor || "market") + " // " + scoutTime(price.observed_at)));
      pricesSection.appendChild(row);
    });
    body.appendChild(pricesSection);

    const signalsSection = el("section", "intel-section");
    signalsSection.appendChild(el("h3", "", "LIVE SIGNALS"));
    if (!signals.length) signalsSection.appendChild(el("p", "field-help", "No signals in the last sweep."));
    signals.slice(0, 12).forEach((signal) => {
      const row = el("div", "signal-row");
      const link = safeUrl(signal.url);
      if (link) {
        const anchor = el("a", "", signal.title || "(untitled)");
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        row.appendChild(anchor);
      } else {
        row.appendChild(el("strong", "", signal.title || "(untitled)"));
      }
      row.appendChild(
        el(
          "span",
          "",
          String(signal.source || "scout") + " // " + scoutTime(signal.published_at) + " // weight " + safeWeight(signal.weight)
        )
      );
      signalsSection.appendChild(row);
    });
    body.appendChild(signalsSection);

    const healthSection = el("section", "intel-section");
    healthSection.appendChild(el("h3", "", "SOURCE HEALTH"));
    const sources = Array.isArray(report.sources) ? report.sources : [];
    const errors = Array.isArray(report.errors) ? report.errors : [];
    if (!sources.length && !errors.length) healthSection.appendChild(el("p", "field-help", "No sources recorded."));
    sources.forEach((source) => healthSection.appendChild(el("div", "signal-row", source)));
    errors.forEach((error) => healthSection.appendChild(el("div", "signal-row error-text", error)));
    body.appendChild(healthSection);
  }

  async function loadScouts() {
    try {
      const data = await api("/scouts/latest");
      if (data.report) renderScout(data.report);
    } catch (error) {
      $("#evidence-summary").textContent = "Scout wire unavailable.";
      $("#intel-meta").textContent = "Scout wire unavailable.";
    }
  }

  async function syncSessionScouts() {
    if (!state.sessionId) return;
    try {
      const documentData = await api("/sessions/" + state.sessionId);
      if (documentData.scouts) {
        state.sessionScout = documentData.scouts;
        renderScout(documentData.scouts);
      }
    } catch (error) {
      /* the last global report remains usable */
    }
  }

  async function refreshScouts() {
    const button = $("#intel-refresh");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "SWEEPING…";
    try {
      const seed = state.topic || $("#seed-input").value.trim();
      const data = await api("/scouts/refresh", {
        method: "POST",
        body: JSON.stringify({ seed, live: true }),
      });
      renderScout(data.report);
      showError("");
    } catch (error) {
      showError("The scout wire is quiet right now. Try the sweep again.");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function openIntel() {
    $("#intel-sheet").hidden = false;
    document.body.classList.add("sheet-open");
    $("#intel-close").focus();
  }

  function closeIntel() {
    $("#intel-sheet").hidden = true;
    document.body.classList.remove("sheet-open");
  }

  // ── progress, contenders, panels ──────────────────────────────────────────
  function renderProgress() {
    const box = $("#progress");
    clear(box);
    STEPS.forEach(([key, label]) => {
      const step = el("div", "progress-step");
      step.dataset.step = key;
      step.appendChild(el("span", "progress-bar"));
      step.appendChild(el("span", "progress-label", label));
      box.appendChild(step);
    });
  }

  function setProgress(persona, complete) {
    const index = STEPS.findIndex(([key]) => key === persona);
    if (index < 0) return;
    $$("#progress .progress-step").forEach((step, stepIndex) => {
      step.classList.toggle("is-done", stepIndex < index || (stepIndex === index && complete));
      step.classList.toggle("is-active", stepIndex === index && !complete);
    });
  }

  function setSpotlight(name, text) {
    if (name) $("#spotlight-speaker").textContent = String(name);
    if (text !== undefined) $("#spotlight-text").textContent = cleanText(text);
  }

  function resetContenders() {
    const box = $("#mobile-bracket");
    clear(box);
    const copy = [
      "The seed takes the first chair.",
      "The cheaper option is still in the hallway.",
      "The premium option is polishing its invoice.",
      "The niche wedge is hiding behind a trade magazine.",
    ];
    for (let index = 0; index < 4; index += 1) {
      const card = el("article", "contender-card empty");
      card.dataset.slot = String(index);
      card.appendChild(el("span", "number", "CONTENDER " + String(index).padStart(2, "0")));
      card.appendChild(el("h3", "", "AWAITING"));
      card.appendChild(el("p", "", copy[index]));
      box.appendChild(card);
    }
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
      body: source.slice(item.end, index + 1 < matches.length ? matches[index + 1].index : source.length).trim(),
    }));
  }

  function renderContenders(text) {
    const parsed = parseContenders(text);
    state.contenders = parsed.length
      ? parsed
      : [{ number: "00", name: "THE FOUR CONTENDERS", body: String(text || "") }];
    const box = $("#mobile-bracket");
    clear(box);
    state.contenders.slice(0, 4).forEach((item, index) => {
      const card = el("article", "contender-card");
      card.dataset.slot = String(index);
      card.dataset.name = String(item.name || "").toLowerCase();
      card.appendChild(el("span", "number", "CONTENDER " + String(item.number || "00").padStart(2, "0")));
      card.appendChild(el("h3", "", item.name || "UNNAMED"));
      card.appendChild(el("p", "", item.body || "No card text."));
      box.appendChild(card);
    });
    if (state.panels["#verdict-foreman"]) markVerdict(state.panels["#verdict-foreman"]);
  }

  function markVerdict(text) {
    const source = String(text || "");
    const winnerMatch = source.match(/winner\s*[:\-]\s*([^\n.]+)/i);
    const eliminatedMatch = source.match(/eliminated\s*[:\-]\s*([^\n.]+)/i);
    $$(".contender-card").forEach((card) => {
      card.classList.remove("winner", "eliminated");
      const old = card.querySelector(".winner-tag");
      if (old) old.remove();
      const name = String(card.dataset.name || "").trim();
      if (!name) return;
      if (
        winnerMatch &&
        (winnerMatch[1].toLowerCase().includes(name) || name.includes(winnerMatch[1].toLowerCase().trim()))
      ) {
        card.classList.add("winner");
        card.appendChild(el("span", "winner-tag", "WINNER"));
      } else if (
        eliminatedMatch &&
        (eliminatedMatch[1].toLowerCase().includes(name) || name.includes(eliminatedMatch[1].toLowerCase().trim()))
      ) {
        card.classList.add("eliminated");
        card.appendChild(el("span", "winner-tag", "OUT"));
      }
    });
  }

  function setPanel(selector, text) {
    const cleaned = cleanText(text);
    state.panels[selector] = cleaned;
    const node = $(selector);
    if (!node) return;
    clear(node);
    const paragraphs = cleaned.split(/\n{2,}/).filter((part) => part.trim());
    if (!paragraphs.length) {
      node.appendChild(el("p", "muted", "No output."));
      return;
    }
    paragraphs.forEach((part) => node.appendChild(el("p", "", part.trim())));
  }

  function panelText(selector, persona) {
    return state.panels[selector] || lastTurn(persona) || "";
  }

  function lastTurn(persona) {
    const turns = state.turns.filter((turn) => String(turn.persona || "") === persona);
    return turns.length ? String(turns[turns.length - 1].content || "") : "";
  }

  // ── turn rendering ─────────────────────────────────────────────────────────
  function streamingTurn(persona, speaker) {
    if (state.streams.has(persona)) return state.streams.get(persona);
    const wrapper = el("div", "turn streaming");
    wrapper.appendChild(el("div", "speaker", String(speaker || persona || "speaker")));
    const body = el("div", "body", "");
    wrapper.appendChild(body);
    $("#mobile-turns").appendChild(wrapper);
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
    const content = cleanText(turn.content || "");
    if (!content) return;
    removeStream(persona);

    const node = el("div", "turn " + persona);
    const speakerNode = el("div", "speaker", speaker);
    if (turn.round) speakerNode.appendChild(el("small", "", "R" + turn.round));
    node.appendChild(speakerNode);
    node.appendChild(el("div", "body", content));
    $("#mobile-turns").appendChild(node);

    if (persona === "producer" || /producer/i.test(speaker)) renderContenders(content);
    if (persona === "critic" || /critic/i.test(speaker)) {
      setPanel("#live-critic-body", content);
      setPanel("#verdict-critic", content);
    }
    if (persona === "foreman" || /foreman/i.test(speaker)) {
      setPanel("#live-foreman-body", content);
      setPanel("#verdict-foreman", content);
      markVerdict(content);
    }
    if (persona === "architect" || /architect/i.test(speaker)) {
      setPanel("#live-brief-body", content);
      setPanel("#verdict-brief", content);
    }
    if (persona === "coroner" || /coroner/i.test(speaker)) setPanel("#verdict-autopsy", content);

    state.turns.push({ ...turn, content });
    setSpotlight(speaker, content);
    setProgress(persona, true);
    $("#mobile-turns").scrollTop = $("#mobile-turns").scrollHeight;
  }

  function addOperator(message) {
    const node = el("div", "turn operator");
    node.appendChild(el("div", "speaker", "OPERATOR // FOLLOW-UP"));
    node.appendChild(el("div", "body", cleanText(message || "")));
    $("#mobile-turns").appendChild(node);
    $("#mobile-turns").scrollTop = $("#mobile-turns").scrollHeight;
  }

  function resetSessionUI() {
    closeSource();
    state.turns = [];
    state.panels = {};
    state.contenders = [];
    state.names = {};
    state.winner = "";
    state.streams.clear();
    state.eventCount = 0;
    state.done = false;
    state.sessionId = null;
    state.sessionScout = null;
    $("#live-topic").textContent = "THE ROOM IS OPENING.";
    $("#live-mode").textContent = "ARENA // LIVE";
    $("#spotlight-speaker").textContent = "THE ROOM";
    $("#spotlight-text").textContent = "The Producer is taking the first chair.";
    $("#mobile-turns").innerHTML = '<p class="muted">No turns yet.</p>';
    ["#live-brief-body", "#live-critic-body", "#live-foreman-body"].forEach((selector) => {
      const node = $(selector);
      clear(node);
      node.appendChild(el("p", "muted", "Awaiting the room."));
    });
    ["#verdict-critic", "#verdict-foreman", "#verdict-brief", "#verdict-autopsy"].forEach((selector) => {
      const node = $(selector);
      clear(node);
      node.appendChild(el("p", "muted", "Awaiting the room."));
    });
    $("#winner-name").textContent = "THE ROOM HAS SPOKEN";
    $("#winner-copy").textContent = "The Foreman's deciding difference appears here.";
    $("#followup-input").value = "";
    $("#followup-button").disabled = true;
    $("#export-status").textContent = "";
    $("#live-flag").hidden = false;
    resetContenders();
    renderProgress();
  }

  // ── tabs ───────────────────────────────────────────────────────────────────
  function activateTab(group, tab) {
    $$('[data-tab-group="' + group + '"]').forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    const panelAttr = group === "live" ? "data-live-panel" : "data-verdict-panel";
    $$("[" + panelAttr + "]").forEach((panel) => {
      panel.hidden = panel.getAttribute(panelAttr) !== tab;
    });
  }

  function setupTabs() {
    $$("[data-tab-group]").forEach((button) => {
      button.addEventListener("click", () => activateTab(button.dataset.tabGroup, button.dataset.tab));
    });
  }

  // ── session flow ───────────────────────────────────────────────────────────
  async function launch() {
    if (state.active) {
      showError("The room is already in session. Finish this one before starting another.");
      return;
    }
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
    resetSessionUI();
    state.active = true;
    state.mode = $("#mode-select").value || "arena";
    state.topic = topic;
    const provider = $("#provider-select").value;
    state.provider = provider === "auto" ? "server config" : provider;
    state.constraintsText = constraintsString();
    document.body.dataset.mode = state.mode;
    $("#live-topic").textContent = topic;
    $("#live-mode").textContent = state.mode.toUpperCase() + " // LIVE";
    setStatus("OPENING", "live");
    setScreen("live");

    const body = {
      mode: state.mode,
      provider: provider === "auto" ? undefined : provider,
      topic,
      options: state.constraintsText ? { constraints: state.constraintsText } : undefined,
      role_models: roleModels(),
      scout_context: $("#attach-scouts").checked ? { live: true } : undefined,
    };

    try {
      const data = await api("/sessions", { method: "POST", body: JSON.stringify(body) });
      state.sessionId = data.session_id;
      connect(0);
      loadScouts();
    } catch (error) {
      state.active = false;
      setStatus("FAULT", "error");
      setScreen("setup");
      showError("The room couldn't open that case. Give it another try.");
    } finally {
      button.disabled = false;
      button.textContent = "CONVENE THE ROOM";
    }
  }

  function connect(since) {
    if (!state.sessionId) return;
    closeSource();
    const source = new EventSource(
      withToken("/sessions/" + state.sessionId + "/events?since=" + Math.max(0, since || 0))
    );
    state.source = source;
    source.onopen = () => {
      if (state.active) setStatus("LIVE", "live");
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
    source.addEventListener("error", (event) => {
      if (state.source !== source) return;
      if (event && event.data) {
        try {
          handle("error", JSON.parse(event.data));
          return;
        } catch (error) {
          /* fall through to reconnect */
        }
      }
      if (!state.active) return;
      source.close();
      window.setTimeout(() => {
        if (state.active && state.sessionId) connect(state.eventCount);
      }, 1600);
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
      $("#live-mode").textContent = String(data.label || state.mode).toUpperCase() + " // LIVE";
      setStatus("IN SESSION", "live");
      setProgress("producer", false);
      setSpotlight("THE PRODUCER", "Building four fair contenders.");
      return;
    }
    if (type === "status") {
      const name = data.persona ? state.names[data.persona] || data.persona : "";
      setStatus(data.message || "IN SESSION", "live");
      if (name) setSpotlight(name, undefined);
      return;
    }
    if (type === "token_chunk") {
      const persona = String(data.persona || "speaker");
      const stream = streamingTurn(persona, state.names[persona] || persona);
      stream.body.textContent = cleanText(stream.body.textContent + String(data.text || ""));
      setSpotlight(state.names[persona] || persona, stream.body.textContent);
      setProgress(persona, false);
      const turns = $("#mobile-turns");
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
      $("#live-flag").hidden = false;
      return;
    }
    if (type === "memory_saved") {
      $("#conn-pill").title = "Memory #" + String(data.memory_id || "?");
      return;
    }
    if (type === "error") {
      state.active = false;
      setStatus("READY", "done");
      showError("The room is regrouping. Give it a moment, then try again.");
      closeSource();
      return;
    }
    if (type === "session_end") {
      state.active = false;
      state.done = true;
      state.provider = data.provider || state.provider;
      closeSource();
      state.turns = [];
      state.panels = {};
      $("#mobile-turns").innerHTML = "";
      (data.turns || []).forEach((turn) => addTurn(turn));
      if (!(data.turns || []).length) {
        $("#mobile-turns").appendChild(el("p", "muted", "Session ended without turns."));
      }
      setStatus("VERDICT IN", "done");
      $("#live-flag").hidden = true;
      $("#followup-button").disabled = false;
      renderWinner();
      activateTab("verdict", "critic");
      setScreen("verdict");
      syncSessionScouts();
    }
  }

  function renderWinner() {
    const foreman = panelText("#verdict-foreman", "foreman");
    const winnerMatch = foreman.match(/winner\s*[:\-]\s*([^\n.]+)/i);
    let name = winnerMatch ? winnerMatch[1].trim() : "";
    if (name) {
      const found = state.contenders.find((contender) => {
        const candidate = String(contender.name || "").toLowerCase();
        return candidate && (candidate.includes(name.toLowerCase()) || name.toLowerCase().includes(candidate));
      });
      if (found) name = found.name;
    }
    state.winner = name;
    $("#winner-name").textContent = name || (state.mode === "arena" ? "THE ROOM HAS SPOKEN" : "SESSION COMPLETE");
    $("#winner-copy").textContent =
      foreman.trim() ||
      panelText("#verdict-brief", "architect").trim() ||
      lastTurn("coroner") ||
      "The session ended without a written verdict.";
    markVerdict(foreman);
  }

  async function followUp(event) {
    event.preventDefault();
    if (!state.sessionId || state.active) return;
    const input = $("#followup-input");
    const message = input.value.trim();
    if (!message) {
      input.focus();
      return;
    }
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
      setStatus("REVISION", "live");
      setScreen("live");
      connect(state.eventCount);
    } catch (error) {
      showError("The room couldn't take that follow-up. Try it once more.");
      button.disabled = false;
    }
  }

  // ── Markdown export ────────────────────────────────────────────────────────
  function buildMarkdown() {
    if (!state.done || !state.turns.length) return "";
    const scoutReport = state.sessionScout || {};
    const anchors = scoutReport.market_anchors || [];
    const prices = scoutReport.prices || [];
    const lines = [
      "# THE HOT SEAT — " + (state.mode === "arena" ? "ARENA BRIEF" : "SESSION BRIEF"),
      "",
      "**Generated:** " + new Date().toISOString(),
      "**Session:** " + (state.sessionId || "unsaved"),
      "**Mode:** " + state.mode,
      "**Topic:** " + (state.topic || "untitled"),
    ];
    const constraints = state.constraintsText;
    if (constraints) lines.push("**Constraints:** " + constraints);
    if (state.winner) lines.push("**Winner:** " + state.winner);
    lines.push("");

    if (anchors.length || prices.length) {
      lines.push("## Market Anchors", "");
      anchors.slice(0, 16).forEach((anchor) => {
        lines.push(
          "- **" +
            String(anchor.competitor || "market") +
            "** — " +
            String(anchor.tier || "unknown") +
            " / " +
            String(anchor.period || "unknown") +
            " — " +
            String(anchor.price || "—") +
            (anchor.product ? " (" + String(anchor.product) + ")" : "")
        );
      });
      if (!anchors.length) {
        prices.slice(0, 8).forEach((price) => {
          lines.push("- **" + String(price.competitor || "market") + "** — " + String(price.price || "—"));
        });
      }
      lines.push("");
    }

    if (state.contenders.length) {
      lines.push("## The Bracket", "");
      state.contenders.forEach((contender) => {
        lines.push(
          "### CONTENDER " + String(contender.number || "00") + " — " + String(contender.name || "UNNAMED"),
          "",
          String(contender.body || "").trim(),
          ""
        );
      });
    }

    [
      ["## Cross-Examination", "#verdict-critic", "critic"],
      ["## The Foreman's Call", "#verdict-foreman", "foreman"],
      ["## Architect — Vertical Slice", "#verdict-brief", "architect"],
      ["## Coroner — Autopsy", "#verdict-autopsy", "coroner"],
    ].forEach(([title, selector, persona]) => {
      const text = panelText(selector, persona);
      if (text) lines.push(title, "", String(text).trim(), "");
    });

    const included = new Set(["producer", "critic", "foreman", "architect", "coroner"]);
    const rest = state.turns.filter((turn) => !included.has(String(turn.persona || "")));
    if (rest.length) {
      lines.push("## Floor Transcript", "");
      rest.forEach((turn) => {
        lines.push("### " + String(turn.speaker || turn.persona || "Speaker"), "", String(turn.content || "").trim(), "");
      });
    } else if (!state.contenders.length) {
      lines.push("## Floor Transcript", "");
      state.turns.forEach((turn) => {
        lines.push("### " + String(turn.speaker || turn.persona || "Speaker"), "", String(turn.content || "").trim(), "");
      });
    }
    return lines.join("\n").trim() + "\n";
  }

  function exportStatus(message) {
    $("#export-status").textContent = message;
    window.setTimeout(() => {
      if ($("#export-status").textContent === message) $("#export-status").textContent = "";
    }, 2400);
  }

  function downloadMarkdown() {
    const markdown = buildMarkdown();
    if (!markdown) return;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "hotseat-" + (state.mode || "arena") + "-" + (state.sessionId || "brief") + ".md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    exportStatus("Markdown downloaded.");
  }

  async function copyMarkdown() {
    const markdown = buildMarkdown();
    if (!markdown) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(markdown);
      } else {
        const area = document.createElement("textarea");
        area.value = markdown;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      exportStatus("Markdown copied.");
    } catch (error) {
      exportStatus("Copy failed — use Download .md.");
    }
  }

  async function shareMarkdown() {
    const markdown = buildMarkdown();
    if (!markdown) return;
    if (!navigator.share) {
      await copyMarkdown();
      exportStatus("Share unavailable — Markdown copied.");
      return;
    }
    try {
      await navigator.share({
        title: "The Hot Seat — Arena Brief",
        text: markdown,
      });
      exportStatus("Shared.");
    } catch (error) {
      if (error && error.name === "AbortError") return;
      await copyMarkdown();
      exportStatus("Share unavailable — Markdown copied.");
    }
  }

  // ── microphone ─────────────────────────────────────────────────────────────
  function setupDictation(button, status, getTarget) {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) {
      button.disabled = true;
      status.textContent = "speech unavailable — type instead";
      button.title = "This browser has no Web Speech API. Type instead.";
      return;
    }
    if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      button.disabled = true;
      status.textContent = "HTTPS required — type instead";
      button.title = "The microphone needs HTTPS or localhost. Type instead.";
      return;
    }
    let recognition = null;
    let base = "";
    let finalText = "";
    button.addEventListener("click", () => {
      if (navigator.onLine === false) {
        status.textContent = "offline — type instead";
        return;
      }
      if (recognition) {
        recognition.stop();
        return;
      }
      const target = getTarget();
      if (!target) return;
      recognition = new Speech();
      recognition.lang = "en-US";
      recognition.continuous = false;
      recognition.interimResults = true;
      base = target.value.trim();
      finalText = "";
      recognition.onresult = (event) => {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const transcript = event.results[index][0].transcript;
          if (event.results[index].isFinal) finalText += transcript + " ";
          else interim += transcript;
        }
        target.value = (base + " " + finalText + interim).trim();
      };
      recognition.onstart = () => {
        button.setAttribute("aria-pressed", "true");
        status.textContent = "listening…";
      };
      recognition.onerror = (event) => {
        const messages = {
          "not-allowed": "mic blocked — type instead",
          "service-not-allowed": "mic blocked — type instead",
          "no-speech": "no speech — try again",
          "audio-capture": "no microphone — type instead",
          network: "offline — type instead",
        };
        status.textContent = messages[event.error] || "mic error — type instead";
      };
      recognition.onend = () => {
        button.setAttribute("aria-pressed", "false");
        status.textContent = finalText ? "captured" : "tap to dictate";
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
  function setupAdvanced() {
    $("#mode-select").addEventListener("change", () => {
      if (state.active) return;
      loadRoleModels();
    });
    $("#provider-select").addEventListener("change", updateProviderHint);
    $("#roles-clear").addEventListener("click", () => {
      $$("#roles-list input[data-role]").forEach((input) => {
        input.value = "";
      });
    });
  }

  function setupConstraints() {
    $$("#constraint-chips .chip").forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.constraint;
        const selected = !state.constraints.has(value);
        if (selected) state.constraints.add(value);
        else state.constraints.delete(value);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    });
  }

  function setupChrome() {
    syncViewLinks();
    updateStagePlaceholder();
    window.addEventListener("resize", updateStagePlaceholder);
    setupTabs();
    setupAdvanced();
    setupConstraints();
    setupDictation($("#seed-mic"), $("#seed-mic-status"), () => $("#seed-input"));
    setupDictation($("#live-mic"), $("#mic-status"), () => $("#followup-input"));

    $("#open-intel").addEventListener("click", openIntel);
    $("#intel-close").addEventListener("click", closeIntel);
    $$("[data-close-intel]").forEach((node) => node.addEventListener("click", closeIntel));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$("#intel-sheet").hidden) closeIntel();
    });
    $("#intel-refresh").addEventListener("click", refreshScouts);
    $("#launch-button").addEventListener("click", launch);
    $("#setup-form").addEventListener("submit", (event) => event.preventDefault());
    $("#seed-input").addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") launch();
    });
    $("#followup-form").addEventListener("submit", followUp);
    $("#share-button").addEventListener("click", shareMarkdown);
    $("#copy-button").addEventListener("click", copyMarkdown);
    $("#download-button").addEventListener("click", downloadMarkdown);
    $("#new-idea").addEventListener("click", () => {
      if (state.active) return;
      showError("");
      setScreen("setup");
      $("#seed-input").focus();
    });
  }

  function init() {
    setupChrome();
    renderProgress();
    resetContenders();
    setScreen("setup");
    setStatus("READY", "idle");
    loadMetadata().then(() => {
      loadRoleModels();
      loadScouts();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
