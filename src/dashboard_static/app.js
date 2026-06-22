const tokenInput = document.querySelector("#token-input");
const tokenForm = document.querySelector("#token-form");
const probeButton = document.querySelector("#probe-button");
const refreshButton = document.querySelector("#refresh");
const sessionEvents = document.querySelector("#session-events");

function setText(selector, text) {
  document.querySelector(selector).textContent = text;
}

function setClass(selector, className) {
  document.querySelector(selector).className = className;
}

function statusClass(ok, warn = false) {
  if (ok) return "status ok";
  if (warn) return "status warn";
  return "status bad";
}

function addSessionEvent(text) {
  const item = document.createElement("li");
  item.textContent = `${new Date().toLocaleTimeString()} ${text}`;
  sessionEvents.prepend(item);
  while (sessionEvents.children.length > 8) {
    sessionEvents.lastElementChild.remove();
  }
}

async function dashboardApi(path) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

async function providerApi(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
  });
  const data = await response.json();
  return { response, data };
}

async function checkAuthGate() {
  try {
    const { response } = await providerApi("/v1/models", {
      headers: { "X-Dashboard-Check": "auth-gate" },
    });
    if (response.status === 401) {
      return { status: 401, label: "Protected", detail: "Bearer token required", ok: true };
    }
    if (response.ok) {
      return { status: response.status, label: "Open", detail: "Models answered without auth", ok: false };
    }
    return { status: response.status, label: "Unexpected", detail: `HTTP ${response.status}`, ok: false };
  } catch (error) {
    return { status: 0, label: "Error", detail: error.message, ok: false };
  }
}

function formatBytes(value) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)} MB`;
  if (value >= 1000) return `${Math.round(value / 1000)} KB`;
  return `${value} B`;
}

function renderStatus(data) {
  const health = data.provider.health;
  const runner = data.provider.runner;
  const limits = data.provider.limits;
  const events = data.events;

  setText("#health-value", health.ok ? "OK" : "Unready");
  setClass("#health-value", health.ok ? "ok-text" : "bad-text");
  setText("#health-detail", health.status);

  setText("#runner-value", runner.busy ? "Busy" : runner.ready ? "Ready" : "Unready");
  setClass("#runner-value", runner.ready && !runner.busy ? "ok-text" : runner.busy ? "warn-text" : "bad-text");
  setText("#runner-detail", `${runner.activeRuns}/${runner.maxConcurrentRuns} active - ${data.provider.modelAlias}`);

  setText("#event-value", String(events.total));
  setText("#event-detail", `${events.errors} errors, p95 ${events.p95DurationMs ?? "-"} ms`);

  setText("#limit-body", formatBytes(limits.maxBodyBytes));
  setText("#limit-text", `${limits.maxTotalTextChars.toLocaleString()} chars`);
  setText("#limit-timeout", `${limits.requestTimeoutSeconds}s`);
  setText("#limit-concurrency", `${limits.maxConcurrentRuns} run${limits.maxConcurrentRuns === 1 ? "" : "s"}`);
  setText("#limit-queue", `${limits.queueWaitSeconds}s`);
  setText("#last-refresh", `Updated ${new Date().toLocaleTimeString()}`);
}

function renderAuthGate(authGate) {
  setText("#auth-value", authGate.status ? String(authGate.status) : authGate.label);
  setClass("#auth-value", authGate.ok ? "ok-text" : "bad-text");
  setText("#auth-detail", authGate.detail);
}

function renderEvents(data) {
  const tbody = document.querySelector("#event-table");
  tbody.replaceChildren();
  const rows = data.events || [];
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty";
    cell.textContent = "No events yet";
    row.appendChild(cell);
    tbody.appendChild(row);
  }
  for (const event of rows.slice().reverse()) {
    const row = document.createElement("tr");
    const values = [
      event.time,
      event.method,
      event.path,
      String(event.status),
      `${event.durationMs} ms`,
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    row.children[3].className = "status-code";
    tbody.appendChild(row);
  }
  const summary = data.summary || {};
  setText("#event-summary", `${summary.total || 0} rows, ${summary.errors || 0} errors, p95 ${summary.p95DurationMs ?? "-"} ms`);
}

async function refreshDashboard() {
  refreshButton.disabled = true;
  try {
    const status = await dashboardApi("/dashboard/api/status");
    const authGate = await checkAuthGate();
    renderStatus(status);
    renderAuthGate(authGate);
    const events = await dashboardApi("/dashboard/api/events");
    renderEvents(events);
  } catch (error) {
    addSessionEvent(`refresh failed: ${error.message}`);
  } finally {
    refreshButton.disabled = false;
  }
}

function currentBearer() {
  return tokenInput.value.trim();
}

tokenForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = currentBearer();
  setClass("#models-status", "status neutral");
  setText("#models-status", "Checking");
  setText("#models-result", "Checking model endpoint...");
  try {
    const { response, data } = await providerApi("/v1/models", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const modelIds = Array.isArray(data.data)
      ? data.data.map((item) => item.id).filter(Boolean)
      : [];
    setClass("#models-status", statusClass(response.ok));
    setText("#models-status", response.ok ? "OK" : `HTTP ${response.status}`);
    setText("#models-result", response.ok ? `Models: ${modelIds.join(", ") || "-"}` : data.error?.message || "Request failed");
    addSessionEvent(`models returned ${response.status}`);
  } catch (error) {
    setClass("#models-status", "status bad");
    setText("#models-status", "Error");
    setText("#models-result", error.message);
    addSessionEvent(`models failed: ${error.message}`);
  } finally {
    await refreshDashboard();
  }
});

probeButton.addEventListener("click", async () => {
  const token = currentBearer();
  probeButton.disabled = true;
  setClass("#probe-status", "status neutral");
  setText("#probe-status", "Running");
  setText("#probe-result", "Waiting for Codex...");
  try {
    const { response, data } = await providerApi("/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "codex-cli-default",
        max_tokens: 20,
        messages: [{ role: "user", content: "Reply with exactly: dashboard ok" }],
      }),
    });
    const content = data.choices?.[0]?.message?.content || data.error?.message || "No response content";
    setClass("#probe-status", statusClass(response.ok, response.status === 429));
    setText("#probe-status", response.ok ? "OK" : `HTTP ${response.status}`);
    setText("#probe-result", content);
    addSessionEvent(`probe returned ${response.status}`);
  } catch (error) {
    setClass("#probe-status", "status bad");
    setText("#probe-status", "Error");
    setText("#probe-result", error.message);
    addSessionEvent(`probe failed: ${error.message}`);
  } finally {
    probeButton.disabled = false;
    await refreshDashboard();
  }
});

refreshButton.addEventListener("click", refreshDashboard);

refreshDashboard();
setInterval(refreshDashboard, 15000);
