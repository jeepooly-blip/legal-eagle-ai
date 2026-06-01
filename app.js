// Legal Eagle AI - frontend
//
// This file is served as a static asset by Vercel. It calls the FastAPI backend
// (deployed on Railway) and renders the structured report.

const API_BASE = (() => {
  // Allow override via window.API_BASE (set in index.html or by hosting config).
  if (window.API_BASE) return window.API_BASE;
  // In dev (Vercel preview / local), fall back to localhost.
  if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
    return "http://127.0.0.1:8000";
  }
  // Production: replace with your Railway URL via window.API_BASE in index.html,
  // or hard-code here. Example: return "https://legal-eagle-api.up.railway.app";
  return "https://legal-eagle-api.up.railway.app";
})();

// ---------- DOM helpers ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
};
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Health check ----------
async function checkHealth() {
  const dot = $("#backend-status");
  const label = $("#backend-label");
  try {
    const r = await fetch(`${API_BASE}/healthz`, { method: "GET" });
    if (r.ok) {
      dot.className = "status-dot status-ok";
      label.textContent = `backend: ${new URL(API_BASE).host}`;
    } else {
      dot.className = "status-dot status-err";
      label.textContent = `backend: HTTP ${r.status}`;
    }
  } catch (e) {
    dot.className = "status-dot status-err";
    label.textContent = `backend: unreachable`;
  }
}

// ---------- Examples ----------
$$(".example").forEach((b) => {
  b.addEventListener("click", () => {
    $("#query").value = b.dataset.q;
    $("#query").focus();
  });
});

// ---------- Tabs ----------
$$(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".tab-panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $(`.tab-panel[data-panel="${t.dataset.tab}"]`).classList.add("active");
  });
});

// ---------- Pipeline steps ----------
const STEP_KEYS = ["orchestrator", "us", "eu", "summarizer", "synthesis", "verification"];
function setStep(key, status) {
  const li = $(`#steps .step[data-step="${key}"]`);
  if (!li) return;
  li.classList.remove("pending", "active", "done", "error");
  li.classList.add(status);
}
function resetSteps() {
  STEP_KEYS.forEach((k) => setStep(k, "pending"));
}
function logLine(msg) {
  const t = new Date().toISOString().slice(11, 19);
  const log = $("#log");
  log.textContent += `[${t}] ${msg}\n`;
  log.scrollTop = log.scrollHeight;
}

// ---------- Form submit ----------
$("#research-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const query = $("#query").value.trim();
  if (!query) return;

  // Reset UI
  $("#run-btn").disabled = true;
  $(".btn-label").textContent = "Running…";
  $(".btn-spinner").hidden = false;
  $("#timer").hidden = false;
  $("#report").hidden = true;
  $("#error").hidden = true;
  $("#progress").hidden = false;
  $("#log").textContent = "";
  resetSteps();

  const t0 = performance.now();
  const tick = setInterval(() => {
    const s = ((performance.now() - t0) / 1000).toFixed(1);
    $("#timer").textContent = `${s}s`;
  }, 100);

  // Walk through steps optimistically as we wait for the single /research call
  // (the backend runs them in sequence, so we just animate the progress).
  const stepOrder = [...STEP_KEYS];
  let stepIdx = 0;
  const stepTimer = setInterval(() => {
    if (stepIdx > 0) setStep(stepOrder[stepIdx - 1], "done");
    if (stepIdx < stepOrder.length) {
      setStep(stepOrder[stepIdx], "active");
      logLine(`running: ${stepOrder[stepIdx]}`);
      stepIdx++;
    }
  }, 2500);

  try {
    logLine(`POST ${API_BASE}/research`);
    logLine(`query: ${query.slice(0, 80)}${query.length > 80 ? "…" : ""}`);

    const r = await fetch(`${API_BASE}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!r.ok) {
      const text = await r.text();
      throw new Error(`HTTP ${r.status}: ${text}`);
    }
    const ack = await r.json();
    logLine(`session_id: ${ack.session_id}`);

    logLine(`GET ${API_BASE}/report/${ack.session_id}`);
    const r2 = await fetch(`${API_BASE}/report/${ack.session_id}`);
    if (!r2.ok) {
      const text = await r2.text();
      throw new Error(`HTTP ${r2.status}: ${text}`);
    }
    const report = await r2.json();
    logLine(`report received: ${report.us_documents?.length ?? 0} US + ${report.eu_documents?.length ?? 0} EU docs`);

    // Mark all steps done
    STEP_KEYS.forEach((k) => setStep(k, "done"));
    logLine(`done in ${((performance.now() - t0) / 1000).toFixed(1)}s`);

    renderReport(report);
  } catch (e) {
    logLine(`ERROR: ${e.message}`);
    setStep(stepOrder[Math.max(0, stepIdx - 1)], "error");
    $("#error").hidden = false;
    $("#error-text").textContent = e.message + "\n\nMake sure:\n  1. The FastAPI backend is running (or deployed)\n  2. API_BASE points to the right URL\n  3. CORS is allowed on the backend";
  } finally {
    clearInterval(tick);
    clearInterval(stepTimer);
    $("#run-btn").disabled = false;
    $(".btn-label").textContent = "Run research";
    $(".btn-spinner").hidden = true;
  }
});

// ---------- Render ----------
function renderReport(report) {
  $("#report").hidden = false;
  $("#report-query").textContent = report.original_query || "";
  $("#session-chip").textContent = `session: ${report.session_id || "?"}`;
  $("#docs-chip").textContent = `docs: ${(report.us_documents?.length ?? 0) + (report.eu_documents?.length ?? 0)}`;
  const v = report.verification;
  if (v) {
    const chip = $("#verify-chip");
    chip.textContent = `verified: ${(v.citation_validation_rate * 100).toFixed(0)}%`;
    chip.className = `chip ${v.passed ? "ok" : "err"}`;
  }

  renderDocList($("#panel-us"), report.us_documents || [], "us");
  renderDocList($("#panel-eu"), report.eu_documents || [], "eu");
  renderSummary($("#panel-us-summary"), report.us_summary, "US");
  renderSummary($("#panel-eu-summary"), report.eu_summary, "EU");
  renderSynthesis($("#panel-synthesis"), report.synthesis);
  renderEuroVoc($("#panel-eurovoc"), report.synthesis, report.eu_documents || []);
  renderVerify($("#panel-verify"), v);
  $("#panel-raw").textContent = JSON.stringify(report, null, 2);
}

function renderDocList(host, docs, juris) {
  host.innerHTML = "";
  if (!docs.length) {
    host.appendChild(el("p", { class: "log" }, `No ${juris.toUpperCase()} documents retrieved.`));
    return;
  }
  for (const d of docs) {
    const evs = (d.eurovoc_descriptors || []).map((e) => el("span", { class: "ev" }, e));
    const card = el(
      "div",
      { class: `card ${juris === "eu" ? "eu" : ""}` },
      el("h4", {}, d.title || d.document_id),
      el(
        "div",
        { class: "meta" },
        el("span", { class: "tag" }, d.document_id),
        " · ",
        d.document_type || "?",
        d.court_or_body ? ` · ${d.court_or_body}` : "",
        d.date_decided ? ` · ${d.date_decided}` : "",
        d.celex ? ` · CELEX ${d.celex}` : ""
      ),
      d.url ? el("a", { href: d.url, target: "_blank", rel: "noopener" }, "open source ↗") : null,
      evs.length ? el("div", { class: "eurovoc" }, ...evs) : null
    );
    host.appendChild(card);
  }
}

function renderSummary(host, summary, jurisLabel) {
  host.innerHTML = "";
  if (!summary) {
    host.appendChild(el("p", { class: "log" }, `No ${jurisLabel} summary.`));
    return;
  }
  if (summary.summary_text) {
    host.appendChild(el("div", { class: "summary-text" }, summary.summary_text));
  }
  if (summary.eurovoc_descriptors?.length) {
    host.appendChild(
      el(
        "div",
        { class: "synth-section" },
        el("h4", {}, "EuroVoc descriptors"),
        el("div", { class: "eurovoc" }, ...summary.eurovoc_descriptors.map((e) => el("span", { class: "ev" }, e)))
      )
    );
  }
  const items = summary.items || [];
  if (items.length) {
    const wrap = el("div", { class: "summary-items" });
    for (const it of items) {
      const card = el("div", { class: "summary-item" });
      card.appendChild(el("h5", {}, it.title || it.document_id));
      if (it.holdings?.length) {
        card.appendChild(el("ul", {}, ...it.holdings.map((h) => el("li", {}, h))));
      }
      if (it.key_facts?.length) {
        card.appendChild(el("div", { class: "meta" }, "Key facts:"));
        card.appendChild(el("ul", {}, ...it.key_facts.map((h) => el("li", {}, h))));
      }
      if (it.legal_basis?.length) {
        card.appendChild(el("div", { class: "meta" }, "Legal basis:"));
        card.appendChild(el("ul", {}, ...it.legal_basis.map((h) => el("li", {}, h))));
      }
      wrap.appendChild(card);
    }
    host.appendChild(wrap);
  }
}

function renderSynthesis(host, syn) {
  host.innerHTML = "";
  if (!syn) {
    host.appendChild(el("p", { class: "log" }, "No synthesis output."));
    return;
  }
  if (syn.narrative) {
    host.appendChild(
      el(
        "div",
        { class: "synth-section" },
        el("h4", {}, "Comparative narrative"),
        el("div", { class: "synth-narrative" }, syn.narrative)
      )
    );
  }
  if (syn.alignment_matrix?.length) {
    const table = el("table", { class: "matrix" });
    table.appendChild(
      el(
        "thead",
        {},
        el("tr", {}, el("th", {}, "Principle"), el("th", {}, "US"), el("th", {}, "EU"), el("th", {}, "Status"))
      )
    );
    const tb = el("tbody");
    for (const row of syn.alignment_matrix) {
      const status = String(row.status || "").toLowerCase();
      tb.appendChild(
        el(
          "tr",
          {},
          el("td", {}, row.principle || ""),
          el("td", {}, row.us_position || ""),
          el("td", {}, row.eu_position || ""),
          el("td", {}, el("span", { class: `status-pill ${status}` }, row.status || ""))
        )
      );
    }
    table.appendChild(tb);
    host.appendChild(el("div", { class: "synth-section" }, el("h4", {}, "Principle alignment matrix"), table));
  }
  if (syn.divergences?.length) {
    const wrap = el("div", { class: "synth-section" });
    wrap.appendChild(el("h4", {}, "Divergences"));
    for (const d of syn.divergences) {
      wrap.appendChild(
        el(
          "div",
          { class: "summary-item" },
          el("h5", {}, d.topic || "(topic)"),
          el("div", { class: "meta" }, `US: ${d.us_view || ""}`),
          el("div", { class: "meta" }, `EU: ${d.eu_view || ""}`),
          d.implication ? el("div", { class: "meta" }, `Implication: ${d.implication}`) : null
        )
      );
    }
    host.appendChild(wrap);
  }
  if (syn.similar_precedents?.length) {
    const wrap = el("div", { class: "synth-section" });
    wrap.appendChild(el("h4", {}, "Similar precedents"));
    for (const p of syn.similar_precedents) {
      wrap.appendChild(
        el(
          "div",
          { class: "summary-item" },
          el("h5", {}, p.shared_principle || "(precedent)"),
          el("div", { class: "meta" }, `US: ${p.us_doc_id || ""} ↔ EU: ${p.eu_doc_id || ""}`)
        )
      );
    }
    host.appendChild(wrap);
  }
}

function renderEuroVoc(host, syn, euDocs) {
  host.innerHTML = "";
  let added = false;
  if (syn?.eurovoc_bridge?.length) {
    const wrap = el("div", { class: "synth-section" });
    wrap.appendChild(el("h4", {}, "EuroVoc ↔ US concept bridge"));
    for (const b of syn.eurovoc_bridge) {
      const conf = Math.round((b.confidence || 0) * 100);
      wrap.appendChild(
        el(
          "div",
          { class: "bridge-entry" },
          el(
            "div",
            { class: "pair" },
            el("span", { class: "eu" }, b.eurovoc_label || ""),
            el("span", { class: "arrow" }, "→"),
            el("span", { class: "us" }, b.us_concept || "")
          ),
          el(
            "div",
            { class: "meta" },
            "confidence ",
            el(
              "span",
              { class: "confidence-bar", title: `${conf}%` },
              el("span", { style: `width:${conf}%` })
            ),
            ` ${conf}%`
          ),
          b.rationale ? el("div", { class: "rationale" }, b.rationale) : null
        )
      );
    }
    host.appendChild(wrap);
    added = true;
  }
  if (syn?.eurovoc_hierarchy?.length) {
    const wrap = el("div", { class: "synth-section" });
    wrap.appendChild(el("h4", {}, "EuroVoc hierarchies"));
    for (const h of syn.eurovoc_hierarchy) {
      const tree = el("div", { class: "tree" });
      if (h.broader?.length) {
        tree.appendChild(el("div", {}, "broader: ", ...h.broader.map((b) => el("b", {}, b)), " "));
      }
      if (h.narrower?.length) {
        tree.appendChild(el("div", {}, "narrower: ", ...h.narrower.map((n) => el("b", {}, n)), " "));
      }
      wrap.appendChild(
        el(
          "div",
          { class: "hierarchy" },
          el("div", { class: "concept" }, h.concept || ""),
          h.uri ? el("code", { class: "uri" }, h.uri) : null,
          h.found === false ? el("div", { class: "meta" }, "(concept not found in live EuroVoc SPARQL — using static fallback)") : null,
          tree
        )
      );
    }
    host.appendChild(wrap);
    added = true;
  }
  if (euDocs.length) {
    const allEvs = new Set();
    for (const d of euDocs) for (const e of d.eurovoc_descriptors || []) allEvs.add(e);
    if (allEvs.size) {
      const wrap = el("div", { class: "synth-section" });
      wrap.appendChild(el("h4", {}, `EuroVoc descriptors across ${euDocs.length} EU documents`));
      wrap.appendChild(el("div", { class: "eurovoc" }, ...[...allEvs].map((e) => el("span", { class: "ev" }, e))));
      host.appendChild(wrap);
      added = true;
    }
  }
  if (!added) host.appendChild(el("p", { class: "log" }, "No EuroVoc data in this report."));
}

function renderVerify(host, v) {
  host.innerHTML = "";
  if (!v) {
    host.appendChild(el("p", { class: "log" }, "No verification report."));
    return;
  }
  const rate = (v.citation_validation_rate * 100).toFixed(0);
  host.appendChild(
    el(
      "div",
      { class: "verify-summary" },
      el("span", { class: `verify-badge ${v.passed ? "passed" : "failed"}` }, v.passed ? "PASSED" : "FLAGGED"),
      el("div", {}, `Citation validation rate: ${rate}%`)
    )
  );
  if (!v.flags?.length) {
    host.appendChild(el("p", { class: "log" }, "No flags raised."));
    return;
  }
  for (const f of v.flags) {
    host.appendChild(
      el(
        "div",
        { class: `flag severity-${f.severity || "info"}` },
        el("span", { class: "code" }, f.code || "FLAG"),
        f.document_id ? `[${f.document_id}] ` : "",
        f.message || ""
      )
    );
  }
}

// ---------- Boot ----------
checkHealth();
