"""Contract drift is a build failure, not a runtime model surprise."""

import json
from pathlib import Path

import pytest

from aifs.contracts import contract_artifacts, project_schema, synchronize


def test_shipped_contracts_match_python_without_writing():
    root = Path(__file__).resolve().parents[2]
    before = {path: (root / path).read_bytes() for path in contract_artifacts()}
    synchronize(root, check=True)
    assert before == {path: (root / path).read_bytes() for path in before}


def test_check_detects_drift_and_does_not_repair_it(tmp_path):
    synchronize(tmp_path, check=False)
    path = tmp_path / "contracts/backend-schema.json"
    data = json.loads(path.read_text())
    data["models"]["PlanDraft"]["properties"]["goal"]["enum"].append("invented_goal")
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="out of date"):
        synchronize(tmp_path, check=True)
    assert path.read_bytes() == before


def test_projection_preserves_required_nullable_and_enums():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["goal"],
        "properties": {
            "goal": {"type": "string", "enum": ["other"]},
            "basis": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    }
    projected = project_schema(schema)
    assert projected["properties"]["goal"] == {
        "type": "string",
        "enum": ["other"],
        "required": True,
    }
    assert projected["properties"]["basis"]["oneOf"][1] == {"type": "null"}
    assert "required" not in projected["properties"]["basis"]


def test_projection_refuses_ambiguous_union_instead_of_weakening_schema():
    with pytest.raises(ValueError, match="union"):
        project_schema({"anyOf": [{"type": "number"}, {"type": "integer"}]})
