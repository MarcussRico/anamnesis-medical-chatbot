"""Free-text symptom extraction with negation scope.

Patients say "my head is pounding" and "no temperature", not `headache=1,
high_fever=0`. Extraction runs in two passes per clause:
  1. lexicon — exact match on canonical names plus a hand-built lay-term list;
  2. fuzzy  — character n-gram TF-IDF similarity between word windows of the
     clause and every phrase, for spellings and phrasings the lexicon misses.
A negation cue ("no", "not", "without", "don't have" ...) flips everything
after it in the same clause to ABSENT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import knowledge as kb

LAY_TERMS: dict[str, list[str]] = {
    "itching": ["itchy", "itch", "itchiness", "scratching"],
    "skin_rash": ["rash", "rashes", "red spots on skin", "skin rash"],
    "continuous_sneezing": ["sneezing", "sneeze", "keep sneezing"],
    "shivering": ["shivering", "shaking", "trembling"],
    "chills": ["chills", "feeling cold", "cold shivers"],
    "joint_pain": ["joint pain", "joints hurt", "joints ache", "aching joints"],
    "stomach_pain": ["stomach pain", "stomach ache", "stomachache", "tummy ache", "stomach hurts"],
    "acidity": ["acidity", "heartburn", "acid reflux", "burning in chest after eating"],
    "vomiting": ["vomiting", "vomit", "throwing up", "threw up", "puking"],
    "burning_micturition": ["burning while peeing", "burning urination", "pain while urinating", "burns when i pee"],
    "fatigue": ["tired", "tiredness", "exhausted", "fatigue", "no energy", "worn out"],
    "weight_gain": ["gaining weight", "weight gain", "put on weight"],
    "anxiety": ["anxious", "anxiety", "nervous", "panicky"],
    "mood_swings": ["mood swings", "moody", "irritable"],
    "weight_loss": ["losing weight", "weight loss", "lost weight"],
    "restlessness": ["restless", "can't sit still"],
    "lethargy": ["lethargic", "sluggish", "drowsy"],
    "cough": ["cough", "coughing"],
    "high_fever": ["high fever", "high temperature", "very hot", "burning up", "fever"],
    "mild_fever": ["mild fever", "slight fever", "low grade fever", "low fever"],
    "breathlessness": ["breathless", "short of breath", "shortness of breath", "can't breathe", "hard to breathe", "difficulty breathing"],
    "sweating": ["sweating", "sweaty", "sweats"],
    "dehydration": ["dehydrated", "very thirsty"],
    "indigestion": ["indigestion", "upset stomach", "bloating after food"],
    "headache": ["headache", "head hurts", "head is pounding", "head pain", "migraine"],
    "yellowish_skin": ["yellow skin", "skin turned yellow", "jaundice"],
    "dark_urine": ["dark urine", "dark pee", "brown urine"],
    "nausea": ["nausea", "nauseous", "feel sick", "queasy", "want to vomit"],
    "loss_of_appetite": ["no appetite", "not hungry", "loss of appetite", "don't feel like eating"],
    "pain_behind_the_eyes": ["pain behind my eyes", "eyes hurt from behind", "pain behind eyes"],
    "back_pain": ["back pain", "back hurts", "backache"],
    "constipation": ["constipated", "constipation", "can't pass stool"],
    "abdominal_pain": ["abdominal pain", "belly pain", "pain in abdomen", "cramps"],
    "diarrhoea": ["diarrhea", "diarrhoea", "loose motion", "loose motions", "loose stools", "watery stool"],
    "yellowing_of_eyes": ["yellow eyes", "eyes turned yellow", "yellowing of eyes"],
    "swelling_of_stomach": ["swollen stomach", "stomach swelling", "bloated belly"],
    "blurred_and_distorted_vision": ["blurry vision", "blurred vision", "can't see clearly"],
    "phlegm": ["phlegm", "mucus", "sputum"],
    "throat_irritation": ["throat irritation", "scratchy throat", "itchy throat"],
    "redness_of_eyes": ["red eyes", "redness in eyes", "bloodshot eyes"],
    "sinus_pressure": ["sinus pressure", "sinus pain", "blocked sinus"],
    "runny_nose": ["runny nose", "running nose", "nose is running"],
    "congestion": ["congestion", "stuffy nose", "blocked nose", "nasal congestion"],
    "chest_pain": ["chest pain", "chest hurts", "pain in my chest", "tight chest"],
    "weakness_in_limbs": ["weak arms", "weak legs", "weakness in limbs"],
    "fast_heart_rate": ["fast heartbeat", "heart racing", "palpitations", "racing heart"],
    "neck_pain": ["neck pain", "neck hurts", "stiff neck"],
    "dizziness": ["dizzy", "dizziness", "lightheaded", "light headed", "head spinning"],
    "cramps": ["muscle cramps", "leg cramps"],
    "obesity": ["overweight", "obese"],
    "puffy_face_and_eyes": ["puffy face", "puffy eyes", "swollen face"],
    "excessive_hunger": ["always hungry", "excessive hunger", "very hungry"],
    "knee_pain": ["knee pain", "knees hurt", "knee hurts"],
    "hip_joint_pain": ["hip pain", "hip hurts"],
    "muscle_weakness": ["weak muscles", "muscle weakness"],
    "stiff_neck": ["stiff neck", "can't turn my neck"],
    "swelling_joints": ["swollen joints", "joint swelling"],
    "loss_of_balance": ["losing balance", "loss of balance", "unsteady"],
    "unsteadiness": ["unsteady on my feet", "wobbly"],
    "loss_of_smell": ["can't smell", "loss of smell", "lost my sense of smell"],
    "bladder_discomfort": ["bladder discomfort", "bladder pain"],
    "continuous_feel_of_urine": ["always need to pee", "frequent urge to urinate", "keep needing to pee"],
    "polyuria": ["peeing a lot", "frequent urination", "urinate often"],
    "depression": ["depressed", "feeling low", "sad all the time"],
    "irritability": ["irritable", "easily annoyed"],
    "muscle_pain": ["body ache", "body pain", "muscle pain", "muscles ache", "aching muscles"],
    "red_spots_over_body": ["red spots", "red dots on body", "spots all over"],
    "belly_pain": ["belly ache"],
    "watering_from_eyes": ["watery eyes", "eyes watering", "teary eyes"],
    "increased_appetite": ["eating more than usual", "increased appetite"],
    "lack_of_concentration": ["can't concentrate", "can't focus", "poor concentration"],
    "visual_disturbances": ["seeing spots", "visual disturbance", "flashing lights"],
    "blood_in_sputum": ["coughing blood", "blood in sputum", "blood in phlegm"],
    "palpitations": ["palpitations", "heart pounding"],
    "painful_walking": ["painful to walk", "hurts to walk"],
    "pus_filled_pimples": ["pimples with pus", "pus filled pimples"],
    "blackheads": ["blackheads"],
    "skin_peeling": ["peeling skin", "skin peeling"],
    "blister": ["blister", "blisters"],
    "slurred_speech": ["slurred speech", "slurring words", "can't speak properly"],
    "weakness_of_one_body_side": ["one side of my body is weak", "weakness on one side", "half body weakness"],
    "altered_sensorium": ["confused", "confusion", "disoriented"],
    "coma": ["unconscious", "unresponsive"],
    "stomach_bleeding": ["vomiting blood", "blood in vomit"],
    "bloody_stool": ["blood in stool", "bloody stool", "blood in poop"],
    "pain_during_bowel_movements": ["pain while passing stool", "painful bowel movements"],
    "irritation_in_anus": ["itchy anus", "anal itching"],
    "cold_hands_and_feets": ["cold hands", "cold feet", "cold hands and feet"],
    "sunken_eyes": ["sunken eyes"],
    "family_history": ["runs in my family", "family history"],
    "receiving_blood_transfusion": ["blood transfusion"],
    "toxic_look_(typhos)": ["looks very ill", "toxic look"],
}

NEGATION = re.compile(
    r"\b(no|not|never|without|none|denies|deny|dont|don't|do not|didn't|didnt|"
    r"haven't|havent|have not|hasn't|isn't|aren't|free of|absence of)\b"
)
CLAUSE_SPLIT = re.compile(r"[,.;!?]|\bbut\b|\bthough\b|\balthough\b|\bhowever\b")


@dataclass
class Mention:
    symptom: str          # canonical column name
    present: bool
    matched: str          # the phrase found in the text
    method: str           # "lexicon" or "fuzzy"


def _norm(t: str) -> str:
    t = t.lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(t.split())


class SymptomExtractor:
    def __init__(self, symptoms: list[str], fuzzy_threshold: float = 0.72, use_fuzzy: bool = True):
        self.symptoms = symptoms
        self.use_fuzzy = use_fuzzy
        self.threshold = fuzzy_threshold
        phrases, owners = [], []
        for s in symptoms:
            for p in {_norm(kb.clean_symptom(s))} | {_norm(x) for x in LAY_TERMS.get(s, [])}:
                if p:
                    phrases.append(p)
                    owners.append(s)
        self.phrases, self.owners = phrases, owners
        # longest phrases first so "high fever" wins over "fever"
        self.order = sorted(range(len(phrases)), key=lambda i: -len(phrases[i]))
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(phrases)
        self.P = self.vec.transform(phrases)

    def _clause(self, clause: str) -> list[Mention]:
        neg = NEGATION.search(clause)
        found: dict[str, Mention] = {}
        consumed = clause
        for i in self.order:
            p = self.phrases[i]
            m = re.search(rf"\b{re.escape(p)}\b", consumed)
            if not m:
                continue
            present = not (neg and neg.start() <= m.start())
            if self.owners[i] not in found:
                found[self.owners[i]] = Mention(self.owners[i], present, p, "lexicon")
            consumed = consumed[: m.start()] + " " * len(p) + consumed[m.end():]
        if self.use_fuzzy:
            words = consumed.split()
            windows, starts = [], []
            for n in (1, 2, 3, 4):
                for k in range(len(words) - n + 1):
                    w = " ".join(words[k:k + n])
                    if len(w) >= 5 and not NEGATION.fullmatch(w):
                        windows.append(w)
                        starts.append(consumed.find(w))
            if windows:
                sims = (self.vec.transform(windows) @ self.P.T).toarray()
                for wi, row in enumerate(sims):
                    j = int(row.argmax())
                    if row[j] >= self.threshold and self.owners[j] not in found:
                        present = not (neg and neg.start() <= starts[wi])
                        found[self.owners[j]] = Mention(self.owners[j], present, windows[wi], "fuzzy")
        return list(found.values())

    def extract(self, text: str) -> list[Mention]:
        out: dict[str, Mention] = {}
        for clause in CLAUSE_SPLIT.split(_norm_keep_punct(text)):
            for m in self._clause(_norm(clause)):
                out[m.symptom] = m
        return list(out.values())


def _norm_keep_punct(t: str) -> str:
    return t.lower().replace("’", "'")


def yes_no(text: str) -> bool | None:
    t = _norm(text)
    if re.match(r"^(y|yes|yeah|yep|yup|sure|i do|i have|correct|right|true|ok|a little|slightly|sometimes)\b", t):
        return True
    if re.match(r"^(n|no|nope|nah|not really|i don't|i dont|never|none|false|not at all)\b", t):
        return False
    return None
