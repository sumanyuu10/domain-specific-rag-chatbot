"""Build and restore a local BM25 index over canonical chunks."""
import hashlib
import json
import os
from pathlib import Path
import re

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
            "fingerprint": self.fingerprint, "ids": [chunk.chunk_id for chunk in chunks],
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
            self.chunk_ids, self.index = payload["ids"], payload["index"]
            return True
        except Exception:
            self.rebuild(chunks)
            return False
