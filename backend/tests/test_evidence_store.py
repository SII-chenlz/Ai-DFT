import json

from aifs.evidence_models import EvidenceSearchRequest
from aifs.evidence_store import EvidenceStore
from aifs.vector_index import FaissIndex


class FakeEmbeddingProvider:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "water" in text else [0.0, 1.0] for text in texts]


def test_faiss_index_persists_and_returns_nearest_record(tmp_path):
    index = FaissIndex(tmp_path / "records.faiss", FakeEmbeddingProvider())
    index.rebuild([("water-record", "water molecule"), ("nickel-record", "nickel cluster")])

    hits = index.search("water geometry", limit=1)

    assert hits[0][0] == "water-record"
    assert hits[0][1] == 1.0


def test_store_uses_faiss_for_record_and_query_retrieval(tmp_path):
    index = FaissIndex(tmp_path / "records.faiss", FakeEmbeddingProvider())
    store = EvidenceStore(tmp_path / "evidence.sqlite3", faiss_index=index)
    store.upsert_record(sample_record())

    response = store.search(EvidenceSearchRequest(system_description="water system"))

    assert response.retrieval_mode == "hybrid"
    assert response.hits[0].record_id == "MREC-1"
    store.close()


def sample_record(record_id: str = "MREC-1") -> dict[str, object]:
    return {
        "record_id": record_id,
        "source": {"doi": "10.1/example", "title": "DFT water benchmark"},
        "context": {
            "system": "water molecule in the gas phase",
            "calculation": "geometry optimization",
            "benchmark": "CCSD(T) reference geometry",
        },
        "method": {"functional": "PBE1PBE", "protocol": "def2-TZVP; Gaussian"},
        "experience": {"type": "evaluation", "summary": "PBE0 gives accurate geometry."},
        "evidence": [
            {
                "quote": "PBE0 gives accurate geometry.",
                "page": 4,
                "section": "Results",
                "evidence_type": "text",
            }
        ],
    }


def test_upsert_is_idempotent_and_preserves_raw_record(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    record = sample_record()
    store.upsert_record(record)
    store.upsert_record(record)

    counts = store._connection.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
    evidence_count = store._connection.execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"]
    raw = store._connection.execute(
        "SELECT raw_json FROM records WHERE record_id='MREC-1'"
    ).fetchone()["raw_json"]
    assert counts == 1
    assert evidence_count == 1
    assert json.loads(raw) == record
    assert (
        store._connection.execute("SELECT functional_normalized FROM records").fetchone()[0]
        == "pbe0"
    )
    store.close()


def test_search_returns_source_linked_evidence_and_explicit_mode(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.upsert_record(sample_record())
    response = store.search(
        EvidenceSearchRequest(
            system_description="water molecule", calculation_goal="geometry optimization"
        )
    )

    assert response.retrieval_mode == "lexical_fallback"
    assert response.hits[0].doi == "10.1/example"
    assert response.hits[0].functional == "PBE1PBE"
    assert response.hits[0].evidence[0].page == 4
    store.close()


def test_lexical_search_allows_natural_language_extra_words(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.upsert_record(sample_record())

    response = store.search(
        EvidenceSearchRequest(
            system_description="water unfamiliar molecule",
            calculation_goal="geometry optimization",
        )
    )

    assert response.hits[0].record_id == "MREC-1"
    store.close()


def test_optional_vector_provider_returns_semantic_mode(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3", FakeEmbeddingProvider())
    store.upsert_record(sample_record())
    response = store.search(EvidenceSearchRequest(system_description="water system"))

    assert response.retrieval_mode == "semantic_vector"
    assert response.hits[0].record_id == "MREC-1"
    assert response.hits[0].score == 1.0
    store.close()
