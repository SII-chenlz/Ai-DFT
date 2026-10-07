"""Optional local embedding provider for semantic evidence retrieval."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerProvider:
    """Lazy wrapper so the base AIFS install does not require torch."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - deployment-dependent
            raise RuntimeError(
                "AIFS_EMBEDDING_MODEL is set but sentence-transformers is not installed; "
                "install the retrieval extra"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


class FaissIndex:
    """Persistent cosine-similarity index backed by FAISS inner product."""

    def __init__(self, index_path: Path, encoder: EmbeddingProvider) -> None:
        try:
            import faiss
            import numpy as np
        except ImportError as exc:  # pragma: no cover - deployment-dependent
            raise RuntimeError(
                "FAISS semantic retrieval requires faiss-cpu and numpy; install the retrieval extra"
            ) from exc
        self._faiss = faiss
        self._np = np
        self.index_path = index_path
        self.ids_path = index_path.with_suffix(index_path.suffix + ".ids.json")
        self.encoder = encoder
        self.index = None
        self.record_ids: list[str] = []
        self._load()

    def _load(self) -> None:
        if self.index_path.exists() and self.ids_path.exists():
            self.index = self._faiss.read_index(str(self.index_path))
            self.record_ids = json.loads(self.ids_path.read_text(encoding="utf-8"))

    def rebuild(self, records: Sequence[tuple[str, str]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_ids = [record_id for record_id, _ in records]
        if not records:
            self.index = None
            if self.index_path.exists():
                self.index_path.unlink()
            if self.ids_path.exists():
                self.ids_path.unlink()
            return
        vectors = self._np.asarray(
            self.encoder.encode([text for _, text in records]), dtype="float32"
        )
        self.index = self._faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)
        self._faiss.write_index(self.index, str(self.index_path))
        self.ids_path.write_text(json.dumps(self.record_ids), encoding="utf-8")

    def search(self, text: str, limit: int) -> list[tuple[str, float]]:
        if self.index is None or not self.record_ids:
            return []
        query = self._np.asarray(self.encoder.encode([text]), dtype="float32")
        scores, positions = self.index.search(query, min(limit, len(self.record_ids)))
        return [
            (self.record_ids[int(position)], float(score))
            for score, position in zip(scores[0], positions[0], strict=True)
            if int(position) >= 0
        ]
