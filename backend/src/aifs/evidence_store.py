"""SQLite evidence graph and lexical retrieval implementation.

The stored raw JSON remains the source of truth. FTS5 is deliberately exposed
as a retrieval mode rather than presented as a semantic embedding model.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from aifs.evidence_models import (
    EvidenceHit,
    EvidenceQuote,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from aifs.vector_index import EmbeddingProvider, FaissIndex


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalise_functional(value: str | None) -> str | None:
    if value is None:
        return None
    compact = re.sub(r"[^a-z0-9]", "", value.lower())
    aliases = {"pbe1pbe": "pbe0", "pbe0": "pbe0", "pbe0d3bj": "pbe0-d3bj"}
    return aliases.get(compact, value.strip())


class EvidenceStore:
    """Small, process-safe store for records, evidence and graph edges."""

    def __init__(
        self,
        db_path: Path,
        embedding_provider: EmbeddingProvider | None = None,
        faiss_index: FaissIndex | None = None,
    ) -> None:
        self.db_path = db_path
        self.embedding_provider = embedding_provider
        self.faiss_index = faiss_index
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def has_record(self, record_id: str) -> bool:
        """Check that a plan's local evidence reference points to an imported record."""
        row = self._connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()
        return row is not None

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                doi TEXT,
                title TEXT,
                system TEXT,
                calculation TEXT,
                benchmark TEXT,
                functional TEXT,
                functional_normalized TEXT,
                protocol TEXT,
                experience_type TEXT,
                summary TEXT,
                raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
                quote TEXT NOT NULL,
                page INTEGER,
                section TEXT,
                evidence_type TEXT,
                UNIQUE(record_id, quote, page, section)
            );
            CREATE TABLE IF NOT EXISTS edges (
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                UNIQUE(source_type, source_id, relation, target_type, target_id)
            );
            CREATE TABLE IF NOT EXISTS record_vectors (
                record_id TEXT PRIMARY KEY REFERENCES records(record_id) ON DELETE CASCADE,
                vector_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS record_search USING fts5(
                record_id UNINDEXED,
                search_text
            );
            """
        )
        self._connection.commit()

    def upsert_record(self, record: dict[str, Any]) -> None:
        record_id = _text(record.get("record_id"))
        if record_id is None:
            raise ValueError("record is missing a non-empty record_id")
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        context = record.get("context") if isinstance(record.get("context"), dict) else {}
        method = record.get("method") if isinstance(record.get("method"), dict) else {}
        experience = record.get("experience") if isinstance(record.get("experience"), dict) else {}
        source_doi = _text(source.get("doi"))
        title = _text(source.get("title"))
        system = _text(context.get("system"))
        calculation = _text(context.get("calculation"))
        benchmark = _text(context.get("benchmark"))
        functional = _text(method.get("functional"))
        protocol = _text(method.get("protocol"))
        experience_type = _text(experience.get("type"))
        summary = _text(experience.get("summary"))
        raw_json = json.dumps(record, ensure_ascii=False, sort_keys=True)
        values = (
            record_id,
            source_doi,
            title,
            system,
            calculation,
            benchmark,
            functional,
            _normalise_functional(functional),
            protocol,
            experience_type,
            summary,
            raw_json,
        )
        connection = self._connection
        connection.execute(
            """
            INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
              doi=excluded.doi, title=excluded.title, system=excluded.system,
              calculation=excluded.calculation, benchmark=excluded.benchmark,
              functional=excluded.functional, functional_normalized=excluded.functional_normalized,
              protocol=excluded.protocol, experience_type=excluded.experience_type,
              summary=excluded.summary, raw_json=excluded.raw_json
            """,
            values,
        )
        connection.execute("DELETE FROM evidence WHERE record_id = ?", (record_id,))
        connection.execute(
            "DELETE FROM edges WHERE source_type = 'record' AND source_id = ?", (record_id,)
        )
        connection.execute("DELETE FROM record_search WHERE record_id = ?", (record_id,))
        connection.execute("DELETE FROM record_vectors WHERE record_id = ?", (record_id,))
        evidence_values: list[tuple[Any, ...]] = []
        raw_evidence = record.get("evidence")
        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if not isinstance(item, dict):
                    continue
                quote = _text(item.get("quote"))
                if quote is None:
                    continue
                evidence_values.append(
                    (
                        record_id,
                        quote,
                        item.get("page"),
                        _text(item.get("section")),
                        _text(item.get("evidence_type")),
                    )
                )
        connection.executemany(
            "INSERT OR IGNORE INTO evidence(record_id, quote, page, section, evidence_type) "
            "VALUES (?, ?, ?, ?, ?)",
            evidence_values,
        )
        if functional:
            connection.execute(
                "INSERT OR IGNORE INTO edges VALUES ('record', ?, 'uses', 'functional', ?)",
                (record_id, _normalise_functional(functional)),
            )
        if source_doi:
            connection.execute(
                "INSERT OR IGNORE INTO edges VALUES ('record', ?, 'cites', 'paper', ?)",
                (record_id, source_doi),
            )
        search_text = " ".join(
            value
            for value in (
                title,
                system,
                calculation,
                benchmark,
                functional,
                protocol,
                experience_type,
                summary,
            )
            if value
        )
        connection.execute(
            "INSERT INTO record_search(record_id, search_text) VALUES (?, ?)",
            (record_id, search_text),
        )
        if self.embedding_provider is not None:
            vector = self.embedding_provider.encode([search_text])[0]
            connection.execute(
                "INSERT INTO record_vectors(record_id, vector_json) VALUES (?, ?)",
                (record_id, json.dumps(vector)),
            )
        connection.commit()
        if self.faiss_index is not None:
            rows = connection.execute(
                "SELECT record_id, search_text FROM record_search ORDER BY record_id"
            ).fetchall()
            self.faiss_index.rebuild([(row["record_id"], row["search_text"]) for row in rows])

    def search(self, query: EvidenceSearchRequest) -> EvidenceSearchResponse:
        terms = " ".join(
            value for value in (query.system_description, query.calculation_goal) if value
        )
        tokens = re.findall(r"[\w-]+", terms, flags=re.UNICODE)
        if not tokens:
            return EvidenceSearchResponse(
                retrieval_mode=(
                    "semantic_vector"
                    if self.faiss_index or self.embedding_provider
                    else "lexical_fallback"
                ),
                query=terms,
                hits=[],
            )
        allowed = {_normalise_functional(value) for value in query.candidate_functionals}
        if self.faiss_index is not None:
            return self._faiss_search(terms, query, allowed)
        if self.embedding_provider is not None:
            return self._vector_search(terms, query, allowed)
        return self._fts_search(terms, tokens, query, allowed)

    def _fts_search(
        self,
        terms: str,
        tokens: list[str],
        query: EvidenceSearchRequest,
        allowed: set[str | None],
    ) -> EvidenceSearchResponse:
        fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:24])
        rows = self._connection.execute(
            """
            SELECT r.*, bm25(record_search) AS rank
            FROM record_search JOIN records r ON r.record_id = record_search.record_id
            WHERE record_search MATCH ?
            ORDER BY rank LIMIT ?
            """,
            (fts_query, max(query.limit * 5, query.limit)),
        ).fetchall()
        hits: list[EvidenceHit] = []
        for row in rows:
            if allowed and row["functional_normalized"] not in allowed:
                continue
            evidence_rows = self._connection.execute(
                "SELECT quote, page, section, evidence_type FROM evidence "
                "WHERE record_id = ? ORDER BY evidence_id",
                (row["record_id"],),
            ).fetchall()
            hits.append(
                EvidenceHit(
                    record_id=row["record_id"],
                    doi=row["doi"],
                    title=row["title"],
                    system=row["system"],
                    calculation=row["calculation"],
                    benchmark=row["benchmark"],
                    functional=row["functional"],
                    protocol=row["protocol"],
                    experience_type=row["experience_type"],
                    summary=row["summary"],
                    score=1.0 / (1.0 + abs(float(row["rank"]))),
                    evidence=[EvidenceQuote(**dict(item)) for item in evidence_rows],
                )
            )
            if len(hits) >= query.limit:
                break
        return EvidenceSearchResponse(retrieval_mode="lexical_fallback", query=terms, hits=hits)

    def _faiss_search(
        self,
        terms: str,
        query: EvidenceSearchRequest,
        allowed: set[str | None],
    ) -> EvidenceSearchResponse:
        assert self.faiss_index is not None
        vector_ranked = self.faiss_index.search(terms, query.limit * 4)
        vector_by_id = {
            record_id: (rank, score) for rank, (record_id, score) in enumerate(vector_ranked, 1)
        }
        tokens = re.findall(r"[\w-]+", terms, flags=re.UNICODE)
        lexical = self._fts_search(
            terms, tokens, query.model_copy(update={"limit": query.limit * 4}), allowed
        )
        lexical_by_id = {hit.record_id: (rank, hit) for rank, hit in enumerate(lexical.hits, 1)}
        record_ids = set(vector_by_id) | set(lexical_by_id)
        ranked_ids = sorted(
            record_ids,
            key=lambda record_id: (
                (1.0 / (60 + vector_by_id[record_id][0]) if record_id in vector_by_id else 0.0)
                + (1.0 / (60 + lexical_by_id[record_id][0]) if record_id in lexical_by_id else 0.0)
            ),
            reverse=True,
        )
        hits: list[EvidenceHit] = []
        for record_id in ranked_ids[: query.limit]:
            row = self._connection.execute(
                "SELECT * FROM records WHERE record_id = ?", (record_id,)
            ).fetchone()
            if row is None or (allowed and row["functional_normalized"] not in allowed):
                continue
            _, lexical_hit = lexical_by_id.get(record_id, (0, None))
            score = (vector_by_id[record_id][1] if record_id in vector_by_id else 0.0) + (
                1.0 / (60 + lexical_by_id[record_id][0]) if record_id in lexical_by_id else 0.0
            )
            hits.append(
                lexical_hit.model_copy(update={"score": score})
                if lexical_hit is not None
                else self._hit_for_record(row, score)
            )
        return EvidenceSearchResponse(retrieval_mode="hybrid", query=terms, hits=hits)

    def _hit_for_record(self, row: sqlite3.Row, score: float) -> EvidenceHit:
        evidence_rows = self._connection.execute(
            "SELECT quote, page, section, evidence_type FROM evidence "
            "WHERE record_id = ? ORDER BY evidence_id",
            (row["record_id"],),
        ).fetchall()
        return EvidenceHit(
            record_id=row["record_id"],
            doi=row["doi"],
            title=row["title"],
            system=row["system"],
            calculation=row["calculation"],
            benchmark=row["benchmark"],
            functional=row["functional"],
            protocol=row["protocol"],
            experience_type=row["experience_type"],
            summary=row["summary"],
            score=score,
            evidence=[EvidenceQuote(**dict(item)) for item in evidence_rows],
        )

    def _vector_search(
        self,
        terms: str,
        query: EvidenceSearchRequest,
        allowed: set[str | None],
    ) -> EvidenceSearchResponse:
        assert self.embedding_provider is not None
        query_vector = self.embedding_provider.encode([terms])[0]
        rows = self._connection.execute(
            "SELECT r.*, v.vector_json FROM records r "
            "JOIN record_vectors v ON v.record_id = r.record_id"
        ).fetchall()
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            if allowed and row["functional_normalized"] not in allowed:
                continue
            vector = json.loads(row["vector_json"])
            score = sum(float(a) * float(b) for a, b in zip(query_vector, vector, strict=True))
            ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hits: list[EvidenceHit] = []
        for score, row in ranked[: query.limit]:
            evidence_rows = self._connection.execute(
                "SELECT quote, page, section, evidence_type FROM evidence "
                "WHERE record_id = ? ORDER BY evidence_id",
                (row["record_id"],),
            ).fetchall()
            hits.append(
                EvidenceHit(
                    record_id=row["record_id"],
                    doi=row["doi"],
                    title=row["title"],
                    system=row["system"],
                    calculation=row["calculation"],
                    benchmark=row["benchmark"],
                    functional=row["functional"],
                    protocol=row["protocol"],
                    experience_type=row["experience_type"],
                    summary=row["summary"],
                    score=score,
                    evidence=[EvidenceQuote(**dict(item)) for item in evidence_rows],
                )
            )
        return EvidenceSearchResponse(retrieval_mode="semantic_vector", query=terms, hits=hits)
