from app.resolvers import get_concerts

PREFIXES = """
@prefix cmo: <https://knowledge.semanticscore.net/ontology/> .
@prefix cmk: <https://knowledge.semanticscore.net/knowledge/> .
@prefix mo: <http://purl.org/ontology/mo/> .
@prefix schema: <https://schema.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def upload(store, ttl_body: str, name: str = "t.ttl"):
    store.upload_ttl(name, (PREFIXES + ttl_body).encode())


def test_basic_fields_with_no_venue_or_programme(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "Test Concert" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime .
    """)

    concerts = get_concerts(store)
    assert len(concerts) == 1
    assert concerts[0]["title"] == "Test Concert"
    assert concerts[0]["venue"] is None
    assert concerts[0]["programme"] is None
    assert concerts[0]["composers"] == []


def test_venue_via_has_venue_predicate(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-venue cmk:v1 .
    cmk:v1 rdfs:label "Venue One" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["venue"] == "Venue One"


def test_venue_via_takes_place_at_predicate(store):
    """Some source feeds (e.g. Hebo) use cmo:takes-place-at instead of
    cmo:has-venue -- the query must union both."""
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:takes-place-at cmk:v1 .
    cmk:v1 rdfs:label "Venue One" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["venue"] == "Venue One"


def test_programme_via_lowercase_predicate(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-programme cmk:p1 .
    cmk:p1 rdfs:label "Programme One" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["programme"] == "Programme One"


def test_programme_via_camel_case_predicate(store):
    """One source feed (Kemi) emits cmo:hasProgramme instead of
    cmo:has-programme -- the query must union both."""
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:hasProgramme cmk:p1 .
    cmk:p1 rdfs:label "Programme One" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["programme"] == "Programme One"


def test_programme_without_label_leaves_programme_field_null(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-programme cmk:p1 .
    cmk:p1 a cmo:Programme .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["programme"] is None


def test_composer_populates_via_composition(store):
    """Composers come from programme_agent.py's schema:hasPart ->
    MusicComposition -> schema:composer chain, not cmo:contains-music-by
    (declared in the ontology but never emitted by the pipeline)."""
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-programme cmk:p1 .
    cmk:p1 rdfs:label "Programme One" ;
        schema:hasPart cmk:work1 .
    cmk:work1 a schema:MusicComposition ;
        schema:name "Symphony No. 2" ;
        schema:composer cmk:composer1 .
    cmk:composer1 foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["composers"] == ["Jean Sibelius"]


def test_composer_deduplicated_across_rows(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-programme cmk:p1, cmk:p2 .
    cmk:p1 schema:hasPart cmk:work1 .
    cmk:p2 schema:hasPart cmk:work2 .
    cmk:work1 schema:composer cmk:composer1 .
    cmk:work2 schema:composer cmk:composer1 .
    cmk:composer1 foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["composers"] == ["Jean Sibelius"]


def test_multiple_concerts_ordered_by_date(store):
    upload(store, """
    cmk:c2 a mo:Performance ;
        schema:name "Second" ;
        schema:startDate "2026-02-01T19:00:00"^^xsd:dateTime .
    cmk:c1 a mo:Performance ;
        schema:name "First" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime .
    """)

    concerts = get_concerts(store)
    assert [c["title"] for c in concerts] == ["First", "Second"]


def test_no_data_returns_empty_list(store):
    assert get_concerts(store) == []
