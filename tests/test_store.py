import pytest

SIMPLE_TTL = b"""
@prefix ex: <http://example.org/> .
ex:a ex:knows ex:b .
"""

OTHER_TTL = b"""
@prefix ex: <http://example.org/> .
ex:c ex:knows ex:d .
"""


def test_reload_all_from_disk_starts_empty(store):
    assert store.reload_all_from_disk() == 0
    df = store.query("SELECT * WHERE { ?s ?p ?o }")
    assert len(df) == 0


def test_upload_ttl_loads_into_graph(store):
    total_files = store.upload_ttl("a.ttl", SIMPLE_TTL)
    assert total_files == 1

    df = store.query("SELECT * WHERE { ?s ?p ?o }")
    assert len(df) == 1


def test_upload_ttl_persists_to_disk(store, tmp_path):
    store.upload_ttl("a.ttl", SIMPLE_TTL)
    assert (tmp_path / "a.ttl").read_bytes() == SIMPLE_TTL


def test_reupload_replaces_only_that_files_triples(store):
    store.upload_ttl("a.ttl", SIMPLE_TTL)
    store.upload_ttl("b.ttl", OTHER_TTL)

    new_a = b"""
    @prefix ex: <http://example.org/> .
    ex:x ex:knows ex:y .
    """
    total_files = store.upload_ttl("a.ttl", new_a)

    assert total_files == 2  # still just a.ttl and b.ttl on disk
    df = store.query("SELECT ?s WHERE { ?s ?p ?o }")
    subjects = {row["s"] for row in df.to_dicts()}

    assert "<http://example.org/x>" in subjects  # new a.ttl content present
    assert "<http://example.org/a>" not in subjects  # old a.ttl content gone
    assert "<http://example.org/c>" in subjects  # b.ttl untouched


def test_upload_bad_turtle_raises(store):
    with pytest.raises(Exception):
        store.upload_ttl("bad.ttl", b"this is not { valid turtle at all")
