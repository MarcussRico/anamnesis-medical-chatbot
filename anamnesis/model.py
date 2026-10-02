"""Partial-evidence Bayesian diagnosis and information-gain question selection.

The posterior conditions only on symptoms whose state is *known* (reported
present or confirmed absent). Unasked symptoms are marginalised out, which is
what lets the chatbot reason from two complaints instead of a full 132-field
form.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import knowledge as kb

UNKNOWN, ABSENT, PRESENT = -1, 0, 1


@dataclass
class EvidenceModel:
    alpha: float = 0.05          # Laplace smoothing on symptom counts
    slip: float = 0.03           # chance a patient misreports a symptom either way
    diseases: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    theta: np.ndarray | None = None   # P(symptom reported | disease), shape (D, S)
    prior: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray, symptoms: list[str]) -> "EvidenceModel":
        self.symptoms = list(symptoms)
        self.diseases = sorted(set(y))
        D = len(self.diseases)
        theta = np.zeros((D, X.shape[1]))
        for i, d in enumerate(self.diseases):
            rows = X[y == d]
            theta[i] = (rows.sum(0) + self.alpha) / (len(rows) + 2 * self.alpha)
        # A symptom is reported with prob theta*(1-slip) + (1-theta)*slip.
        self.theta = theta * (1 - self.slip) + (1 - theta) * self.slip
        self.prior = np.full(D, 1.0 / D)
        return self

    def log_likelihood(self, state: np.ndarray) -> np.ndarray:
        pres, absn = state == PRESENT, state == ABSENT
        lt, l1t = np.log(self.theta), np.log1p(-self.theta)
        return lt[:, pres].sum(1) + l1t[:, absn].sum(1)

    def posterior(self, state: np.ndarray) -> np.ndarray:
        logp = np.log(self.prior) + self.log_likelihood(state)
        logp -= logp.max()
        p = np.exp(logp)
        return p / p.sum()

    def expected_information_gain(self, post: np.ndarray, state: np.ndarray) -> np.ndarray:
        """EIG(s) = H(D) - E_answer[H(D | answer)] for every unasked symptom s."""
        def H(p):
            p = np.clip(p, 1e-12, 1)
            return -(p * np.log2(p)).sum(0)

        q = self.theta                                   # (D, S)
        p_yes = post @ q                                 # (S,)
        post_yes = (post[:, None] * q) / np.clip(p_yes, 1e-12, None)
        post_no = (post[:, None] * (1 - q)) / np.clip(1 - p_yes, 1e-12, None)
        eig = H(post) - (p_yes * H(post_yes) + (1 - p_yes) * H(post_no))
        eig[state != UNKNOWN] = -np.inf
        return eig

    def explain(self, state: np.ndarray, top: int, rival: int) -> list[tuple[str, str, float]]:
        """Per-symptom log-likelihood ratio of the top disease against its nearest rival."""
        rows = []
        for j in np.where(state != UNKNOWN)[0]:
            a, b = self.theta[top, j], self.theta[rival, j]
            if state[j] == PRESENT:
                llr, kind = np.log(a / b), "present"
            else:
                llr, kind = np.log((1 - a) / (1 - b)), "absent"
            rows.append((self.symptoms[j], kind, float(llr)))
        return sorted(rows, key=lambda r: -abs(r[2]))


def build_default() -> EvidenceModel:
    prof = kb.unique_profiles()
    cols = kb.symptom_columns()
    return EvidenceModel().fit(prof[cols].to_numpy(), prof["prognosis"].to_numpy(), cols)
