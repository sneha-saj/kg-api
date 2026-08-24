from app.resolvers import get_composers, get_concerts

PREFIXES = """
@prefix cmo: <https://knowledge.semanticscore.net/ontology/> .
@prefix cmk: <https://knowledge.semanticscore.net/knowledge/> .
@prefix mo: <http://purl.org/ontology/mo/> .
@prefix schema: <https://schema.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
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
    assert concerts[0]["organizer"] is None
    assert concerts[0]["programme"] is None
    assert concerts[0]["composers"] == []


def test_organizer(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        schema:organizer cmk:org1 .
    cmk:org1 a schema:Organization ;
        schema:name "Avanti! kamariorkesteri" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["organizer"] == {
        "id": "https://knowledge.semanticscore.net/knowledge/org1",
        "name": "Avanti! kamariorkesteri",
    }


def test_organizer_without_name_still_returns_id(store):
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        schema:organizer cmk:org1 .
    cmk:org1 a schema:Organization .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["organizer"] == {
        "id": "https://knowledge.semanticscore.net/knowledge/org1",
        "name": None,
    }


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


MINIMAL_COMPOSER_PROFILE = {
    "gender": [],
    "nationality": [],
    "birthPlace": [],
    "birthDate": None,
    "deathDate": None,
    "birthYear": None,
    "deathYear": None,
    "featuredAt": [],
}


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
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["composers"] == [
        {
            "id": "https://knowledge.semanticscore.net/knowledge/composer1",
            "name": "Jean Sibelius",
            **MINIMAL_COMPOSER_PROFILE,
        }
    ]


def test_composer_via_camel_case_programme_predicate(store):
    """Kemi's cmo:hasProgramme feed must also join composers, same as it
    does for the programme label itself."""
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:hasProgramme cmk:p1 .
    cmk:p1 schema:hasPart cmk:work1 .
    cmk:work1 schema:composer cmk:composer1 .
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["composers"] == [
        {
            "id": "https://knowledge.semanticscore.net/knowledge/composer1",
            "name": "Jean Sibelius",
            **MINIMAL_COMPOSER_PROFILE,
        }
    ]


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
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    """)

    concerts = get_concerts(store)
    assert concerts[0]["composers"] == [
        {
            "id": "https://knowledge.semanticscore.net/knowledge/composer1",
            "name": "Jean Sibelius",
            **MINIMAL_COMPOSER_PROFILE,
        }
    ]


def test_concert_composer_carries_full_enrichment_profile(store):
    """/concerts composer entries must carry the same enrichment fields as
    /composers (gender, nationality, birth/death info, ...), not just
    id/name -- so the frontend can render a concert card without a second
    /composers lookup."""
    upload(store, """
    cmk:c1 a mo:Performance ;
        schema:name "C1" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:has-programme cmk:p1 .
    cmk:p1 schema:hasPart cmk:work1 .
    cmk:work1 schema:composer cmk:composer1 .
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" ;
        schema:gender schema:Male ;
        schema:nationality cmk:finland ;
        schema:birthDate "1865-12-08"^^xsd:date ;
        schema:deathDate "1957-09-20"^^xsd:date .
    cmk:finland skos:prefLabel "Finland"@en .
    """)

    concerts = get_concerts(store)
    composer = concerts[0]["composers"][0]
    assert composer["id"] == "https://knowledge.semanticscore.net/knowledge/composer1"
    assert composer["name"] == "Jean Sibelius"
    assert "Male" in composer["gender"]
    assert composer["nationality"] == [
        {"id": "https://knowledge.semanticscore.net/knowledge/finland", "label": "Finland"}
    ]
    import datetime

    assert composer["birthDate"] == datetime.date(1865, 12, 8)
    assert composer["deathDate"] == datetime.date(1957, 9, 20)

    # Same dict a direct /composers call would return for this composer.
    composers = get_composers(store)
    assert composer == composers[0]


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


def test_composer_basic_fields(store):
    """birthDate/deathDate come back as native date objects, same as
    get_concerts' ?date column -- FastAPI serializes them to ISO strings at
    the HTTP boundary (see test_composers_endpoint_reflects_uploaded_data)."""
    import datetime

    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" ;
        schema:birthDate "1865-12-08"^^xsd:date ;
        schema:deathDate "1957-09-20"^^xsd:date .
    """)

    composers = get_composers(store)
    assert len(composers) == 1
    assert composers[0]["name"] == "Jean Sibelius"
    assert composers[0]["birthDate"] == datetime.date(1865, 12, 8)
    assert composers[0]["deathDate"] == datetime.date(1957, 9, 20)
    assert composers[0]["nationality"] == []
    assert composers[0]["featuredAt"] == []


def test_composer_year_only_precision(store):
    """KANTO/FINAF-sourced composers may only have year precision -- see
    cmo:birthYear/deathYear in source-ontology.ttl."""
    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Antti" ; foaf:familyName "Auvinen" ;
        cmo:birthYear "1974"^^xsd:gYear .
    """)

    composers = get_composers(store)
    assert composers[0]["birthYear"] == "1974"
    assert composers[0]["birthDate"] is None


def test_composer_gender_prefers_schema_org_label(store):
    """schema:gender can carry both a schema.org individual (labelled) and a
    GSSO ontology concept (no label in our data) for the same composer."""
    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" ;
        schema:gender schema:Male, <http://purl.obolibrary.org/obo/GSSO_000090> .
    """)

    composers = get_composers(store)
    assert "Male" in composers[0]["gender"]
    assert "http://purl.obolibrary.org/obo/GSSO_000090" in composers[0]["gender"]


def test_composer_nationality_and_birthplace_with_labels(store):
    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" ;
        schema:nationality cmk:finland ;
        schema:birthPlace cmk:finland .
    cmk:finland skos:prefLabel "Finland"@en .
    """)

    composers = get_composers(store)
    assert composers[0]["nationality"] == [{"id": "https://knowledge.semanticscore.net/knowledge/finland", "label": "Finland"}]
    assert composers[0]["birthPlace"] == [{"id": "https://knowledge.semanticscore.net/knowledge/finland", "label": "Finland"}]


def test_composer_multiple_nationalities_not_deduplicated_away(store):
    """A composer born under a since-dissolved polity can legitimately carry
    more than one schema:nationality (see FIXES.md's Crusell note)."""
    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Bernhard" ; foaf:familyName "Crusell" ;
        schema:nationality cmk:finland, cmk:grand-duchy-of-finland .
    """)

    composers = get_composers(store)
    assert len(composers[0]["nationality"]) == 2


def test_composer_featured_at_performance(store):
    """cmo:features is a materialized inference-layer fact, not raw
    extracted data -- see knowledge/rules/composer-featured-at.sparql."""
    upload(store, """
    cmk:composer1 a foaf:Person ;
        foaf:firstName "Jean" ; foaf:familyName "Sibelius" .
    cmk:concert1 schema:name "Sibelius Night" ;
        schema:startDate "2026-01-01T19:00:00"^^xsd:dateTime ;
        cmo:features cmk:composer1 .
    """)

    composers = get_composers(store)
    assert len(composers[0]["featuredAt"]) == 1
    featured = composers[0]["featuredAt"][0]
    assert featured["performance"] == "https://knowledge.semanticscore.net/knowledge/concert1"
    assert featured["title"] == "Sibelius Night"
    assert featured["date"].isoformat() == "2026-01-01T19:00:00+00:00"


def test_composers_no_data_returns_empty_list(store):
    assert get_composers(store) == []
