// FPF Studio — chat-driven reasoning console with live trace + graph + report.

const KIND_COLOR = {
  BoundedContext: "#7c5cff", // violet
  Claim: "#22d3ee",          // cyan
  Evidence: "#34e3a4",       // green
  DecisionRecord: "#ffb020", // amber
  Commitment: "#ff5fa2",     // pink
  PromiseContent: "#b56cff", // purple
  Method: "#19d3da",         // teal
};
const KIND_LABEL = {
  BoundedContext: "Context", Claim: "Claim", Evidence: "Evidence",
  DecisionRecord: "Decision", Commitment: "Commitment",
  PromiseContent: "Promise", Method: "Method", finish: "Finish",
};

let cy = null;
let currentRun = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// ---- theme -----------------------------------------------------------------
function applyTheme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  $("theme").textContent = dark ? "🌙" : "☀️";
  localStorage.setItem("fpf-theme", dark ? "dark" : "light");
}
applyTheme((localStorage.getItem("fpf-theme") || "dark") === "dark");
$("theme").addEventListener("click", () =>
  applyTheme(!document.documentElement.classList.contains("dark")));

// ---- run -------------------------------------------------------------------
function badge(kind, ok, rolled) {
  const c = KIND_COLOR[kind] || "#a1a1aa";
  const icon = ok ? "✓" : (rolled ? "↩" : "✕");
  const ring = ok ? "" : "ring-1 ring-rose-500/60";
  return `<span class="px-2 py-0.5 rounded-md text-[11px] font-semibold ${ring}"
    style="background:${c}22;color:${c}">${icon} ${KIND_LABEL[kind] || kind || "move"}</span>`;
}

function addCard(ev) {
  const tl = $("timeline");
  const card = document.createElement("div");
  const bad = ev.ok
    ? "border-zinc-200 dark:border-zinc-800"
    : "border-rose-400/50 bg-rose-50 dark:border-rose-700/50 dark:bg-rose-950/20";
  card.className = `fade-in rounded-xl border ${bad} bg-zinc-50/60 dark:bg-zinc-900/40 p-3`;
  card.innerHTML = `
    <div class="flex items-center justify-between gap-2">
      ${badge(ev.kind, ev.ok, ev.rolled_back)}
      <span class="mono text-[10px] text-zinc-400">${ev.phase}</span>
    </div>
    ${ev.object_id ? `<div class="mt-1 mono text-xs text-zinc-500">${esc(ev.object_id)}</div>` : ""}
    ${ev.rationale ? `<div class="mt-1.5 text-[13px] leading-snug">${esc(ev.rationale)}</div>` : ""}
    ${ev.reason ? `<div class="mt-1.5 text-[12px] text-rose-600 dark:text-rose-300">⛔ ${esc(ev.reason)}</div>` : ""}`;
  tl.appendChild(card);
  tl.scrollTop = tl.scrollHeight;
}

async function run() {
  const task = $("task").value.trim();
  if (!task) return;
  $("empty")?.remove();
  $("timeline").innerHTML = "";
  $("inspector").classList.add("hidden");
  $("report-btn").disabled = true;
  if (cy) { cy.destroy(); cy = null; }
  $("run").disabled = true;
  $("status").innerHTML = `<span class="text-indigo-500">● thinking…</span>`;

  const r = await fetch("/api/runs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, provider: $("provider").value, model: $("model").value.trim() || null }),
  });
  currentRun = (await r.json()).run_id;

  const es = new EventSource(`/api/runs/${currentRun}/stream`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "step") addCard(ev);
    else if (ev.type === "done") finish(ev);
    else if (ev.type === "error")
      $("status").innerHTML = `<span class="text-rose-500">error: ${esc(ev.message)}</span>`;
  };
  es.addEventListener("end", () => { es.close(); $("run").disabled = false; });
}

function finish(ev) {
  const head = ev.ok ? `<span class="text-emerald-500 font-medium">DONE</span>`
                     : `<span class="text-amber-500 font-medium">INCOMPLETE</span>`;
  const by = ev.served_by ? ` · <span class="mono">${esc(ev.served_by)}</span>` : "";
  $("status").innerHTML = `${head} — ${ev.steps} moves, phase ${ev.final_phase}${by}`
    + (ev.reason ? ` · <span class="text-rose-400">${esc(ev.reason)}</span>` : "");
  $("report-btn").disabled = false;
  loadGraph();
}

// ---- graph -----------------------------------------------------------------
async function loadGraph() {
  const g = await (await fetch(`/api/runs/${currentRun}/graph`)).json();
  if (!g.nodes.length) return;
  const elements = [
    ...g.nodes.map((n) => ({ data: { id: n.id, label: short(n.id), kind: n.kind } })),
    ...g.edges.map((e) => ({ data: { source: e.source, target: e.target, label: e.rel } })),
  ];
  const dark = document.documentElement.classList.contains("dark");
  cy = cytoscape({
    container: $("graph"), elements,
    style: [
      { selector: "node", style: {
        "background-color": (n) => KIND_COLOR[n.data("kind")] || "#a1a1aa",
        "label": "data(label)", "color": dark ? "#e4e4e7" : "#27272a", "font-size": 10,
        "font-weight": 600, "text-valign": "bottom", "text-margin-y": 5,
        "width": 28, "height": 28, "border-width": 3,
        "border-color": dark ? "#0a0a0b" : "#ffffff" } },
      { selector: "edge", style: {
        "width": 1.5, "line-color": dark ? "#3f3f46" : "#d4d4d8",
        "target-arrow-color": dark ? "#3f3f46" : "#d4d4d8", "target-arrow-shape": "triangle",
        "curve-style": "bezier", "label": "data(label)", "font-size": 8,
        "color": dark ? "#71717a" : "#a1a1aa" } },
    ],
    layout: { name: "breadthfirst", directed: true, padding: 28, spacingFactor: 1.25 },
  });
  cy.on("tap", "node", (e) => inspect(e.target.id()));
  setTimeout(() => { cy.resize(); cy.fit(undefined, 36); }, 60);
}
const short = (id) => id.length > 16 ? id.slice(0, 14) + "…" : id;

async function inspect(oid) {
  const r = await fetch(`/api/runs/${currentRun}/object/${encodeURIComponent(oid)}`);
  if (!r.ok) return;
  const { kind, payload } = await r.json();
  $("inspector-title").innerHTML = `<span style="color:${KIND_COLOR[kind] || "#a1a1aa"}">${KIND_LABEL[kind] || kind}</span> · ${esc(oid)}`;
  $("inspector-body").textContent = JSON.stringify(payload, null, 2);
  $("inspector").classList.remove("hidden");
}

// ---- report ----------------------------------------------------------------
async function report() {
  const g = await (await fetch(`/api/runs/${currentRun}/graph`)).json();
  const objs = {};
  await Promise.all(g.nodes.map(async (n) => {
    const r = await fetch(`/api/runs/${currentRun}/object/${encodeURIComponent(n.id)}`);
    if (r.ok) objs[n.id] = (await r.json()).payload;
  }));
  const byKind = (k) => g.nodes.filter((n) => n.kind === k).map((n) => objs[n.id]).filter(Boolean);

  const sec = (title, color, html) =>
    `<div><div class="text-xs uppercase tracking-wide mb-1" style="color:${color}">${title}</div>${html}</div>`;
  const li = (s) => `<li class="ml-4 list-disc">${esc(s)}</li>`;

  let h = "";
  for (const c of byKind("BoundedContext"))
    h += sec("Context", KIND_COLOR.BoundedContext,
      `<div class="mono text-xs mb-1">${esc(c.id)}</div><ul>${(c.invariants || []).map(li).join("")}</ul>`);
  const claims = byKind("Claim");
  if (claims.length) h += sec("Claims", KIND_COLOR.Claim, `<ul>${claims.map((c) => li(c.statement)).join("")}</ul>`);
  const ev = byKind("Evidence");
  if (ev.length) h += sec("Evidence", KIND_COLOR.Evidence,
    `<ul>${ev.map((e) => li(`${e.target_claim_id}: ${e.claim_scope} [${e.kind}]`)).join("")}</ul>`);
  for (const d of byKind("DecisionRecord"))
    h += sec("Decision", KIND_COLOR.DecisionRecord,
      `<div><b>${esc(d.decision_subject)}</b></div>
       <div class="text-zinc-500">options: ${esc((d.option_set || []).join(", "))}</div>
       <div class="text-zinc-500">rule: ${esc(d.choice_rule)}</div>
       <div class="mt-1">→ <b style="color:${KIND_COLOR.DecisionRecord}">${esc(d.chosen)}</b></div>`);
  $("report-body").innerHTML = h || `<div class="text-zinc-400">No objects recorded.</div>`;
  $("report").classList.remove("hidden");
}

// ---- wiring ----------------------------------------------------------------
$("run").addEventListener("click", run);
$("report-btn").addEventListener("click", report);
$("task").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(); }
});
