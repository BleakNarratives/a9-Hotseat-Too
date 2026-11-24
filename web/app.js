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
    sessionScout: null,
    providerStatus: [],
    roles: [],
    contenders: [],
    panels: {},
    topic: "",
    provider: "",
    constraints: "",
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
      showError("Could not load bridge metadata: " + error.message);
    }
    try {
      const statusData = await api("/providers/status");
      statusRows = statusData.providers || [];
      state.providerStatus = statusRows;
      renderProviderStatus(statusRows);
    } catch (error) {
      state.providerStatus = [];
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
    const providerEntries = [
      { value: "auto", label: "AUTO // SERVER CONFIG", title: "Use the server's configured provider (auto probes 9router, then cloud keys).", configured: true },
    ].concat(
      (providers.length ? providers : statusRows.length ? statusRows : fallbackProviders).map((item) => {
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
              ? "Credential found. Retryable failures will fall back to other configured providers."
              : "No key required; reachability is checked when a session starts.",
          configured,
          disabled: missing,
        };
      })
    );
    fillSelect($("#provider-select"), providerEntries, "auto");
    updateProviderHint();
  }

  function renderProviderStatus(rows) {
    const box = $("#provider-badges");
    clear(box);
    rows.forEach((row) => {
      const badge = el("span", "provider-badge", row.name.toUpperCase());
      badge.dataset.state = row.configured ? "ready" : "missing";
      badge.title = row.configured
        ? row.requires_key
          ? "Credential discovered (" + (row.credential_names || []).join(" / ") + ")"
          : "No credential required"
        : "No credential found for " + (row.credential_names || []).join(" / ");
      box.appendChild(badge);
    });
    if (!rows.length) box.appendChild(el("span", "hint", "status unavailable"));
  }

  function updateProviderHint() {
    const select = $("#provider-select");
    const selected = select.options[select.selectedIndex];
    if (!selected) return;
    let hint = selected.title || "Credentials resolve automatically from env, .env, or vault.";
    if (selected.value !== "auto" && selected.dataset.configured === "0") {
      hint = "No credential discovered. Add it to .env or ~/.concierge/vault.json, then restart the bridge.";
    }
    $("#provider-hint").textContent = hint;
  }

  // ── role model routing ──────────────────────────────────────────────────────
  async function loadRoleModels() {
    const mode = $("#mode-select").value || "arena";
    const box = $("#roles-list");
    try {
      const data = await api("/personas?mode=" + encodeURIComponent(mode));
      state.roles = Array.isArray(data.personas) ? data.personas : [];
    } catch (error) {
      state.roles = [];
    }
    renderRoleDrawer();
  }

  function renderRoleDrawer() {
    const box = $("#roles-list");
    clear(box);
    if (!state.roles.length) {
      box.appendChild(el("p", "muted", "No roles loaded."));
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
    document.querySelectorAll("#roles-list input[data-role]").forEach((input) => {
      const value = input.value.trim();
      if (value && value !== input.dataset.defaultModel) values[input.dataset.role] = value;
    });
    return Object.keys(values).length ? values : undefined;
  }

  function setupRoles() {
    const toggle = $("#roles-toggle");
    toggle.addEventListener("click", () => {
      const drawer = $("#roles-drawer");
      const open = drawer.hidden;
      drawer.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && !state.roles.length) loadRoleModels();
    });
    $("#roles-clear").addEventListener("click", () => {
      document.querySelectorAll("#roles-list input[data-role]").forEach((input) => {
        input.value = "";
      });
    });
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

    const anchors = Array.isArray(report.market_anchors) ? report.market_anchors : [];
    const anchorBox = $("#scout-anchors");
    clear(anchorBox);
    if (!anchors.length) anchorBox.appendChild(el("p", "muted", "No structured anchors in the last sweep."));
    anchors.slice(0, 16).forEach((anchor) => {
      const row = el("div", "scout-row");
      row.appendChild(el("span", "", String(anchor.competitor || "market") + " — " + String(anchor.price || "—")));
      row.appendChild(
        el(
          "span",
          "meta",
          String(anchor.tier || "unknown") +
            " // " +
            String(anchor.period || "unknown") +
            " // " +
            String(anchor.product || "") +
            (anchor.source ? " // " + String(anchor.source) : "")
        )
      );
      anchorBox.appendChild(row);
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
    state.sessionScout = null;
    state.contenders = [];
    state.panels = {};
    state.streams.clear();
    $("#export-button").disabled = true;
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
    state.panels[selector] = String(text || "");
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
    state.contenders = parsed.length
      ? parsed
      : [{ number: "00", name: "THE FOUR CONTENDERS", body: String(text || "") }];
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

  // ── export ─────────────────────────────────────────────────────────────────
  function lastTurn(persona) {
    const turns = state.turns.filter((turn) => String(turn.persona || "") === persona);
    return turns.length ? String(turns[turns.length - 1].content || "") : "";
  }

  function panelText(selector, persona) {
    return state.panels[selector] || lastTurn(persona) || "";
  }

  function exportMarkdown() {
    if (!state.done || !state.turns.length) return;
    const headline = state.mode === "arena" ? "THE HOT SEAT — ARENA BRIEF" : "THE HOT SEAT — SESSION BRIEF";
    const lines = [
      "# " + headline,
      "",
      "**Generated:** " + new Date().toISOString(),
      "**Session:** " + (state.sessionId || "unsaved"),
      "**Mode:** " + state.mode,
      "**Provider:** " + (state.provider || "server config"),
      "**Topic:** " + (state.topic || "untitled"),
    ];
    if (state.constraints) lines.push("**Constraints:** " + state.constraints);
    lines.push("");

    const scoutReport = state.sessionScout || state.scout || {};
    const anchors = scoutReport.market_anchors || [];
    const prices = scoutReport.prices || [];
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
        lines.push("### CONTENDER " + String(contender.number || "00") + " — " + String(contender.name || "UNNAMED"));
        lines.push("", String(contender.body || "").trim(), "");
      });
    }

    const sections = [
      ["## Cross-Examination", "#critic-body", "critic"],
      ["## The Foreman's Call", "#foreman-body", "foreman"],
      ["## Architect — Vertical Slice", "#architect-body", "architect"],
      ["## Coroner — Autopsy", "#coroner-body", "coroner"],
    ];
    sections.forEach(([title, selector, persona]) => {
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
    }
    if (!state.contenders.length && !rest.length) {
      lines.push("## Floor Transcript", "");
      state.turns.forEach((turn) => {
        lines.push("### " + String(turn.speaker || turn.persona || "Speaker"), "", String(turn.content || "").trim(), "");
      });
    }

    const blob = new Blob([lines.join("\n").trim() + "\n"], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "hotseat-" + (state.mode || "arena") + "-" + (state.sessionId || "brief") + ".md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    const button = $("#export-button");
    const original = button.textContent;
    button.textContent = "EXPORTED";
    window.setTimeout(() => {
      button.textContent = original;
    }, 1400);
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
    const provider = $("#provider-select").value;
    state.topic = topic;
    state.provider = provider === "auto" ? "server config" : provider;
    state.constraints = constraints;
    const body = {
      mode: state.mode,
      provider: provider === "auto" ? undefined : provider,
      topic,
      options: constraints ? { constraints } : undefined,
      role_models: roleModels(),
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
      state.turns = [];
      clear($("#turns"));
      (data.turns || []).forEach((turn) => addTurn(turn));
      if (!(data.turns || []).length) $("#turns").appendChild(el("p", "muted", "Session ended without turns."));
      $("#export-button").disabled = !state.turns.length;
      $("#followup-input").disabled = false;
      $("#followup-button").disabled = false;
      setLiveFlag(false);
      setStatus(data.fallback_used ? "VERDICT IN // FALLBACK" : "VERDICT IN", "done");
      syncSessionScouts();
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
      $("#export-button").disabled = true;
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
    if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      button.disabled = true;
      status.textContent = "HTTPS required — type instead";
      button.title = "The microphone needs HTTPS or localhost. Type the seed instead.";
      return;
    }
    let recognition = null;
    let base = "";
    button.addEventListener("click", () => {
      if (navigator.onLine === false) {
        status.textContent = "offline — type instead";
        return;
      }
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
        const messages = {
          "not-allowed": "mic blocked — type instead",
          "service-not-allowed": "mic blocked — type instead",
          "no-speech": "no speech — try again or type",
          "audio-capture": "no microphone — type instead",
          network: "offline — type instead",
        };
        status.textContent = messages[event.error] || "mic error — type instead";
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
    setupRoles();
    $("#scout-refresh").addEventListener("click", refreshScouts);
    $("#launch-button").addEventListener("click", launch);
    $("#export-button").addEventListener("click", exportMarkdown);
    $("#provider-select").addEventListener("change", updateProviderHint);
    $("#mode-select").addEventListener("change", () => {
      if (state.active) return;
      state.mode = $("#mode-select").value || "arena";
      document.body.dataset.mode = state.mode;
      $("#stage-title").textContent =
        ($("#mode-select").selectedOptions[0]?.textContent || state.mode) + " // FLOOR";
      loadRoleModels();
    });
    document.body.dataset.mode = state.mode;
    $("#followup-form").addEventListener("submit", followUp);
    $("#seed-input").addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") launch();
    });
    loadMetadata().then(() => {
      loadRoleModels();
      loadScouts();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
