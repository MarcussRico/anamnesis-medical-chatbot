"""Dialogue manager: one conversation = one evidence vector.

Every sentence the bot says is assembled from the knowledge base and the
model's own numbers. There is no generative language model anywhere in the
loop, so nothing it says can be invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from . import knowledge as kb
from .model import ABSENT, PRESENT, UNKNOWN, EvidenceModel, build_default
from .nlu import SymptomExtractor, yes_no

CONFIDENT = 0.90        # stop questioning once the top disease reaches this
ABSTAIN_BELOW = 0.50    # below this at the end, refuse to name a single disease
MAX_QUESTIONS = 8
MIN_EIG_BITS = 0.02

RED_FLAGS = {
    "chest_pain", "breathlessness", "slurred_speech", "weakness_of_one_body_side",
    "altered_sensorium", "coma", "blood_in_sputum", "stomach_bleeding",
    "bloody_stool", "acute_liver_failure",
}
EMERGENCY_DISEASES = {"Heart attack", "Paralysis (brain hemorrhage)"}
PROMPT_DISEASES = {
    "Pneumonia", "Tuberculosis", "Dengue", "Malaria", "Typhoid", "AIDS", "Jaundice",
    "Hypoglycemia", "Alcoholic hepatitis", "hepatitis A", "Hepatitis B", "Hepatitis C",
    "Hepatitis D", "Hepatitis E", "Chronic cholestasis",
}

_MODEL: EvidenceModel | None = None
_NLU: SymptomExtractor | None = None


def resources() -> tuple[EvidenceModel, SymptomExtractor]:
    global _MODEL, _NLU
    if _MODEL is None:
        _MODEL = build_default()
        _NLU = SymptomExtractor(_MODEL.symptoms)
    return _MODEL, _NLU


def _cap(t: str) -> str:
    return t[:1].upper() + t[1:]


def nice(symptom: str) -> str:
    return kb.clean_symptom(symptom)


def triage_for(disease: str | None, state: np.ndarray, symptoms: list[str]) -> dict:
    flags = [nice(s) for s, v in zip(symptoms, state) if v == PRESENT and s in RED_FLAGS]
    if flags or disease in EMERGENCY_DISEASES:
        return {"level": "emergency", "label": "Seek emergency care now",
                "why": "Reported warning sign: " + ", ".join(flags) if flags else
                "The leading condition needs immediate medical attention."}
    if disease in PROMPT_DISEASES:
        return {"level": "prompt", "label": "See a doctor within 24 hours",
                "why": "The leading condition usually needs tests and prescribed treatment."}
    return {"level": "routine", "label": "Book a routine consultation",
            "why": "Nothing reported so far is a warning sign; monitor and see a doctor if it worsens."}


@dataclass
class Session:
    state: np.ndarray = field(default_factory=lambda: np.full(len(resources()[0].symptoms), UNKNOWN))
    pending: int | None = None
    asked: list[dict] = field(default_factory=list)
    done: bool = False
    transcript: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    def _snapshot(self, model: EvidenceModel) -> dict:
        post = model.posterior(self.state)
        order = np.argsort(-post)[:5]
        evidence = [{"symptom": nice(s), "present": bool(v == PRESENT)}
                    for s, v in zip(model.symptoms, self.state) if v != UNKNOWN]
        top = model.diseases[order[0]] if (self.state == PRESENT).any() else None
        return {
            "differential": [{"disease": kb.display(model.diseases[i]), "p": round(float(post[i]), 4)}
                             for i in order] if top else [],
            "evidence": evidence,
            "questions": len(self.asked),
            "asked": self.asked,
            "entropy": round(float(-(post * np.log2(np.clip(post, 1e-12, 1))).sum()), 3),
            "triage": triage_for(top, self.state, model.symptoms) if top else None,
            "done": self.done,
        }

    def _say(self, model, messages: list[dict]) -> dict:
        for m in messages:
            self.transcript.append({"role": "bot", **m})
        return {"messages": messages, **self._snapshot(model)}

    # ------------------------------------------------------------------ turns
    def handle(self, text: str) -> dict:
        model, nlu = resources()
        text = (text or "").strip()
        self.transcript.append({"role": "user", "text": text})
        low = text.lower()

        if re.search(r"\b(restart|start over|new consultation|reset)\b", low):
            self.__init__()
            return self._say(model, [{"kind": "text", "text": "Fresh start. Tell me what you're feeling, in your own words."}])

        info = re.match(r"^(what is|what's|tell me about|explain|define)\s+(.+?)\??$", low)
        if info:
            return self._say(model, [self._info(info.group(2))])

        mentions = nlu.extract(text)
        answered = None
        if self.pending is not None:
            answered = yes_no(text)
            if answered is None and not mentions:
                q = nice(model.symptoms[self.pending])
                return self._say(model, [{"kind": "text", "text": f"Sorry, I didn't catch that. Do you have {q}? A yes or no is enough."}])
            if answered is not None:
                self.state[self.pending] = PRESENT if answered else ABSENT
                self.asked[-1]["answer"] = answered
            self.pending = None

        new = []
        for m in mentions:
            j = model.symptoms.index(m.symptom)
            self.state[j] = PRESENT if m.present else ABSENT
            new.append(m)

        if not (self.state == PRESENT).any():
            if new:
                return self._say(model, [{"kind": "text", "text": "Noted. What symptoms *do* you have? Describe them as you would to a doctor."}])
            return self._say(model, [{"kind": "text", "text":
                "I couldn't pick out a symptom there. Try something like \"I've had a fever and headache since yesterday, no cough\"."}])

        out = []
        if new:
            heard = "; ".join(("" if m.present else "no ") + nice(m.symptom) for m in new)
            out.append({"kind": "heard", "text": f"Noted: {heard}."})

        sev = kb.severity()
        flags = [nice(s) for s, v in sorted(zip(model.symptoms, self.state), key=lambda t: -sev.get(t[0], 0))
                 if v == PRESENT and s in RED_FLAGS]
        if flags and not any(m.get("kind") == "alert" for m in self.transcript if m["role"] == "bot"):
            out.append({"kind": "alert", "text":
                f"{flags[0].capitalize()} can be a sign of something serious. If it is severe, sudden or getting worse, "
                "call 108 or go to the nearest emergency department now. I'll keep going, but don't wait on me."})

        post = model.posterior(self.state)
        n_present = int((self.state == PRESENT).sum())
        if post.max() >= CONFIDENT and n_present >= 2 or len(self.asked) >= MAX_QUESTIONS:
            return self._say(model, out + self._conclude(model, post))

        eig = model.expected_information_gain(post, self.state)
        j = int(np.argmax(eig))
        if eig[j] < MIN_EIG_BITS:
            return self._say(model, out + self._conclude(model, post))
        self.pending = j
        self.asked.append({"symptom": nice(model.symptoms[j]), "bits": round(float(eig[j]), 3), "answer": None})
        out.append({"kind": "question", "symptom": nice(model.symptoms[j]), "bits": round(float(eig[j]), 3),
                    "text": f"Do you also have {nice(model.symptoms[j])}?"})
        return self._say(model, out)

    def _conclude(self, model: EvidenceModel, post: np.ndarray) -> list[dict]:
        self.done = True
        order = np.argsort(-post)
        top, rival = int(order[0]), int(order[1])
        name = model.diseases[top]
        if post[top] < ABSTAIN_BELOW:
            cands = ", ".join(f"{kb.display(model.diseases[i])} ({post[i]:.0%})" for i in order[:3])
            return [{"kind": "abstain", "text":
                     "I can't narrow this down with enough confidence to name one condition. "
                     f"The closest matches are {cands}. Please see a doctor and mention the symptoms listed on the right."}]
        why = model.explain(self.state, top, rival)
        support = [w for w in why if w[2] > 0.5][:4]
        against = [w for w in why if w[2] < -0.5][:2]
        return [{
            "kind": "result",
            "disease": kb.display(name),
            "p": round(float(post[top]), 4),
            "rival": kb.display(model.diseases[rival]),
            "rival_p": round(float(post[rival]), 4),
            "support": [{"symptom": nice(s), "state": k, "llr": round(l, 2)} for s, k, l in support],
            "against": [{"symptom": nice(s), "state": k, "llr": round(l, 2)} for s, k, l in against],
            "description": _cap(kb.lookup(kb.descriptions(), name) or ""),
            "precautions": kb.lookup(kb.precautions(), name) or [],
            "triage": triage_for(name, self.state, model.symptoms),
            "text": f"Your answers are most consistent with {kb.display(name)}.",
        }]

    def _info(self, query: str) -> dict:
        model, _ = resources()
        q = re.sub(r"[^a-z ]", "", query.lower()).strip()
        for d in model.diseases:
            names = {d.lower(), kb.display(d).lower()}
            if any(q == n or q in n or n in q for n in names):
                return {"kind": "info", "disease": kb.display(d),
                        "text": kb.lookup(kb.descriptions(), d) or "",
                        "precautions": kb.lookup(kb.precautions(), d) or []}
        return {"kind": "text", "text": f"\"{query}\" isn't one of the 41 conditions in my knowledge base, so I won't guess about it."}
