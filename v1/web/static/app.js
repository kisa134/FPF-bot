// FPF Swarm — live team console: agents debate, you watch and inspect.

const AGENTS = {
  Architect:    { color: "#7c5cff", icon: "🏗", role: "generator — proposes moves" },
  Censor:       { color: "#ffb020", icon: "🔍", role: "auditor — reviews & vetoes" },
  Orchestrator: { color: "#34e3a4", icon: "📐", role: "recorder — commits to memory" },
};
const ACTION = {
  propose: "▸ proposes", revise: "↻ revises", veto: "⛔ vetoes", approve: "✓ approves",
  commit: "📌 committed", reject: "✕ rejected", escalate: "⚠ escalates", done: "✔ done",
};
const KIND_COLOR = {
  BoundedContext: "#7c5cff", Claim: "#22d3ee", Evidence: "#34e3a4",
  DecisionRecord: "#ffb020", Commitment: "#ff5fa2", PromiseContent: "#b56cff", Method: "#19d3da",
};

let currentRun = null, cy = null, filter = null;
const counts = { Architect: 0, Censor: 0, Orchestrator: 0 };
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// theme ----------------------------------------------------------------------
function theme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  $("theme").textContent = dark ? "🌙" : "☀️";
  localStorage.setItem("fpf-theme", dark ? "dark" : "light");
}
theme((localStorage.getItem("fpf-theme") || "dark") === "dark");
$("theme").onclick = () => theme(!document.documentElement.classList.contains("dark"));

// tabs -----------------------------------------------------------------------
function showTab(name) {
  ["team", "graph", "report"].forEach((t) => $(`tab-${t}`).classList.toggle("hidden", t !== name));
  document.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("border-indigo-500", on);
    b.classList.toggle("font-medium", on);
    b.classList.toggle("border-transparent", !on);
    b.classList.toggle("text-zinc-400", !on);
  });
  if (name === "graph") loadGraph();
  if (name === "report") report();
}
document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

// roster ---------------------------------------------------------------------
function renderRoster() {
  $("roster").innerHTML = Object.entries(AGENTS).map(([name, a]) => {
    const active = filter === name;
    return `<button data-agent="${name}" class="agent-chip shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs transition
      ${active ? "ring-2" : ""}"
      style="border-color:${a.color}55;${active ? `--tw-ring-color:${a.color}` : ""}">
      <span>${a.icon}</span><span style="color:${a.color}" class="font-medium">${name}</span>
      <span class="text-zinc-400">${counts[name]}</span></button>`;
  }).join("");
  document.querySelectorAll(".agent-chip").forEach((c) => {
    c.onclick = () => { filter = filter === c.dataset.agent ? null : c.dataset.agent; renderRoster(); applyFilter(); };
  });
}
function applyFilter() {
  document.querySelectorAll("#feed [data-agent]").forEach((el) => {
    el.classList.toggle("hidden", !!filter && el.dataset.agent !== filter);
  });
}

// feed -----------------------------------------------------------------------
function addEvent(ev) {
  counts[ev.agent] = (counts[ev.agent] || 0) + 1;
  renderRoster();
  const a = AGENTS[ev.agent] || { color: "#a1a1aa", icon: "•" };
  const bad = ev.ok === false;
  const accent = ev.action === "approve" || ev.action === "commit" ? "#34e3a4"
    : bad ? "#f43f5e" : a.color;
  const meta = [ev.kind, ev.object_id, ev.to ? `→ ${ev.to}` : null, ev.round ? `r${ev.round}` : null]
    .filter(Boolean).map((m) => `<span class="mono">${esc(m)}</span>`).join(" · ");
  const el = document.createElement("div");
  el.dataset.agent = ev.agent;
  el.className = "fade-in rounded-xl border bg-zinc-50/60 dark:bg-zinc-900/40 p-2.5";
  el.style.borderColor = accent + "44";
  el.style.borderLeft = `3px solid ${accent}`;
  el.innerHTML = `
    <div class="flex items-center gap-1.5 text-xs">
      <span>${a.icon}</span>
      <span class="font-semibold" style="color:${a.color}">${ev.agent}</span>
      <span class="text-zinc-500">${esc(ACTION[ev.action] || ev.action)}</span>
    </div>
    <div class="mt-1 text-[13px] leading-snug ${bad ? "text-rose-600 dark:text-rose-300" : ""}">${esc(ev.content)}</div>
    ${meta ? `<div class="mt-1 text-[10px] text-zinc-400">${meta}</div>` : ""}`;
  $("feed").appendChild(el);
  if (!filter || filter === ev.agent) {
    $("tab-team").scrollTop = $("tab-team").scrollHeight;
  } else el.classList.add("hidden");
}

// run ------------------------------------------------------------------------
async function run() {
  const task = $("task").value.trim();
  if (!task) return;
  $("empty")?.remove();
  $("feed").innerHTML = ""; counts.Architect = counts.Censor = counts.Orchestrator = 0; renderRoster();
  if (cy) { cy.destroy(); cy = null; }
  filter = null; showTab("team");
  $("run").disabled = true;
  $("status").innerHTML = `<span class="text-indigo-500">● team working…</span>`;

  const r = await fetch("/api/runs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, provider: $("provider").value, model: $("model")?.value || null }),
  });
  currentRun = (await r.json()).run_id;

  const es = new EventSource(`/api/runs/${currentRun}/stream`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "agent") addEvent(ev);
    else if (ev.type === "done") finish(ev);
    else if (ev.type === "error") $("status").innerHTML = `<span class="text-rose-500">error: ${esc(ev.message)}</span>`;
  };
  es.addEventListener("end", () => { es.close(); $("run").disabled = false; });
}

function finish(ev) {
  const head = ev.ok ? `<span class="text-emerald-500 font-medium">DONE</span>`
                     : `<span class="text-amber-500 font-medium">${ev.reason ? "ESCALATED" : "STOPPED"}</span>`;
  const by = ev.served_by ? ` · <span class="mono">${esc(ev.served_by)}</span>` : "";
  $("status").innerHTML = `${head} · ${ev.committed} committed${by}`;
  showAnswer(ev);
}

// Answer-first: surface the decision at the top once the team is done.
async function showAnswer(ev) {
  if (!currentRun) return;
  const g = await (await fetch(`/api/runs/${currentRun}/graph`)).json();
  const dnode = g.nodes.find((n) => n.kind === "DecisionRecord");
  const claims = g.nodes.filter((n) => n.kind === "Claim").length;
  const evid = g.nodes.filter((n) => n.kind === "Evidence").length;
  const card = document.createElement("div");
  card.className = "fade-in rounded-2xl border-2 p-4 mb-1";
  if (dnode) {
    const { payload: d } = await (await fetch(`/api/runs/${currentRun}/object/${encodeURIComponent(dnode.id)}`)).json();
    card.style.borderColor = "#34e3a4";
    card.innerHTML = `
      <div class="text-xs uppercase tracking-wide text-emerald-500 mb-1">Answer · ${esc(d.decision_subject || "")}</div>
      <div class="text-2xl font-bold" style="color:#34e3a4">${esc(d.chosen)}</div>
      <div class="mt-1 text-sm text-zinc-500">${esc(d.choice_rule || "")}</div>
      <div class="mt-2 text-[11px] text-zinc-400">based on ${claims} claims · ${evid} evidence · audited by the Censor${ev.served_by ? ` · ${esc(ev.served_by)}` : ""}</div>
      <div class="mt-1 text-[11px] text-zinc-400">↓ scroll to see exactly how the team reached this</div>`;
  } else {
    card.style.borderColor = ev.ok ? "#34e3a4" : "#ffb020";
    card.innerHTML = `<div class="text-xs uppercase tracking-wide text-zinc-400 mb-1">Result</div>
      <div class="text-sm">${ev.ok ? "Analysis complete — see the trace below." : "The team could not reach a confident answer" + (ev.reason ? ` (${esc(ev.reason)})` : "") + " — escalated for a human."}</div>`;
  }
  $("feed").prepend(card);
  $("tab-team").scrollTop = 0;
}

// graph ----------------------------------------------------------------------
async function loadGraph() {
  if (!currentRun || cy) return;
  const g = await (await fetch(`/api/runs/${currentRun}/graph`)).json();
  if (!g.nodes.length) return;
  const dark = document.documentElement.classList.contains("dark");
  cy = cytoscape({
    container: $("graph"),
    elements: [
      ...g.nodes.map((n) => ({ data: { id: n.id, label: n.id.length > 16 ? n.id.slice(0, 14) + "…" : n.id, kind: n.kind } })),
      ...g.edges.map((e) => ({ data: { source: e.source, target: e.target, label: e.rel } })),
    ],
    style: [
      { selector: "node", style: { "background-color": (n) => KIND_COLOR[n.data("kind")] || "#a1a1aa",
        "label": "data(label)", "color": dark ? "#e4e4e7" : "#27272a", "font-size": 10, "font-weight": 600,
        "text-valign": "bottom", "text-margin-y": 5, "width": 26, "height": 26,
        "border-width": 3, "border-color": dark ? "#0a0a0b" : "#fff" } },
      { selector: "edge", style: { "width": 1.5, "line-color": dark ? "#3f3f46" : "#d4d4d8",
        "target-arrow-color": dark ? "#3f3f46" : "#d4d4d8", "target-arrow-shape": "triangle",
        "curve-style": "bezier", "label": "data(label)", "font-size": 8, "color": dark ? "#71717a" : "#a1a1aa" } },
    ],
    layout: { name: "breadthfirst", directed: true, padding: 24, spacingFactor: 1.2 },
  });
  cy.on("tap", "node", (e) => inspect(e.target.id()));
  setTimeout(() => { cy.resize(); cy.fit(undefined, 30); }, 60);
}
async function inspect(oid) {
  const r = await fetch(`/api/runs/${currentRun}/object/${encodeURIComponent(oid)}`);
  if (!r.ok) return;
  const { kind, payload } = await r.json();
  $("inspector-title").innerHTML = `<span style="color:${KIND_COLOR[kind] || "#a1a1aa"}">${kind}</span> · ${esc(oid)}`;
  $("inspector-body").textContent = JSON.stringify(payload, null, 2);
  $("inspector").classList.remove("hidden");
}

// report ---------------------------------------------------------------------
async function report() {
  if (!currentRun) return;
  const g = await (await fetch(`/api/runs/${currentRun}/graph`)).json();
  const objs = {};
  await Promise.all(g.nodes.map(async (n) => {
    const r = await fetch(`/api/runs/${currentRun}/object/${encodeURIComponent(n.id)}`);
    if (r.ok) objs[n.id] = (await r.json()).payload;
  }));
  const byKind = (k) => g.nodes.filter((n) => n.kind === k).map((n) => objs[n.id]).filter(Boolean);
  const sec = (t, c, h) => `<div><div class="text-xs uppercase tracking-wide mb-1" style="color:${c}">${t}</div>${h}</div>`;
  const li = (s) => `<li class="ml-4 list-disc">${esc(s)}</li>`;
  let h = "";
  for (const c of byKind("BoundedContext"))
    h += sec("Context", KIND_COLOR.BoundedContext, `<div class="mono text-xs mb-1">${esc(c.id)}</div><ul>${(c.invariants || []).map(li).join("")}</ul>`);
  const cl = byKind("Claim"); if (cl.length) h += sec("Claims", KIND_COLOR.Claim, `<ul>${cl.map((c) => li(c.statement)).join("")}</ul>`);
  const ev = byKind("Evidence"); if (ev.length) h += sec("Evidence", KIND_COLOR.Evidence, `<ul>${ev.map((e) => li(`${e.target_claim_id}: ${e.claim_scope} [${e.kind}]`)).join("")}</ul>`);
  for (const d of byKind("DecisionRecord"))
    h += sec("Decision", KIND_COLOR.DecisionRecord, `<div><b>${esc(d.decision_subject)}</b></div><div class="text-zinc-500">options: ${esc((d.option_set||[]).join(", "))}</div><div class="text-zinc-500">rule: ${esc(d.choice_rule)}</div><div class="mt-1">→ <b style="color:${KIND_COLOR.DecisionRecord}">${esc(d.chosen)}</b></div>`);
  $("report-body").innerHTML = h || `<div class="text-zinc-400">No objects recorded yet — run a task first.</div>`;
}

// wiring ---------------------------------------------------------------------
renderRoster();
$("run").onclick = run;
$("task").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(); } });
