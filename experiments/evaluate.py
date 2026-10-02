"""Runs every experiment reported in the PBL report and writes results/ + figures/.

    python -m experiments.evaluate

Deterministic: every random draw comes from a seeded Generator.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import BernoulliNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from anamnesis import knowledge as kb
from anamnesis.model import ABSENT, PRESENT, UNKNOWN, EvidenceModel
from anamnesis.nlu import SymptomExtractor
from experiments.nlu_testset import CASES

ROOT = Path(__file__).resolve().parent.parent
RES, FIG = ROOT / "results", ROOT / "figures"
RES.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)

SEEDS = [0, 1, 2, 3, 4]
INK, ACCENT, MUTED, PAPER = "#1f2a36", "#a33b2b", "#8a8f98", "#ffffff"
plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": INK, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "figure.dpi": 200})

COLS = kb.symptom_columns()
FULL = kb.load_training()
TEST = kb.load_testing()
PROF = kb.unique_profiles()


def classifiers():
    return {
        "Logistic Regression": LogisticRegression(max_iter=2000),
        "Random Forest": RandomForestClassifier(n_estimators=200, random_state=0),
        "SVM (RBF)": SVC(),
        "Bernoulli Naive Bayes": BernoulliNB(),
        "Decision Tree": DecisionTreeClassifier(random_state=0),
        "k-NN (k=5)": KNeighborsClassifier(5),
    }


def group_split(seed: int, per_disease: int = 2):
    """Hold out whole unique symptom profiles, so no test row has a copy in training."""
    rng = np.random.default_rng(seed)
    test_idx = []
    for d, g in PROF.groupby("prognosis"):
        k = min(per_disease, len(g) - 1)
        test_idx += list(rng.choice(g.index.to_numpy(), size=k, replace=False))
    test = PROF.loc[sorted(test_idx)]
    train = PROF.drop(index=test_idx)
    return train, test


# --------------------------------------------------------------------- E1 leakage
def e1_leakage():
    X, y = FULL[COLS].to_numpy(), FULL["prognosis"].to_numpy()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    train_keys = {r.tobytes() for r in Xtr.astype(np.int8)}
    overlap = float(np.mean([r.tobytes() in train_keys for r in Xte.astype(np.int8)]))
    official_overlap = float(np.mean([r.tobytes() in {q.tobytes() for q in X.astype(np.int8)}
                                      for r in TEST[COLS].to_numpy().astype(np.int8)]))
    rows = {}
    for name, clf in classifiers().items():
        official = clf.fit(X, y).score(TEST[COLS].to_numpy(), TEST["prognosis"].to_numpy())
        rnd = clf.fit(Xtr, ytr).score(Xte, yte)
        honest = []
        for s in SEEDS:
            tr, te = group_split(s)
            honest.append(clf.fit(tr[COLS].to_numpy(), tr["prognosis"]).score(te[COLS].to_numpy(), te["prognosis"]))
        rows[name] = {"official_test": official, "random_split": rnd,
                      "group_split_mean": float(np.mean(honest)), "group_split_std": float(np.std(honest))}
    return {"rows": rows, "n_rows": len(FULL), "n_unique": len(PROF), "n_diseases": FULL.prognosis.nunique(),
            "n_symptoms": len(COLS), "random_split_test_rows_seen_in_train": overlap,
            "official_test_rows_seen_in_train": official_overlap, "n_official_test": len(TEST)}


# ------------------------------------------------------- simulated patients
def sample_reports(profile_row: np.ndarray, k: int, rng) -> np.ndarray:
    on = np.where(profile_row == 1)[0]
    return rng.choice(on, size=min(k, len(on)), replace=False)


def e2_partial():
    """Patients volunteer only k symptoms. Static classifiers read every
    unmentioned symptom as 'absent'; the evidence model treats it as unknown."""
    ks = [1, 2, 3, 4]
    names = ["Logistic Regression", "Random Forest", "SVM (RBF)", "Bernoulli Naive Bayes",
             "Masked-augmented LR", "Evidence model (ours)"]
    acc = {n: {k: [] for k in ks} for n in names}
    for s in SEEDS:
        rng = np.random.default_rng(100 + s)
        tr, te = group_split(s)
        Xtr, ytr = tr[COLS].to_numpy(), tr["prognosis"].to_numpy()
        base = {n: c.fit(Xtr, ytr) for n, c in classifiers().items() if n in names}
        # masked augmentation: train on random subsets of each profile
        aug_X, aug_y = [Xtr], [ytr]
        for _ in range(20):
            keep = rng.random(Xtr.shape) < rng.uniform(0.2, 0.9, size=(len(Xtr), 1))
            aug_X.append(Xtr * keep)
            aug_y.append(ytr)
        Xa, ya = np.vstack(aug_X), np.concatenate(aug_y)
        nz = Xa.sum(1) > 0
        mlr = LogisticRegression(max_iter=3000).fit(Xa[nz], ya[nz])
        em = EvidenceModel().fit(Xtr, ytr, COLS)
        for _, row in te.iterrows():
            prof = row[COLS].to_numpy().astype(int)
            for k in ks:
                for _rep in range(3):
                    idx = sample_reports(prof, k, rng)
                    x = np.zeros(len(COLS))
                    x[idx] = 1
                    for n, c in base.items():
                        acc[n][k].append(c.predict(x[None])[0] == row.prognosis)
                    acc["Masked-augmented LR"][k].append(mlr.predict(x[None])[0] == row.prognosis)
                    st = np.full(len(COLS), UNKNOWN)
                    st[idx] = PRESENT
                    acc["Evidence model (ours)"][k].append(em.diseases[int(np.argmax(em.posterior(st)))] == row.prognosis)
    return {n: {k: float(np.mean(v)) for k, v in d.items()} for n, d in acc.items()}


def run_dialogue(em: EvidenceModel, prof: np.ndarray, initial, policy: str, budget: int,
                 rng, noise: float, early_stop: float | None):
    st = np.full(len(COLS), UNKNOWN)
    st[initial] = PRESENT
    trace = []
    asked = 0
    freq = em.theta.mean(0)
    for q in range(budget + 1):
        post = em.posterior(st)
        trace.append(post)
        if q == budget or (early_stop is not None and post.max() >= early_stop):
            break
        unknown = np.where(st == UNKNOWN)[0]
        if policy == "random":
            j = int(rng.choice(unknown))
        elif policy == "frequency":
            j = int(unknown[np.argmax(freq[unknown])])
        else:
            j = int(np.argmax(em.expected_information_gain(post, st)))
        truth = prof[j] == 1
        if rng.random() < noise:
            truth = not truth
        st[j] = PRESENT if truth else ABSENT
        asked += 1
    return trace, asked


def e3_interactive(budget=10, noise=0.03):
    policies = ["random", "frequency", "eig"]
    curves = {p: {"top1": np.zeros(budget + 1), "top3": np.zeros(budget + 1)} for p in policies}
    n = 0
    stop = {p: {"top1": [], "top3": [], "asked": [], "conf": [], "correct": []} for p in policies}
    t_eig = []
    for s in SEEDS:
        rng = np.random.default_rng(200 + s)
        tr, te = group_split(s)
        em = EvidenceModel().fit(tr[COLS].to_numpy(), tr["prognosis"].to_numpy(), COLS)
        for _, row in te.iterrows():
            prof = row[COLS].to_numpy().astype(int)
            truth = em.diseases.index(row.prognosis)
            for _rep in range(3):
                init = sample_reports(prof, 2, rng)
                n += 1
                for p in policies:
                    r2 = np.random.default_rng(rng.integers(1 << 30))
                    trace, _ = run_dialogue(em, prof, init, p, budget, r2, noise, None)
                    for q, post in enumerate(trace):
                        order = np.argsort(-post)
                        curves[p]["top1"][q] += order[0] == truth
                        curves[p]["top3"][q] += truth in order[:3]
                    r3 = np.random.default_rng(rng.integers(1 << 30))
                    t0 = time.perf_counter()
                    trace, asked = run_dialogue(em, prof, init, p, budget, r3, noise, 0.90)
                    if p == "eig":
                        t_eig.append((time.perf_counter() - t0) / max(asked, 1))
                    post = trace[-1]
                    order = np.argsort(-post)
                    stop[p]["top1"].append(order[0] == truth)
                    stop[p]["top3"].append(truth in order[:3])
                    stop[p]["asked"].append(asked)
                    stop[p]["conf"].append(float(post.max()))
                    stop[p]["correct"].append(bool(order[0] == truth))
    out = {"n_dialogues": n, "budget": budget, "noise": noise, "curves": {}, "early_stop": {},
           "ms_per_question_eig": float(np.mean(t_eig) * 1000)}
    for p in policies:
        out["curves"][p] = {k: (v / n).tolist() for k, v in curves[p].items()}
        d = stop[p]
        out["early_stop"][p] = {"top1": float(np.mean(d["top1"])), "top3": float(np.mean(d["top3"])),
                                "mean_questions": float(np.mean(d["asked"]))}
    # calibration + abstention on the EIG policy
    conf, corr = np.array(stop["eig"]["conf"]), np.array(stop["eig"]["correct"])
    bins = np.linspace(0, 1, 11)
    ece, rel = 0.0, []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            ece += m.mean() * abs(conf[m].mean() - corr[m].mean())
            rel.append([float(conf[m].mean()), float(corr[m].mean()), int(m.sum())])
    abst = []
    for tau in [0.0, 0.3, 0.5, 0.7, 0.9]:
        m = conf >= tau
        abst.append({"tau": tau, "coverage": float(m.mean()), "accuracy": float(corr[m].mean()) if m.any() else None})
    out["calibration"] = {"ece": float(ece), "reliability": rel, "abstention": abst}
    return out


def e3_noise_sweep():
    return {str(nz): e3_interactive(noise=nz)["early_stop"]["eig"] for nz in [0.0, 0.05, 0.10]}


# --------------------------------------------------------------------- E4 NLU
def e4_nlu():
    out = {}
    for label, kw in {"Exact canonical names only": dict(use_fuzzy=False, lay=False),
                      "+ lay-term lexicon": dict(use_fuzzy=False, lay=True),
                      "+ fuzzy char n-gram (final)": dict(use_fuzzy=True, lay=True)}.items():
        import anamnesis.nlu as nlu_mod
        saved = nlu_mod.LAY_TERMS
        if not kw["lay"]:
            nlu_mod.LAY_TERMS = {}
        ex = SymptomExtractor(COLS, use_fuzzy=kw["use_fuzzy"])
        nlu_mod.LAY_TERMS = saved
        tp = fp = fn = neg_ok = neg_total = 0
        for text, gold in CASES:
            pred = {m.symptom: int(m.present) for m in ex.extract(text)}
            for s, v in gold.items():
                if s in pred and pred[s] == v:
                    tp += 1
                else:
                    fn += 1
                if v == 0:
                    neg_total += 1
                    neg_ok += int(pred.get(s) == 0)
            fp += sum(1 for s, v in pred.items() if gold.get(s) != v)
        p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        out[label] = {"precision": p, "recall": r, "f1": 2 * p * r / max(p + r, 1e-9),
                      "negation_accuracy": neg_ok / max(neg_total, 1)}
    out["n_utterances"] = len(CASES)
    out["n_labels"] = sum(len(g) for _, g in CASES)
    return out


# --------------------------------------------------------------------- figures
def figures(r):
    e1 = r["e1"]["rows"]
    names = list(e1)
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(x - 0.27, [e1[n]["official_test"] * 100 for n in names], 0.27, color=MUTED, label="Official Testing.csv")
    ax.bar(x, [e1[n]["random_split"] * 100 for n in names], 0.27, color="#c9ccd1", label="Random 80/20 row split")
    ax.bar(x + 0.27, [e1[n]["group_split_mean"] * 100 for n in names], 0.27, color=ACCENT,
           yerr=[e1[n]["group_split_std"] * 100 for n in names], capsize=2, label="Profile-grouped split (ours)")
    ax.set_xticks(x, [n.replace(" ", "\n", 1) for n in names], fontsize=8)
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_ylim(0, 125)
    ax.set_yticks(range(0, 101, 20))
    ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout()
    fig.savefig(FIG / "fig_leakage.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    lab = {"random": "Random question", "frequency": "Most-common symptom", "eig": "Expected information gain (ours)"}
    sty = {"random": (MUTED, ":"), "frequency": ("#5b6b7c", "--"), "eig": (ACCENT, "-")}
    for p, c in r["e3"]["curves"].items():
        col, ls = sty[p]
        ax.plot(range(len(c["top1"])), np.array(c["top1"]) * 100, ls, color=col, lw=2, marker="o", ms=3, label=lab[p])
    ax.set_xlabel("Follow-up questions asked (after 2 volunteered symptoms)")
    ax.set_ylabel("Top-1 accuracy (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "fig_questions.png")
    plt.close(fig)

    e2 = r["e2"]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for n, v in e2.items():
        ks = sorted(v, key=int)
        mine = "ours" in n
        ax.plot([int(k) for k in ks], [v[k] * 100 for k in ks], "-" if mine else "--", marker="o", ms=3,
                lw=2.4 if mine else 1.2, color=ACCENT if mine else None, label=n)
    ax.set_xlabel("Symptoms volunteered by the patient")
    ax.set_ylabel("Top-1 accuracy (%)")
    ax.set_xticks([1, 2, 3, 4])
    ax.legend(frameon=False, fontsize=7.5, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "fig_partial.png")
    plt.close(fig)

    rel = r["e3"]["calibration"]["reliability"]
    fig, ax = plt.subplots(figsize=(3.6, 3.4))
    ax.plot([0, 1], [0, 1], ":", color=MUTED)
    ax.plot([a for a, _, _ in rel], [b for _, b, _ in rel], "o-", color=ACCENT)
    ax.set_xlabel("Model confidence")
    ax.set_ylabel("Observed accuracy")
    ax.set_title(f"ECE = {r['e3']['calibration']['ece']:.3f}", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "fig_calibration.png")
    plt.close(fig)


def main():
    t = time.time()
    r = {"e1": e1_leakage()}
    print("E1 done", round(time.time() - t, 1))
    r["e2"] = e2_partial()
    print("E2 done", round(time.time() - t, 1))
    r["e3"] = e3_interactive()
    print("E3 done", round(time.time() - t, 1))
    r["e3_noise"] = e3_noise_sweep()
    r["e4"] = e4_nlu()
    (RES / "results.json").write_text(json.dumps(r, indent=2, default=float))
    figures(r)
    print(json.dumps({k: r[k] for k in ["e1", "e2", "e4", "e3_noise"]}, indent=1, default=float))
    print(json.dumps({k: v for k, v in r["e3"].items() if k != "curves"}, indent=1))
    print({p: [round(x, 3) for x in c["top1"]] for p, c in r["e3"]["curves"].items()})


if __name__ == "__main__":
    main()
