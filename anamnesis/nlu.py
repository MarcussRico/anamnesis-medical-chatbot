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
    "joint_pain": ["joint pain", "joints hurt", "joints ache", "aching joints", "joint pains", "pain in joints", "pain in my joints"],
    "stomach_pain": ["stomach pain", "stomach ache", "stomachache", "tummy ache", "stomach hurts"],
    "acidity": ["acidity", "heartburn", "acid reflux", "burning in chest after eating", "burning in my chest", "burning in the chest", "chest burning", "burning sensation in chest"],
    "vomiting": ["vomiting", "vomit", "throwing up", "threw up", "puking", "vomited", "vomits"],
    "burning_micturition": ["burning while peeing", "burning urination", "pain while urinating", "burns when i pee", "burning sensation while urinating", "burning while urinating", "burning when urinating", "pain while peeing", "pain when urinating", "burning urine", "burning while passing urine", "pain while passing urine", "burning when passing urine", "burning when i pee", "burning sensation when i pee"],
    "fatigue": ["tired", "tiredness", "exhausted", "fatigue", "no energy", "worn out", "feel weak", "feeling weak", "general weakness"],
    "weight_gain": ["gaining weight", "weight gain", "put on weight"],
    "anxiety": ["anxious", "anxiety", "nervous", "panicky"],
    "mood_swings": ["mood swings", "moody", "irritable"],
    "weight_loss": ["losing weight", "weight loss", "lost weight"],
    "restlessness": ["restless", "can't sit still"],
    "lethargy": ["lethargic", "sluggish", "drowsy"],
    "cough": ["cough", "coughing"],
    "high_fever": ["high fever", "high temperature", "very hot", "burning up", "fever", "feverish", "temperature", "running a temperature"],
    "mild_fever": ["mild fever", "slight fever", "low grade fever", "low fever"],
    "breathlessness": ["breathless", "short of breath", "shortness of breath", "can't breathe", "hard to breathe", "difficulty breathing", "breathing problem", "breathing difficulty", "difficulty in breathing", "trouble breathing", "can't breathe properly"],
    "sweating": ["sweating", "sweaty", "sweats"],
    "dehydration": ["dehydrated", "very thirsty"],
    "indigestion": ["indigestion", "upset stomach", "bloating after food"],
    "headache": ["headache", "head hurts", "head is pounding", "head pain", "migraine"],
    "yellowish_skin": ["yellow skin", "skin turned yellow", "jaundice", "skin is yellow", "skin has turned yellow"],
    "dark_urine": ["dark urine", "dark pee", "brown urine", "urine is dark", "dark yellow urine"],
    "nausea": ["nausea", "nauseous", "feel sick", "queasy", "want to vomit"],
    "loss_of_appetite": ["no appetite", "not hungry", "loss of appetite", "don't feel like eating"],
    "pain_behind_the_eyes": ["pain behind my eyes", "eyes hurt from behind", "pain behind eyes"],
    "back_pain": ["back pain", "back hurts", "backache", "lower back pain", "pain in my back", "pain in my lower back", "lower back"],
    "constipation": ["constipated", "constipation", "can't pass stool"],
    "abdominal_pain": ["abdominal pain", "belly pain", "pain in abdomen", "cramps"],
    "diarrhoea": ["diarrhea", "diarrhoea", "loose motion", "loose motions", "loose stools", "watery stool", "motions", "the runs"],
    "yellowing_of_eyes": ["yellow eyes", "eyes turned yellow", "yellowing of eyes"],
    "swelling_of_stomach": ["swollen stomach", "stomach swelling", "bloated belly", "belly is swollen", "swollen belly", "stomach is swollen", "swollen tummy"],
    "blurred_and_distorted_vision": ["blurry vision", "blurred vision", "can't see clearly"],
    "phlegm": ["phlegm", "mucus", "sputum"],
    "throat_irritation": ["throat irritation", "scratchy throat", "itchy throat", "sore throat", "throat hurts", "throat pain", "painful throat", "throat is sore", "throat"],
    "redness_of_eyes": ["red eyes", "redness in eyes", "bloodshot eyes"],
    "sinus_pressure": ["sinus pressure", "sinus pain", "blocked sinus"],
    "runny_nose": ["runny nose", "running nose", "nose is running", "have a cold", "caught a cold", "got a cold"],
    "congestion": ["congestion", "stuffy nose", "blocked nose", "nasal congestion"],
    "chest_pain": ["chest pain", "chest hurts", "pain in my chest", "tight chest", "pain in chest", "chest tightness"],
    "weakness_in_limbs": ["weak arms", "weak legs", "weakness in limbs", "legs feel weak", "arms feel weak", "legs are weak", "arms are weak"],
    "fast_heart_rate": ["fast heartbeat", "heart racing", "palpitations", "racing heart", "heart is beating fast", "heart beating fast", "heartbeat is fast", "heart is racing"],
    "neck_pain": ["neck pain", "neck hurts", "stiff neck"],
    "dizziness": ["dizzy", "dizziness", "lightheaded", "light headed", "head spinning", "giddy", "giddiness"],
    "cramps": ["muscle cramps", "leg cramps"],
    "obesity": ["overweight", "obese"],
    "puffy_face_and_eyes": ["puffy face", "puffy eyes", "swollen face"],
    "excessive_hunger": ["always hungry", "excessive hunger", "very hungry"],
    "knee_pain": ["knee pain", "knees hurt", "knee hurts"],
    "hip_joint_pain": ["hip pain", "hip hurts"],
    "muscle_weakness": ["weak muscles", "muscle weakness"],
    "stiff_neck": ["stiff neck", "can't turn my neck"],
    "swelling_joints": ["swollen joints", "joint swelling", "joints are swollen", "joint is swollen", "swollen knees"],
    "loss_of_balance": ["losing balance", "loss of balance", "unsteady"],
    "unsteadiness": ["unsteady on my feet", "wobbly"],
    "loss_of_smell": ["can't smell", "loss of smell", "lost my sense of smell"],
    "bladder_discomfort": ["bladder discomfort", "bladder pain"],
    "continuous_feel_of_urine": ["always need to pee", "frequent urge to urinate", "keep needing to pee"],
    "polyuria": ["peeing a lot", "frequent urination", "urinate often"],
    "depression": ["depressed", "feeling low", "sad all the time"],
    "irritability": ["irritable", "easily annoyed"],
    "muscle_pain": ["body ache", "body pain", "muscle pain", "muscles ache", "aching muscles", "body is aching", "body aches", "body aching"],
    "red_spots_over_body": ["red spots", "red dots on body", "spots all over"],
    "belly_pain": ["belly ache"],
    "watering_from_eyes": ["watery eyes", "eyes watering", "teary eyes"],
    "increased_appetite": ["eating more than usual", "increased appetite"],
    "lack_of_concentration": ["can't concentrate", "can't focus", "poor concentration"],
    "visual_disturbances": ["seeing spots", "visual disturbance", "flashing lights"],
    "blood_in_sputum": ["coughing blood", "blood in sputum", "blood in phlegm", "coughing up blood", "blood in my cough", "blood when i cough"],
    "palpitations": ["palpitations", "heart pounding"],
    "painful_walking": ["painful to walk", "hurts to walk"],
    "pus_filled_pimples": ["pimples with pus", "pus filled pimples", "pimples", "pimple", "zits"],
    "blackheads": ["blackheads"],
    "skin_peeling": ["peeling skin", "skin peeling"],
    "blister": ["blister", "blisters"],
    "slurred_speech": ["slurred speech", "slurring words", "can't speak properly"],
    "weakness_of_one_body_side": ["one side of my body is weak", "weakness on one side", "half body weakness"],
    "altered_sensorium": ["confused", "confusion", "disoriented"],
    "coma": ["unconscious", "unresponsive"],
    "stomach_bleeding": ["vomiting blood", "blood in vomit"],
    "bloody_stool": ["blood in stool", "bloody stool", "blood in poop", "bleeding when passing stool", "bleeding while passing stool", "blood when passing stool", "bleeding from anus", "rectal bleeding"],
    "pain_during_bowel_movements": ["pain while passing stool", "painful bowel movements"],
    "irritation_in_anus": ["itchy anus", "anal itching"],
    "cold_hands_and_feets": ["cold hands", "cold feet", "cold hands and feet"],
    "sunken_eyes": ["sunken eyes"],
    "family_history": ["runs in my family", "family history"],
    "receiving_blood_transfusion": ["blood transfusion"],
    "toxic_look_(typhos)": ["looks very ill", "toxic look"],
    "movement_stiffness": ["stiffness", "stiff joints", "joints are stiff"],
    "swollen_legs": ["legs are swollen", "swollen ankles", "swollen feet", "swelling in my legs", "leg swelling"],
    "swollen_blood_vessels": ["swollen veins", "bulging veins"],
    "prominent_veins_on_calf": ["veins on my legs", "veins on my calf", "varicose"],
    "passage_of_gases": ["gas", "gas problem", "gastric trouble", "flatulence"],
}

NEGATION = re.compile(
    r"\b(no|not|never|without|none|denies|deny|dont|don't|do not|didn't|didnt|"
    r"haven't|havent|have not|hasn't|isn't|aren't|free of|absence of)\b"
)
# Trimmed from both ends of a fuzzy window, so "my arms" or "all over" can't match on filler alone.
FILLER = {"my", "is", "are", "am", "i", "im", "all", "the", "a", "an", "very", "so", "and", "with", "on", "in",
          "of", "to", "at", "it", "its", "has", "have", "been", "over", "i've", "ive", "i'm", "feeling", "feel",
          "having", "while", "when", "time", "today", "twice", "there's", "really", "some", "bit", "little"}
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
        self.multiword = np.array([" " in p for p in phrases])

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
            windows, starts, single = [], [], []
            for n in (1, 2, 3, 4):
                for k in range(len(words) - n + 1):
                    ws = words[k:k + n]
                    while ws and ws[0] in FILLER:
                        ws = ws[1:]
                    while ws and ws[-1] in FILLER:
                        ws = ws[:-1]
                    w = " ".join(ws)
                    if len(w) >= 5 and not NEGATION.fullmatch(w) and w not in windows:
                        windows.append(w)
                        starts.append(consumed.find(w))
                        single.append(len(ws) == 1)
            if windows:
                sims = (self.vec.transform(windows) @ self.P.T).toarray()
                # One word may only fuzzy-match a one-word phrase (a misspelling), never part of a
                # longer one: otherwise "burning" matches "burning up" and "swollen" "swollen face".
                sims[np.array(single)[:, None] & self.multiword[None, :]] = 0
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
