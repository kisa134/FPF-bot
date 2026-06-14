// FPF Studio frontend — live timeline + interactive reasoning graph.

const KIND_COLOR = {
  BoundedContext: "#818cf8",  // indigo
  Claim: "#38bdf8",           // sky
  Evidence: "#34d399",        // emerald
  DecisionRecord: "#fbbf24",  // amber
  Commitment: "#e879f9",      // fuchsia
  PromiseContent: "#a78bfa",  // violet
  Method: "#2dd4bf",          // teal
};

let cy = null;
let currentRun = null;

const $ = (id) => document.getElementById(id);

function badge(kind, ok, rolledBack) {
  const color = KIND_COLOR[kind] || "#94a3b8";
  const label = kind || "finish";
  const ring = ok ? "" : "ring-1 ring-rose-500/60";
  const icon = ok ? "✓" : (rolledBack ? "↩" : "✕");
  return `<span class="px-2 py-0.5 rounded-md text-[11px] font-semibold ${ring}"
    style="background:${color}22;color:${color}">${icon} ${label}</span>`;
}

function addCard(ev) {
  const tl = $("timeline");
  const card = document.createElement("div");
  const border = ev.ok ? "border-slate-800" : "border-rose-700/60 bg-rose-950/20";
  card.className = `fade-in rounded-xl border ${border} bg-slate-900/50 p-3`;
  card.innerHTML = `
    <div class="flex items-center justify-between gap-2">
      ${badge(ev.kind, ev.ok, ev.rolled_back)}
      <span class="mono text-[11px] text-slate-500">${ev.phase}</span>
    </div>
    <div class="mt-1.5 mono text-xs text-slate-300">${ev.object_id || ""}</div>
    ${ev.reason ? `<div class="mt-1 text-[11px] text-rose-300">⛔ ${escapeHtml(ev.reason)}</div>` : ""}
    ${ev.sha ? `<div class="mt-1 mono text-[10px] text-slate-600">${ev.sha}</div>` : ""}`;
  tl.appendChild(card);
  tl.scrollTop = tl.scrollHeight;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function run() {
  const task = $("task").value.trim();
  if (!task) { $("status").textContent = "Enter a task first."; return; }
  $("timeline").innerHTML = "";
  $("inspector").classList.add("hidden");
  if (cy) { cy.destroy(); cy = null; }
  $("run").disabled = true;
  $("status").innerHTML = `<span class="text-indigo-300">● running…</span>`;

  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      provider: $("provider").value,
      model: $("model").value.trim() || null,
    }),
  });
  const { run_id } = await res.json();
  currentRun = run_id;

  const es = new EventSource(`/api/runs/${run_id}/stream`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "step") addCard(ev);
    else if (ev.type === "done") finish(ev, run_id);
    else if (ev.type === "error") {
      $("status").innerHTML = `<span class="text-rose-400">error: ${escapeHtml(ev.message)}</span>`;
    }
  };
  es.addEventListener("end", () => { es.close(); $("run").disabled = false; });
}

function finish(ev, runId) {
  const ok = ev.ok ? `<span class="text-emerald-400">DONE</span>` : `<span class="text-amber-400">INCOMPLETE</span>`;
  const by = ev.served_by ? ` · <span class="mono text-slate-300">${ev.served_by}</span>` : "";
  $("status").innerHTML = `${ok} — ${ev.steps} moves, phase ${ev.final_phase}${by}`
    + (ev.reason ? `<div class="text-rose-300 mt-1">${escapeHtml(ev.reason)}</div>` : "");
  loadGraph(runId);
}

async function loadGraph(runId) {
  const g = await (await fetch(`/api/runs/${runId}/graph`)).json();
  const elements = [
    ...g.nodes.map((n) => ({ data: { id: n.id, label: shortLabel(n.id), kind: n.kind } })),
    ...g.edges.map((e) => ({ data: { source: e.source, target: e.target, label: e.rel } })),
  ];
  cy = cytoscape({
    container: $("graph"),
    elements,
    style: [
      { selector: "node", style: {
        "background-color": (n) => KIND_COLOR[n.data("kind")] || "#94a3b8",
        "label": "data(label)", "color": "#e2e8f0", "font-size": 10,
        "text-valign": "bottom", "text-margin-y": 4, "width": 26, "height": 26,
        "border-width": 2, "border-color": "#0f172a" } },
      { selector: "edge", style: {
        "width": 1.5, "line-color": "#475569", "target-arrow-color": "#475569",
        "target-arrow-shape": "triangle", "curve-style": "bezier",
        "label": "data(label)", "font-size": 8, "color": "#64748b" } },
    ],
    layout: { name: "breadthfirst", directed: true, padding: 30, spacingFactor: 1.3 },
  });
  cy.on("tap", "node", (e) => inspect(runId, e.target.id()));
}

function shortLabel(id) { return id.length > 18 ? id.slice(0, 16) + "…" : id; }

async function inspect(runId, oid) {
  const r = await fetch(`/api/runs/${runId}/object/${encodeURIComponent(oid)}`);
  if (!r.ok) return;
  const { kind, payload } = await r.json();
  $("inspector-title").innerHTML = `<span style="color:${KIND_COLOR[kind] || "#94a3b8"}">${kind}</span> · ${oid}`;
  $("inspector-body").textContent = JSON.stringify(payload, null, 2);
  $("inspector").classList.remove("hidden");
}

$("run").addEventListener("click", run);
$("task").addEventListener("keydown", (e) => { if (e.metaKey && e.key === "Enter") run(); });
