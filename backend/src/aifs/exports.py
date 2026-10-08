"""Stable workspace-relative destinations; DSH owns filesystem export."""

from pathlib import PurePosixPath


def direct_export_path(filename: str) -> str:
    """Content-addressed direct cards each have their own calculation directory."""
    return str(PurePosixPath("aifs-inputs", PurePosixPath(filename).stem, filename))


def saved_export_path(plan_id: str, task_id: str, filename: str) -> str:
    """Immutable identifiers keep paths stable through renames and revisions.

    Plan UUIDs and validated task IDs contain no path separators. Prefixing the
    task ID also avoids Windows reserved directory names such as CON and AUX.
    """
    return str(PurePosixPath("aifs-inputs", f"plan-{plan_id}", f"task-{task_id}", filename))
