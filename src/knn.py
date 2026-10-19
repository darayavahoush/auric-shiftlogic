"""
kNN example retrieval for the prompt. Embeddings only CHOOSE which labelled lines to show Granite; Granite still
makes every verdict. Labelled pool = visible items (src/pool.json, data).

Embedders: "st" = sentence-transformers all-MiniLM-L6-v2 (local, downloads once; best), "tfidf" = char n-gram
TF-IDF (no download, offline fallback). Names/blocks/stations are masked before embedding so neighbours match on
the *phrasing and intent*, not on who is mentioned.
"""
import json, os, re
import numpy as np

POOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool.json")
_NAMES = re.compile(r"\b(Ayesha|Daniel|Ingrid|Lukas|Meera|Nadia|Priya|Rohan|Samuel|Tomas|Farah|Kiran|Omar|Zoe|Hugo|Bianca|Tobias|Leila)\b")


def mask(text: str, staff=()) -> str:
    t = text
    for s in set(list(staff)):
        t = re.sub(r"\b" + re.escape(s) + r"\b", "PERSON", t)
    t = _NAMES.sub("PERSON", t)
    t = re.sub(r"\b\d\d:00\b", "TIME", t)
    return re.sub(r"\b(intake|calibration|packing)\b", "STATION", t, flags=re.I)


class Retriever:
    def __init__(self, backend: str = "auto", pool_path: str = POOL_PATH):
        self.pool = json.load(open(pool_path))
        self.texts = [mask(p["text"]) for p in self.pool]
        self.backend = backend
        if backend in ("auto", "st"):
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                self.backend = "st"
            except Exception:
                if backend == "st":
                    raise
                self.backend = "tfidf"
        if self.backend == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, sublinear_tf=True)
            self.M = self.vec.fit_transform(self.texts)
        else:
            self.M = self.model.encode(self.texts, normalize_embeddings=True)

    def _sims(self, queries):
        q = [mask(x) for x in queries]
        if self.backend == "tfidf":
            return (self.vec.transform(q) @ self.M.T).toarray()
        return self.model.encode(q, normalize_embeddings=True) @ self.M.T

    def neighbours(self, lines, k=3, max_total=36, exclude_item=None):
        """lines: list of text. Returns up to max_total pool rows, best matches first, de-duplicated by masked text,
        never from `exclude_item` (so a visible item doesn't retrieve itself)."""
        S = self._sims(lines)
        if exclude_item is not None:
            for j, p in enumerate(self.pool):
                if p["item"] == exclude_item:
                    S[:, j] = -1
        picked, seen = [], set()
        for rank in range(k):
            for qi in range(len(lines)):
                order = np.argsort(-S[qi])
                for j in order[: k + 6]:
                    key = self.texts[j]
                    if key in seen:
                        continue
                    seen.add(key); picked.append((float(S[qi, j]), int(j)))
                    break
            if len(picked) >= max_total:
                break
        picked.sort(reverse=True)
        return [self.pool[j] for _, j in picked[:max_total]]
