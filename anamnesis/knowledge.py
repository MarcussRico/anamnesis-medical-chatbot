"""Loads the disease–symptom knowledge base and cleans its names.

Source: the public Kaggle "Disease Prediction Using Machine Learning" data
(Training.csv / Testing.csv) and its companion description, precaution and
severity tables.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "raw"


def clean_symptom(raw: str) -> str:
    s = raw.strip().replace("_", " ").replace("  ", " ")
    s = s.replace("(typhos)", "").replace(" .1", "").strip()
    return " ".join(s.split())


def _read_frame(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / name)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df["prognosis"] = df["prognosis"].str.strip()
    return df


@lru_cache(maxsize=1)
def load_training() -> pd.DataFrame:
    return _read_frame("Training.csv")


@lru_cache(maxsize=1)
def load_testing() -> pd.DataFrame:
    return _read_frame("Testing.csv")


@lru_cache(maxsize=1)
def symptom_columns() -> list[str]:
    return [c for c in load_training().columns if c != "prognosis"]


@lru_cache(maxsize=1)
def unique_profiles() -> pd.DataFrame:
    """The 4,920 training rows collapse to this many distinct (symptoms, disease) rows."""
    return load_training().drop_duplicates().reset_index(drop=True)


@lru_cache(maxsize=1)
def descriptions() -> dict[str, str]:
    out = {}
    with open(DATA / "symptom_Description.csv", newline="") as f:
        for row in csv.reader(f):
            if row:
                out[row[0].strip()] = row[1].strip()
    return out


@lru_cache(maxsize=1)
def precautions() -> dict[str, list[str]]:
    out = {}
    with open(DATA / "symptom_precaution.csv", newline="") as f:
        for row in csv.reader(f):
            if row:
                out[row[0].strip()] = [p.strip().capitalize() for p in row[1:] if p.strip()]
    return out


@lru_cache(maxsize=1)
def severity() -> dict[str, int]:
    out = {}
    with open(DATA / "symptom_severity.csv", newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[1].strip().isdigit():
                out[row[0].strip()] = int(row[1])
    return out


def severity_vector() -> np.ndarray:
    sev = severity()
    return np.array([sev.get(c, sev.get(c.replace(" ", "_"), 3)) for c in symptom_columns()])


DISPLAY = {
    "(vertigo) Paroymsal  Positional Vertigo": "Paroxysmal Positional Vertigo",
    "Osteoarthristis": "Osteoarthritis",
    "Peptic ulcer diseae": "Peptic ulcer disease",
    "Dimorphic hemmorhoids(piles)": "Haemorrhoids (piles)",
    "hepatitis A": "Hepatitis A",
    "Paralysis (brain hemorrhage)": "Paralysis (brain haemorrhage)",
}


def display(disease: str) -> str:
    return DISPLAY.get(disease, disease)


def lookup(table: dict, disease: str):
    """Description/precaution tables spell a few diseases differently."""
    if disease == "Dimorphic hemmorhoids(piles)":
        disease = "Dimorphic hemorrhoids(piles)"
    if disease in table:
        return table[disease]
    key = disease.lower().replace(" ", "")
    for k, v in table.items():
        if k.lower().replace(" ", "") == key:
            return v
    return None
