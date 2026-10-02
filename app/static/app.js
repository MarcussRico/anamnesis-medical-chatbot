const $ = (s) => document.querySelector(s);
const log = $("#log");
let sid = null;

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (p) => (p * 100).toFixed(p >= 0.995 || p < 0.01 ? 1 : 0) + "%";

function bubble(cls, html) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = html;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}

function render(m) {
  switch (m.kind) {
    case "heard": return bubble("bot heard", esc(m.text));
    case "alert": return bubble("bot alert", `<strong>Warning sign</strong>${esc(m.text)}`);
    case "question": {
      const b = bubble("bot question", `${esc(m.text)}<span class="bits">chosen because it is worth ${m.bits.toFixed(2)} bits of expected information</span>
        <div class="quick"><button data-a="yes">Yes</button><button data-a="no">No</button></div>`);
      b.querySelectorAll("button").forEach((x) => x.onclick = () => send(x.dataset.a));
      return b;
    }
    case "result": {
      const sup = m.support.map((s) => `<li>${s.state === "absent" ? "no " : ""}${esc(s.symptom)} <span class="llr">×${Math.exp(s.llr).toFixed(1)}</span></li>`).join("");
      const ag = m.against.length ? m.against.map((s) => `<li>${s.state === "absent" ? "no " : ""}${esc(s.symptom)} <span class="llr">×${Math.exp(s.llr).toFixed(2)}</span></li>`).join("") : "<li>Nothing reported counts against it.</li>";
      return bubble("bot result", `<div class="eyebrow">Most consistent with</div>
        <h3>${esc(m.disease)} <span class="p">${pct(m.p)}</span></h3>
        <div class="eyebrow">Next most likely: ${esc(m.rival)} (${pct(m.rival_p)})</div>
        <p>${esc(m.description)}</p>
        <div class="why"><div><h4>What points to it (vs. ${esc(m.rival)})</h4><ul>${sup}</ul></div>
        <div><h4>What argues against it</h4><ul>${ag}</ul></div></div>
        <div class="care"><h4>Suggested precautions</h4><ul>${m.precautions.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>`);
    }
    case "info":
      return bubble("bot info", `<h3>${esc(m.disease)}</h3><p>${esc(m.text)}</p><h4>Precautions</h4><ul>${m.precautions.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`);
    case "abstain": return bubble("bot abstain", esc(m.text));
    default: return bubble("bot", esc(m.text).replace(/\*(.+?)\*/g, "<em>$1</em>"));
  }
}

function panel(r) {
  const diff = $("#diff");
  diff.innerHTML = r.differential.length
    ? r.differential.map((d) => `<li><div class="row"><span>${esc(d.disease)}</span><span>${pct(d.p)}</span></div><div class="bar"><i style="width:${Math.max(d.p * 100, 1)}%"></i></div></li>`).join("")
    : `<li class="empty">Probabilities appear once you describe a symptom.</li>`;
  $("#entropy").textContent = r.differential.length ? `uncertainty ${r.entropy.toFixed(2)} bits` : "—";
  $("#qcount").textContent = `${r.questions} question${r.questions === 1 ? "" : "s"}`;
  $("#evidence").innerHTML = r.evidence.length
    ? r.evidence.map((e) => `<li class="chip ${e.present ? "yes" : "no"}">${esc(e.symptom)}</li>`).join("")
    : `<li class="empty">Nothing recorded yet.</li>`;
  $("#asked").innerHTML = r.asked.map((a) => `<li>${esc(a.symptom)}? <b>${a.answer === null ? "…" : a.answer ? "yes" : "no"}</b> <span class="mono">${a.bits.toFixed(2)} bits</span></li>`).join("");
  const tc = $("#triage-card");
  if (r.triage) {
    tc.hidden = false;
    $("#triage").innerHTML = `<div class="triage ${r.triage.level}"><b>${esc(r.triage.label)}</b><span>${esc(r.triage.why)}</span></div>`;
  } else tc.hidden = true;
}

async function send(text) {
  if (!text.trim()) return;
  log.querySelectorAll(".quick").forEach((q) => q.remove());
  bubble("user", esc(text));
  const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid, text }) });
  const r = await res.json();
  sid = r.session_id;
  r.messages.forEach(render);
  panel(r);
}

$("#form").onsubmit = (e) => { e.preventDefault(); const v = $("#input").value; $("#input").value = ""; send(v); };
$("#restart").onclick = () => { log.innerHTML = ""; send("restart"); };
bubble("bot", "Hello. Tell me what you're feeling, in your own words. I'll ask a few yes/no questions, each one picked to narrow things down as fast as possible.");
window.send = send;
