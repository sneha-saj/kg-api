"""
Thin wrapper around a maplib.Model that holds the whole knowledge graph
in memory for the life of the process.

Design note: everything is loaded into the single *default* graph, not
per-file named graphs. Named graphs were tried first but SPARQL only
matches the default graph unless a query explicitly says GRAPH ?g {...} -
a plain `SELECT * WHERE { ?s ?p ?o }` from the frontend would silently
see nothing. At this data scale (a few dozen KB per file, low single
digit MB total) a full reload of every .ttl on every upload is cheap
and avoids that whole class of bug, so that's what this does instead.
"""
import threading
from pathlib import Path

from maplib import Model


class KnowledgeGraphStore:
    """
    Not safe to share across processes (it's in-memory, single process).
    If you run uvicorn with multiple workers, each worker gets its own
    copy of the graph and uploads to one worker won't be visible on
    another — run with --workers 1, or move to a queue/shared store
    later if you need horizontal scale.
    """

    def __init__(self, assertions_dir: Path):
        self.assertions_dir = assertions_dir
        self._model = Model()
        self._lock = threading.Lock()

    def reload_all_from_disk(self) -> int:
        """Rebuild the in-memory graph from scratch by reading every .ttl
        in assertions_dir into the default graph. Called at startup and
        after every upload. Returns number of files loaded."""
        with self._lock:
            self._model = Model()
            count = 0
            for ttl_path in sorted(self.assertions_dir.glob("*.ttl")):
                self._model.read(str(ttl_path))
                count += 1
            return count

    def upload_ttl(self, filename: str, content: bytes) -> int:
        """
        Persist an uploaded .ttl to disk (so a restart doesn't lose it),
        then reload the whole graph so it's reflected immediately.
        Returns the total number of files now loaded.
        """
        dest = self.assertions_dir / filename
        dest.write_bytes(content)
        return self.reload_all_from_disk()

    def query(self, sparql: str):
        """Run a SPARQL query (SELECT/ASK/CONSTRUCT) against the whole model,
        across all named graphs. Returns whatever maplib.query() returns
        (a Polars DataFrame for SELECT)."""
        with self._lock:
            return self._model.query(sparql)