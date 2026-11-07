"""Build and restore a local BM25 index over canonical chunks."""
import hashlib
import json
import os
from pathlib import Path
import re
import math

import joblib
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+(?:[.+/#-]\w+)*(?:\+\+|#)?", text.casefold())


class SparseIndex:
    def __init__(self, path: Path, fingerprint: str):
        self.path = path
        self.fingerprint = fingerprint
        self.chunk_ids = []
        self.index = None

    def signature(self, chunks):
        return hashlib.sha256(json.dumps({
            "fingerprint": self.fingerprint, "chunks": [(chunk.chunk_id, chunk.text) for chunk in chunks],
        }, sort_keys=True).encode()).hexdigest()

    def rebuild(self, chunks):
        self.chunk_ids = [chunk.chunk_id for chunk in chunks]
        self.index = BM25Okapi([tokenize(chunk.text) for chunk in chunks]) if chunks else None
        payload = {"format": 1, "signature": self.signature(chunks), "ids": self.chunk_ids, "index": self.index}
        temporary = self.path.with_suffix(".tmp")
        try:
            joblib.dump(payload, temporary, compress=3)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, chunks) -> bool:
        """Load only the application's own snapshot; recover stale/corrupt files."""
        try:
            payload = joblib.load(self.path)
            valid = (
                payload["format"] == 1 and payload["signature"] == self.signature(chunks)
                and payload["ids"] == [chunk.chunk_id for chunk in chunks]
                and (isinstance(payload["index"], BM25Okapi) if chunks else payload["index"] is None)
            )
            if not valid:
                raise ValueError("Stale BM25 snapshot")
            if chunks:
                index = payload["index"]
                terms = [tokenize(chunk.text) for chunk in chunks]
                expected = BM25Okapi(terms)
                if (index.doc_freqs != expected.doc_freqs or index.doc_len != expected.doc_len
                        or index.corpus_size != expected.corpus_size or index.idf != expected.idf
                        or index.avgdl != expected.avgdl or index.k1 != expected.k1
                        or index.b != expected.b or index.epsilon != expected.epsilon):
                    raise ValueError("Inconsistent BM25 statistics")
            self.chunk_ids, self.index = payload["ids"], payload["index"]
            return True
        except Exception:
            self.rebuild(chunks)
            return False

    def search(self, question: str, chunks, selected_paper_ids: set[str], k: int):
        """Filter eligible positions before ranking; retain genuine lexical matches.

        BM25 can assign zero/negative scores in small corpora. A lexical match,
        rather than an arbitrary positive-score cutoff, defines eligibility.
        """
        if not self.index or k <= 0:
            return []
        by_id = {chunk.chunk_id: chunk for chunk in chunks}
        terms = tokenize(question)
        if not terms:
            return []
        scores = self.index.get_scores(terms)
        eligible = []
        for position, chunk_id in enumerate(self.chunk_ids):
            chunk = by_id.get(chunk_id)
            if chunk and chunk.paper_id in selected_paper_ids and any(
                term in self.index.doc_freqs[position] for term in terms
            ) and math.isfinite(float(scores[position])):
                eligible.append((chunk_id, float(scores[position])))
        return sorted(eligible, key=lambda item: (-item[1], item[0]))[:k]
