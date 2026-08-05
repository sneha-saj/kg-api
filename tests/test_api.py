from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.store import KnowledgeGraphStore

SIMPLE_TTL = b"""
@prefix ex: <http://example.org/> .
ex:a ex:knows ex:b .
"""

CONCERT_TTL = b"""
@prefix cmk: <https://knowledge.semanticscore.net/knowledge/> .
@prefix mo: <http://purl.org/ontology/mo/> .
@prefix schema: <https://schema.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

cmk:c1 a mo:Performance ;
    schema:name "Test Concert" ;
    schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime .
"""


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """TestClient wired to a store backed by a scratch directory, so tests
    never touch the real knowledge/assertions/ data."""
    monkeypatch.setattr(main, "store", KnowledgeGraphStore(tmp_path))
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_upload_rejects_non_ttl_extension(client):
    res = client.post("/upload", files={"file": ("data.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def test_upload_and_query_round_trip(client):
    res = client.post("/upload", files={"file": ("t.ttl", SIMPLE_TTL, "text/turtle")})
    assert res.status_code == 200
    assert res.json() == {"filename": "t.ttl", "status": "loaded", "total_files_loaded": 1}

    res = client.post("/sparql", json={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert res.status_code == 200
    assert len(res.json()["rows"]) == 1


def test_upload_bad_turtle_returns_422(client):
    res = client.post(
        "/upload", files={"file": ("bad.ttl", b"this is not { valid turtle", "text/turtle")}
    )
    assert res.status_code == 422


def test_sparql_get_query_param(client):
    client.post("/upload", files={"file": ("t.ttl", SIMPLE_TTL, "text/turtle")})
    res = client.get("/sparql", params={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert res.status_code == 200
    assert len(res.json()["rows"]) == 1


def test_sparql_get_without_query_param_is_400(client):
    res = client.get("/sparql")
    assert res.status_code == 400


def test_sparql_bad_query_returns_400(client):
    res = client.post("/sparql", json={"query": "NOT VALID SPARQL"})
    assert res.status_code == 400


def test_concerts_endpoint_reflects_uploaded_data(client):
    client.post("/upload", files={"file": ("concerts.ttl", CONCERT_TTL, "text/turtle")})

    res = client.get("/concerts")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Concert"


def test_concerts_endpoint_empty_when_no_data(client):
    res = client.get("/concerts")
    assert res.status_code == 200
    assert res.json() == []


COMPOSER_TTL = b"""
@prefix cmk: <https://knowledge.semanticscore.net/knowledge/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix schema: <https://schema.org/> .

cmk:composer1 a foaf:Person ;
    foaf:firstName "Jean" ; foaf:familyName "Sibelius" ;
    schema:gender schema:Male .
"""


def test_composers_endpoint_reflects_uploaded_data(client):
    client.post("/upload", files={"file": ("composers.ttl", COMPOSER_TTL, "text/turtle")})

    res = client.get("/composers")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "Jean Sibelius"
    assert data[0]["gender"] == ["Male"]


def test_composers_endpoint_empty_when_no_data(client):
    res = client.get("/composers")
    assert res.status_code == 200
    assert res.json() == []
