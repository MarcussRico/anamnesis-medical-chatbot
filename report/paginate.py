"""Reads the rendered PDF and writes printed page numbers for the TOC/LOF/LOT."""
import json, re, sys
import pymupdf

pdf = pymupdf.open(sys.argv[1])
texts = [pg.get_text() for pg in pdf]
start = next(i for i, t in enumerate(texts) if re.search(r"^CHAPTER 1\s*\n\s*INTRODUCTION", t, re.M))
def find(pattern, frm=start):
    for i in range(frm, len(texts)):
        if re.search(pattern, texts[i], re.M):
            return i - start + 1
    return None
keys = {f"ch{n}": rf"^CHAPTER {n}\s*$" for n in range(1, 9)}
secs = ["1.1","1.2","1.3","1.4","1.5","2.1","2.2","2.3","3.1","3.2","3.3","4.1","4.2","4.3","4.4","4.5",
        "5.1","5.2","5.3","6.1","6.2","6.3","6.4","7.1","7.2","7.3","8.1","8.2"]
for s in secs:
    keys[f"s{s}"] = rf"^{re.escape(s)} \S"
keys.update({"refs": r"^REFERENCES\s*$", "app": r"^APPENDIX\s*$", "a1": r"^A\.1 Full source", "a2": r"^A\.2 Complete",
             "a3": r"^A\.3 Self", "a4": r"^A\.4 PBL Poster"})
for f in ["4.1","4.2","5.1","5.2","5.3","5.4","5.5","6.1","6.2","6.3","6.4"]:
    keys[f"f{f}"] = rf"Figure {re.escape(f)} —"
for t in ["2.1","3.1","3.2","4.1","6.1","6.2","6.3","6.4"]:
    keys[f"t{t}"] = rf"Table {re.escape(t)} —"
out = {k: find(v) for k, v in keys.items()}
missing = [k for k, v in out.items() if v is None]
print("pages:", len(texts), "body starts at pdf page", start + 1, "missing:", missing)
json.dump(out, open(sys.argv[2], "w"), indent=1)
