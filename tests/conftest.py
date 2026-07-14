from pathlib import Path

import pytest

from app.store import KnowledgeGraphStore


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeGraphStore:
    """A KnowledgeGraphStore backed by a scratch directory, isolated from
    the real knowledge/assertions/ data."""
    return KnowledgeGraphStore(tmp_path)
