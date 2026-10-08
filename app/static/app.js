const $ = (s) => document.querySelector(s);
const log = $("#log");
const H0 = Math.log2(41); // uncertainty with nothing known: 41 equally likely conditions
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

let session = null;   // the whole conversation; the server is stateless and gets it back each turn
let trail = [];       // uncertainty after each answer: {label, bits, note}
let questionNo = 0;

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (p) => (p * 100).toFixed(p >= 0.995 || p < 0.01 ? 1 : 0) + "%";
const times = (llr) => { const x = Math.exp(llr); return "×" + (x >= 10 ? x.toFixed(1) : x.toFixed(2)); };

const ICON = {
  pulse: `<svg viewBox="0 0 32 32" class="size-4" aria-hidden="true"><path d="M4 17.5h5.5l3-8.5 4.5 14 3.2-8 1.6 2.5H28" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  alert: `<svg viewBox="0 0 24 24" class="size-5 shrink-0" aria-hidden="true"><path d="M12 3 2 20h20L12 3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.2v.3" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" class="size-5 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
  calendar: `<svg viewBox="0 0 24 24" class="size-5 shrink-0" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3.5 10h17M8 3v4M16 3v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
  check: `<svg viewBox="0 0 20 20" class="mt-0.5 size-4 shrink-0 text-scrub" aria-hidden="true"><path d="m4.5 10.5 3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

const EXAMPLES = [
  "I have a high fever and joint pain",
  "My head is pounding and I keep throwing up, no fever",
  "I have chest pain and I'm sweating a lot, feel short of breath",
];

// ------------------------------------------------------------------ conversation
function add(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html.trim();
  const el = wrap.firstElementChild;
  log.appendChild(el);
  log.scrollTo({ top: log.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  return el;
}

const botRow = (inner, extra = "") => `
  <div class="flex animate-rise gap-3 ${extra}">
    <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-scrub-soft text-scrub" aria-hidden="true">${ICON.pulse}</span>
    <div class="min-w-0 flex-1">${inner}</div>
  </div>`;

function welcome() {
  add(`
    <div id="welcome" class="mx-auto max-w-[580px] animate-rise py-4 sm:py-10">
      <p class="text-[13px] font-semibold text-scrub">History-taking, one question at a time</p>
      <h2 class="mt-2 font-display text-[clamp(30px,4.2vw,44px)] leading-[1.02] font-bold tracking-tight">What's bothering you today?</h2>
      <p class="mt-3 text-[15.5px] leading-relaxed text-ink-2">Describe it the way you'd tell a doctor. Anamnesis keeps all 41 conditions in mind, asks the yes/no question worth the most information, and stops once it's 90% sure, or tells you it can't be.</p>
      <p class="mt-7 text-[12.5px] font-semibold text-muted">Try one of these</p>
      <div class="mt-2 grid gap-2">
        ${EXAMPLES.map((e) => `<button type="button" data-example="${esc(e)}" class="group flex items-center justify-between gap-3 rounded-xl border border-rule bg-paper/50 px-4 py-3 text-left text-[14.5px] text-ink transition hover:border-scrub hover:bg-scrub-soft/60">
          <span>“${esc(e)}”</span><span class="text-scrub transition group-hover:translate-x-0.5" aria-hidden="true">→</span></button>`).join("")}
      </div>
    </div>`);
  log.querySelectorAll("[data-example]").forEach((b) => (b.onclick = () => send(b.dataset.example)));
}

function findingsChips(items) {
  return items.map(({ symptom, present }) => present
    ? `<li class="rounded-full bg-scrub-soft px-2.5 py-1 text-[13px] font-medium text-scrub-deep"><span class="font-mono" aria-label="has">+</span> ${esc(symptom)}</li>`
    : `<li class="rounded-full border border-rule px-2.5 py-1 text-[13px] text-muted"><span class="font-mono" aria-label="does not have">−</span> ${esc(symptom)}</li>`).join("");
}

function lrBar(s, against) {
  const x = Math.exp(s.llr);
  const w = Math.min(100, Math.max(6, (Math.abs(Math.log(x)) / Math.log(30)) * 100));
  return `<li>
    <div class="flex items-baseline justify-between gap-3 text-[13.5px]"><span class="text-ink">${s.state === "absent" ? "no " : ""}${esc(s.symptom)}</span><span class="font-mono text-[12.5px] text-ink-2">${times(s.llr)}</span></div>
    <div class="mt-1 h-[5px] rounded-full bg-paper"><i class="block h-full rounded-full ${against ? "bg-iodine/70" : "bg-scrub"}" style="width:${w}%"></i></div>
  </li>`;
}

function render(m) {
  switch (m.kind) {
    case "heard": {
      const items = m.text.replace(/^Noted:\s*/, "").replace(/\.$/, "").split(/;\s*/).filter(Boolean)
        .map((t) => (t.startsWith("no ") ? { symptom: t.slice(3), present: false } : { symptom: t, present: true }));
      return add(botRow(`<p class="text-[13px] font-semibold text-ink-2">Noted</p><ul class="mt-1.5 flex flex-wrap gap-1.5">${findingsChips(items)}</ul>`));
    }
    case "alert":
      return add(`<div role="alert" class="flex animate-rise gap-3 rounded-2xl border border-alarm/30 bg-alarm-soft p-4 text-alarm">
        ${ICON.alert}<div><p class="font-display text-[17px] font-bold">Warning sign</p><p class="mt-1 text-[14.5px] leading-relaxed text-ink">${esc(m.text)}</p>
        <a href="tel:108" class="mt-2.5 inline-flex rounded-full bg-alarm px-3.5 py-1.5 text-[13.5px] font-semibold text-card">Call 108</a></div></div>`);
    case "question": {
      questionNo += 1;
      const el = add(botRow(`
        <div class="rounded-2xl border border-scrub/25 bg-scrub-soft/45 p-4">
          <div class="flex items-center justify-between gap-3">
            <p class="text-[12.5px] font-semibold text-scrub">Question ${questionNo}</p>
            <p class="font-mono text-[12px] text-ink-2" title="How much this answer is expected to reduce the uncertainty">${m.bits.toFixed(2)} bits of information</p>
          </div>
          <p class="msg question mt-1.5 font-display text-[21px] leading-snug font-semibold">${esc(m.text)}</p>
          <div class="quick mt-3 flex gap-2">
            <button type="button" data-a="yes" class="rounded-xl bg-scrub px-5 py-2 text-[14.5px] font-semibold text-card transition hover:bg-scrub-deep">Yes</button>
            <button type="button" data-a="no" class="rounded-xl border border-ink/20 bg-card px-5 py-2 text-[14.5px] font-semibold text-ink transition hover:border-ink/40">No</button>
          </div>
        </div>`));
      el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => send(b.dataset.a)));
      return el;
    }
    case "result": {
      const why = m.support.map((s) => lrBar(s, false)).join("");
      const against = m.against.length
        ? `<p class="mt-4 text-[12.5px] font-semibold text-ink-2">Counts against it</p><ul class="mt-2 space-y-2.5">${m.against.map((s) => lrBar(s, true)).join("")}</ul>` : "";
      return add(`
        <article class="msg result animate-rise rounded-2xl border border-rule bg-card p-5 shadow-[0_18px_40px_-28px_rgb(16_35_28/0.45)] sm:p-6">
          <p class="text-[12.5px] font-semibold text-scrub">Impression</p>
          <div class="mt-1 flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
            <h3 class="font-display text-[clamp(30px,3.6vw,40px)] leading-none font-bold tracking-tight">${esc(m.disease)}</h3>
            <p class="font-mono text-[26px] leading-none font-medium text-scrub">${pct(m.p)}</p>
          </div>
          <p class="mt-2 text-[13.5px] text-ink-2">Next most likely: ${esc(m.rival)} · ${pct(m.rival_p)}</p>
          ${m.description ? `<p class="mt-4 text-[15px] leading-relaxed text-ink-2">${esc(m.description)}</p>` : ""}
          <div class="mt-5 grid gap-6 border-t border-rule pt-5 sm:grid-cols-2">
            <div>
              <h4 class="text-[13.5px] font-semibold">Why ${esc(m.disease)} over ${esc(m.rival)}</h4>
              <p class="mt-0.5 text-[12.5px] text-muted">How many times more likely each finding is with ${esc(m.disease)}</p>
              <ul class="mt-3 space-y-2.5">${why || `<li class="text-[13.5px] text-muted">No single finding stands out.</li>`}</ul>
              ${against}
            </div>
            <div>
              <h4 class="text-[13.5px] font-semibold">Suggested precautions</h4>
              <ul class="mt-3 space-y-2">${m.precautions.map((p) => `<li class="flex gap-2 text-[14px] text-ink-2">${ICON.check}<span>${esc(p[0].toUpperCase() + p.slice(1))}</span></li>`).join("")}</ul>
            </div>
          </div>
        </article>`);
    }
    case "info":
      return add(botRow(`<div class="rounded-2xl border border-rule bg-paper/50 p-4">
        <h3 class="font-display text-[22px] font-bold">${esc(m.disease)}</h3>
        <p class="mt-1.5 text-[14.5px] leading-relaxed text-ink-2">${esc(m.text)}</p>
        ${m.precautions.length ? `<h4 class="mt-3 text-[13px] font-semibold">Precautions</h4><ul class="mt-2 space-y-1.5">${m.precautions.map((p) => `<li class="flex gap-2 text-[14px] text-ink-2">${ICON.check}<span>${esc(p[0].toUpperCase() + p.slice(1))}</span></li>`).join("")}</ul>` : ""}
      </div>`));
    case "abstain":
      return add(`<div class="msg abstain flex animate-rise gap-3 rounded-2xl border border-iodine/30 bg-iodine-soft p-4 text-iodine">${ICON.clock}
        <div><p class="font-display text-[17px] font-bold">Not enough to name one condition</p><p class="mt-1 text-[14.5px] leading-relaxed text-ink">${esc(m.text)}</p></div></div>`);
    default:
      return add(botRow(`<p class="pt-0.5 text-[15px] leading-relaxed text-ink">${esc(m.text).replace(/\*(.+?)\*/g, "<em>$1</em>")}</p>`));
  }
}

// ------------------------------------------------------------------ case board
function drawTrail() {
  const svg = $("#trail");
  const W = 380, H = 150, L = 30, R = 14, T = 14, B = 26;
  const slots = Math.max(trail.length + 1, 6); // one spare slot keeps the value label inside the chart
  const x = (i) => L + (i * (W - L - R)) / (slots - 1);
  const y = (b) => T + (1 - b / 5.5) * (H - T - B);
  let g = "";
  for (const b of [0, 2, 4]) {
    g += `<line x1="${L}" x2="${W - R}" y1="${y(b)}" y2="${y(b)}" stroke="var(--color-rule)" stroke-width="1" ${b ? 'stroke-dasharray="2 4"' : ""}/>`;
    g += `<text x="${L - 8}" y="${y(b) + 3.5}" text-anchor="end" class="fill-muted font-mono" font-size="10">${b}</text>`;
  }
  if (trail.length) {
    let d = `M${x(0)},${y(trail[0].bits)}`;
    trail.slice(1).forEach((p, i) => { d += ` H${x(i + 1)} V${y(p.bits)}`; });
    const last = trail.length - 1;
    g += `<path d="${d} V${y(0)} H${x(0)} Z" fill="var(--color-scrub)" opacity="0.08"/>`;
    g += `<path d="${d}" fill="none" stroke="var(--color-scrub)" stroke-width="2" stroke-linejoin="round"/>`;
    trail.forEach((p, i) => {
      const lastOne = i === last;
      g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" class="${lastOne ? "fill-ink" : "fill-muted"} font-mono" font-size="10">${esc(p.label)}</text>`;
      g += `<circle cx="${x(i)}" cy="${y(p.bits)}" r="${lastOne ? 5.5 : 4}" fill="${lastOne ? "var(--color-scrub)" : "var(--color-card)"}" stroke="var(--color-scrub)" stroke-width="2"/>`;
      g += `<circle cx="${x(i)}" cy="${y(p.bits)}" r="14" fill="transparent" data-i="${i}" class="cursor-default"/>`;
    });
    // Value label sits to the right of the final point, clear of the vertical step into it.
    g += `<text x="${x(last) + 10}" y="${y(trail[last].bits) + 4}" class="fill-ink font-mono" font-size="11" font-weight="500">${trail[last].bits.toFixed(2)}</text>`;
  }
  svg.innerHTML = g;
  const tip = $("#tip");
  tip.classList.add("hidden");
  svg.querySelectorAll("[data-i]").forEach((c) => {
    const p = trail[+c.dataset.i];
    c.onpointerenter = () => {
      tip.innerHTML = `<b class="font-semibold">${esc(p.note)}</b><br><span class="font-mono">${p.bits.toFixed(2)} bits left</span>`;
      tip.classList.remove("hidden");
      const box = svg.getBoundingClientRect(), s = box.width / W;
      const cx = +c.getAttribute("cx") * s, cy = +c.getAttribute("cy") * s;
      tip.style.left = Math.min(Math.max(cx - tip.offsetWidth / 2, 0), box.width - tip.offsetWidth) + "px";
      tip.style.top = cy - tip.offsetHeight - 12 + "px";
    };
    c.onpointerleave = () => tip.classList.add("hidden");
  });
}

function updateTrail(r) {
  if (!r.differential.length) { trail = []; drawTrail(); return; }
  if (!trail.length) trail.push({ label: "start", bits: H0, note: "Nothing known yet: 41 equally likely conditions" });
  const answered = r.asked.filter((a) => a.answer !== null);
  const n = answered.length;
  const label = n ? `Q${n}` : "c/o";
  const q = answered[n - 1];
  const note = n ? `${q.symptom}? ${q.answer ? "yes" : "no"}`
    : "Complaint: " + r.evidence.filter((e) => e.present).map((e) => e.symptom).join(", ");
  const point = { label, bits: r.entropy, note };
  if (trail[trail.length - 1].label === label) trail[trail.length - 1] = point; else trail.push(point);
  drawTrail();
}

function renderDiff(list) {
  const ol = $("#diff");
  if (!list.length) {
    ol.innerHTML = `<li class="text-[13.5px] leading-snug text-muted">Probabilities appear once you describe a symptom.</li>`;
    return;
  }
  const before = new Map([...ol.querySelectorAll("li[data-k]")].map((li) =>
    [li.dataset.k, { top: li.getBoundingClientRect().top, w: li.querySelector("i").style.width }]));
  ol.innerHTML = list.map((d, i) => `
    <li data-k="${esc(d.disease)}">
      <div class="flex items-baseline justify-between gap-3">
        <span class="truncate text-[14.5px] ${i ? "text-ink-2" : "font-semibold text-ink"}">${esc(d.disease)}</span>
        <span class="font-mono text-[13px] ${i ? "text-ink-2" : "font-medium text-ink"}">${pct(d.p)}</span>
      </div>
      <div class="mt-1.5 h-[6px] overflow-hidden rounded-full bg-scrub-soft"><i class="block h-full rounded-full ${i ? "bg-scrub/45" : "bg-scrub"} transition-[width] duration-700 ease-out" style="width:${before.get(d.disease)?.w || "0%"}"></i></div>
    </li>`).join("");
  const rows = [...ol.querySelectorAll("li[data-k]")];
  rows.forEach((li) => {
    const prev = before.get(li.dataset.k);
    if (prev && !reduceMotion) {
      const dy = prev.top - li.getBoundingClientRect().top;
      if (dy) li.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 500, easing: "cubic-bezier(.2,.8,.2,1)" });
    }
  });
  requestAnimationFrame(() => rows.forEach((li, i) => { li.querySelector("i").style.width = Math.max(list[i].p * 100, 1.5) + "%"; }));
}

const TRIAGE = {
  emergency: { box: "border-alarm/30 bg-alarm-soft", ink: "text-alarm", icon: ICON.alert },
  prompt: { box: "border-iodine/30 bg-iodine-soft", ink: "text-iodine", icon: ICON.clock },
  routine: { box: "border-scrub/25 bg-scrub-soft", ink: "text-scrub", icon: ICON.calendar },
};

function panel(r) {
  const has = r.differential.length > 0;
  $("#bits").textContent = (has ? r.entropy : H0).toFixed(2);
  updateTrail(r);
  const first = trail[0], last = trail[trail.length - 1];
  $("#trail-caption").textContent = trail.length > 1
    ? `Down from ${first.bits.toFixed(2)} to ${last.bits.toFixed(2)} bits${!r.done ? " so far."
        : r.messages.some((m) => m.kind === "abstain") ? `. Still unclear after ${r.questions} questions, so it stopped.` : ". Confident enough to stop."}`
    : "With nothing known, all 41 conditions are equally likely. Each answer should bring this down.";
  renderDiff(r.differential);
  $("#mini").textContent = has ? `${r.differential[0].disease} ${pct(r.differential[0].p)} · ${r.entropy.toFixed(2)} bits` : "";

  const tc = $("#triage-card");
  if (r.triage) {
    const t = TRIAGE[r.triage.level];
    tc.className = `rounded-[22px] border p-5 ${t.box}`;
    tc.innerHTML = `<div class="flex gap-3 ${t.ink}">${t.icon}<div>
      <p class="text-[12.5px] font-semibold">Triage</p>
      <p class="font-display text-[19px] leading-tight font-bold">${esc(r.triage.label)}</p>
      <p class="mt-1 text-[13.5px] leading-snug text-ink-2">${esc(r.triage.why)}</p></div></div>`;
  } else tc.className = "hidden";

  $("#qcount").textContent = `${r.questions} question${r.questions === 1 ? "" : "s"}`;
  $("#evidence").innerHTML = r.evidence.length ? findingsChips(r.evidence)
    : `<li class="text-[13.5px] text-muted">Nothing recorded yet.</li>`;
  $("#asked").innerHTML = r.asked.map((a, i) => `
    <li class="flex items-baseline justify-between gap-3 text-[13.5px]">
      <span class="text-ink-2">${i + 1}. ${esc(a.symptom)}? <b class="font-semibold text-ink">${a.answer === null ? "…" : a.answer ? "yes" : "no"}</b></span>
      <span class="shrink-0 font-mono text-[12px] text-muted">${a.bits.toFixed(2)} bits</span>
    </li>`).join("");
}

const EMPTY = { differential: [], entropy: H0, evidence: [], asked: [], questions: 0, triage: null, done: false };

// ------------------------------------------------------------------ sending
async function send(text) {
  if (!text.trim()) return;
  $("#welcome")?.remove();
  log.querySelectorAll(".quick").forEach((q) => q.remove());
  add(`<div class="flex animate-rise justify-end"><p class="max-w-[80%] rounded-2xl rounded-br-md bg-scrub px-4 py-2.5 text-[15px] leading-relaxed text-card">${esc(text)}</p></div>`);
  const typing = add(botRow(`<p class="flex h-6 items-center gap-1" aria-label="Thinking">
    <i class="size-1.5 animate-pulse rounded-full bg-scrub"></i><i class="size-1.5 animate-pulse rounded-full bg-scrub [animation-delay:150ms]"></i><i class="size-1.5 animate-pulse rounded-full bg-scrub [animation-delay:300ms]"></i></p>`));
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session, text }) });
    if (!res.ok) throw new Error(res.status);
    const r = await res.json();
    typing.remove();
    session = r.session;
    if (/^(restart|start over|new consultation|reset)$/i.test(text.trim())) { questionNo = 0; trail = []; }
    r.messages.forEach(render);
    panel(r);
  } catch {
    typing.remove();
    add(botRow(`<p class="pt-0.5 text-[15px] text-alarm">Couldn't reach the server. Check your connection and send that again.</p>`));
  }
  $("#input").focus();
}

function restart() {
  session = null; trail = []; questionNo = 0;
  log.innerHTML = "";
  welcome();
  panel(EMPTY);
  $("#input").focus();
}

// Touch has no "leave", so any tap elsewhere or a scroll dismisses the chart tooltip.
const hideTip = (e) => { if (!e.target.closest?.("#trail")) $("#tip").classList.add("hidden"); };
document.addEventListener("pointerdown", hideTip);
document.addEventListener("scroll", () => $("#tip").classList.add("hidden"), true);

$("#form").onsubmit = (e) => { e.preventDefault(); const v = $("#input").value; $("#input").value = ""; send(v); };
$("#restart").onclick = restart;
restart();
window.send = send;
