# ANAMNESIS — a medical chatbot that asks the right next question

A Project-Based Learning (Machine Learning) project, Department of Computer Science and Engineering,
Chennai Institute of Technology, 2026–2027 — **Sai Charan A** (2104251040844) and **Ashfaq Muhammed A** (2104251040096).

Patients start a consultation with two or three symptoms, not a 132-field form. ANAMNESIS keeps a Bayesian
posterior over 41 diseases that conditions only on symptoms whose state is known, and at every turn asks the
yes/no question with the highest **expected information gain**. It stops at 90% confidence, abstains below 50%,
raises an emergency alert for warning-sign symptoms, and explains every result with per-symptom likelihood ratios.
No generative language model is used anywhere, so it cannot invent a condition or a treatment.

> Not a diagnostic device. In an emergency call 108.

## Key results (1,230 simulated consultations on held-out symptom profiles, 3% answer noise)

| | Top-1 | Top-3 | Questions |
|---|---|---|---|
| Random question | 79.4% | 94.8% | 7.9 |
| Most-common symptom first | 90.4% | 98.5% | 5.2 |
| **Expected information gain (ours)** | **96.3%** | **98.7%** | **4.0** |

**Leakage audit.** The public dataset's 4,920 training rows contain only 304 unique records, and all 41 official
test rows also appear in training, which is why projects on it report 100% accuracy. Every result here uses a
profile-grouped split instead. With only two volunteered symptoms, logistic regression reaches 61.8% on unseen profiles.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.server:app --port 8765        # open http://localhost:8765
```

## Reproduce every number and figure

```bash
python -m experiments.evaluate            # writes results/results.json and figures/*.png (~90 s)
python scripts/diagrams.py                # architecture + loop diagrams
python -m playwright install chromium && python scripts/screenshots.py   # needs the server running
```

## Layout

```
anamnesis/   knowledge.py  model.py (evidence model + EIG)  nlu.py (lay-language + negation)  engine.py (dialogue)
app/         server.py (FastAPI) + static/ (chat UI with live differential panel)
experiments/ evaluate.py (all experiments)  nlu_testset.py (50 labelled utterances)
data/raw/    Kaggle disease–symptom data + description / precaution / severity tables
report/      build_report.py (PBL report generator)    poster/  poster.html
```

Data: Kaggle "Disease Prediction Using Machine Learning" (kaushil268) and the description/precaution/severity
tables from github.com/itachi9604/healthcare-chatbot.
