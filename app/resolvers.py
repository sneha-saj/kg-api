"""
Example of a "shaped" endpoint — the GraphQL-resolver equivalent for SPARQL.

Pattern: one function per endpoint. Each function
  1. runs a fixed SPARQL query
  2. gets back flat rows
  3. groups those rows into nested JSON keyed by concert
"""

CONCERT_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX mo: <http://purl.org/ontology/mo/>
PREFIX schema: <https://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?concert ?title ?date ?venueName ?programmeTitle
WHERE {
    ?concert a mo:Performance ;
             schema:name ?title ;
             schema:startDate ?date .

    OPTIONAL {
        { ?concert cmo:has-venue ?venue } UNION { ?concert cmo:takes-place-at ?venue }
        OPTIONAL { ?venue rdfs:label ?venueName }
    }

    OPTIONAL {
        { ?concert cmo:has-programme ?programme } UNION { ?concert cmo:hasProgramme ?programme }
        OPTIONAL { ?programme rdfs:label ?programmeTitle }
    }
}
ORDER BY ?date
"""

CONCERT_COMPOSER_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX schema: <https://schema.org/>

SELECT ?concert ?composer ?composerFirst ?composerLast
WHERE {
    { ?concert cmo:has-programme ?programme } UNION { ?concert cmo:hasProgramme ?programme }
    ?programme schema:hasPart ?work .
    ?work schema:composer ?composer .
    OPTIONAL { ?composer foaf:firstName ?composerFirst }
    OPTIONAL { ?composer foaf:familyName ?composerLast }
}
"""


def get_concerts(store) -> list[dict]:
    """Returns a list of concerts with venue, programme, and composer info.
    e.g. [{"id": ..., "title": ..., "date": ..., "venue": ..., "programme": ...,
           "composers": [<full composer profile>, ...]}]

    Each concert's composers carry the *same* profile fields as get_composers()
    (gender, nationality, birthPlace, birth/death dates or year, featuredAt) --
    literally the same dicts, keyed by composer id, so a composer's data is
    identical whether read via /concerts or /composers and the frontend never
    needs a second lookup to render a concert card. A composer joined here but
    missing from get_composers() (not typed foaf:Person -- shouldn't happen for
    registry composers, see composers.ttl) falls back to just id/name with
    empty/null enrichment fields rather than being dropped.

    Composers are joined via the raw schema:hasPart/schema:composer extraction
    chain, not cmo:features -- that predicate is a time-dependent
    materialized-inference-layer fact (see get_composers' FEATURED_AT_QUERY and
    knowledge/rules/composer-featured-at.sparql in xclam-pipeline), so it can
    silently omit composers for concerts outside whatever window it was last
    generated for.
    """
    composer_index = {c["id"]: c for c in get_composers(store)}

    concerts: dict[str, dict] = {}
    for row in store.query(CONCERT_QUERY).to_dicts():
        concert_id = _clean_uri(row["concert"])
        concerts[concert_id] = {
            "id": concert_id,
            "title": row.get("title"),
            "date": row.get("date"),
            "venue": row.get("venueName"),
            "programme": row.get("programmeTitle"),
            "composers": [],
        }

    for row in store.query(CONCERT_COMPOSER_QUERY).to_dicts():
        entry = concerts.get(_clean_uri(row["concert"]))
        if entry is None:
            continue
        composer_id = _clean_uri(row["composer"])
        composer = composer_index.get(composer_id)
        if composer is None:
            composer_name = " ".join(
                part for part in (row.get("composerFirst"), row.get("composerLast")) if part
            ) or None
            composer = {
                "id": composer_id,
                "name": composer_name,
                "gender": [],
                "nationality": [],
                "birthPlace": [],
                "birthDate": None,
                "deathDate": None,
                "birthYear": None,
                "deathYear": None,
                "featuredAt": [],
            }
        if composer not in entry["composers"]:
            entry["composers"].append(composer)

    return list(concerts.values())


COMPOSER_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX schema: <https://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?composer ?first ?last ?gender ?birthDate ?deathDate ?birthYear ?deathYear
WHERE {
    ?composer a foaf:Person .
    OPTIONAL { ?composer foaf:firstName ?first }
    OPTIONAL { ?composer foaf:familyName ?last }
    OPTIONAL { ?composer schema:gender ?gender }
    OPTIONAL { ?composer schema:birthDate ?birthDate }
    OPTIONAL { ?composer schema:deathDate ?deathDate }
    OPTIONAL { ?composer cmo:birthYear ?birthYear }
    OPTIONAL { ?composer cmo:deathYear ?deathYear }
}
"""

NATIONALITY_QUERY = """
PREFIX schema: <https://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?composer ?nationality ?label
WHERE {
    ?composer schema:nationality ?nationality .
    OPTIONAL { ?nationality skos:prefLabel ?label }
}
"""

BIRTHPLACE_QUERY = """
PREFIX schema: <https://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?composer ?birthPlace ?label
WHERE {
    ?composer schema:birthPlace ?birthPlace .
    OPTIONAL { ?birthPlace skos:prefLabel ?label }
}
"""

FEATURED_AT_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX schema: <https://schema.org/>

SELECT ?composer ?performance ?title ?date
WHERE {
    ?performance cmo:features ?composer .
    OPTIONAL { ?performance schema:name ?title }
    OPTIONAL { ?performance schema:startDate ?date }
}
"""


def _clean_uri(value):
    """maplib returns URI columns as their raw N-Triples form, e.g.
    "<https://knowledge.semanticscore.net/knowledge/finland>" -- strip the
    angle brackets so callers get a plain, usable URI string."""
    if isinstance(value, str) and value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    return value


def _clean_literal(value):
    """maplib returns plain (untagged, undatatyped) literals already
    unwrapped, but a language-tagged literal like skos:prefLabel comes back
    as its raw N-Triples form, e.g. '"Finland"@en' -- strip the quotes and
    tag so callers get a plain string."""
    if isinstance(value, str) and value.startswith('"'):
        return value[1:value.rindex('"')]
    return value


def _gender_label(uri: str) -> str:
    """schema:gender values are either schema.org's own Male/Female
    individuals or, for KANTO-sourced composers, a GSSO ontology concept with
    no label triples in our data -- fall back to the raw URI for those."""
    uri = _clean_uri(uri)
    if uri.startswith("https://schema.org/"):
        return uri.rsplit("/", 1)[-1]
    return uri


def get_composers(store) -> list[dict]:
    """Returns every composer with their enrichment attributes (gender,
    nationality, birthplace, birth/death dates or year-only precision) and
    the performances they're featured at (from the materialized inference
    layer). Multi-valued fields (gender, nationality, birthPlace, featuredAt)
    are lists; a composer can legitimately have more than one nationality
    (see FIXES.md's Bernhard Crusell / historical-borders note).
    """
    composers: dict[str, dict] = {}

    def _ensure(cid: str) -> dict:
        if cid not in composers:
            composers[cid] = {
                "id": cid,
                "name": None,
                "gender": [],
                "nationality": [],
                "birthPlace": [],
                "birthDate": None,
                "deathDate": None,
                "birthYear": None,
                "deathYear": None,
                "featuredAt": [],
            }
        return composers[cid]

    for row in store.query(COMPOSER_QUERY).to_dicts():
        entry = _ensure(_clean_uri(row["composer"]))
        entry["name"] = " ".join(
            part for part in (row.get("first"), row.get("last")) if part
        ) or None
        entry["birthDate"] = row.get("birthDate") or entry["birthDate"]
        entry["deathDate"] = row.get("deathDate") or entry["deathDate"]
        entry["birthYear"] = row.get("birthYear") or entry["birthYear"]
        entry["deathYear"] = row.get("deathYear") or entry["deathYear"]
        gender = row.get("gender")
        if gender:
            label = _gender_label(gender)
            if label not in entry["gender"]:
                entry["gender"].append(label)

    for row in store.query(NATIONALITY_QUERY).to_dicts():
        entry = _ensure(_clean_uri(row["composer"]))
        value = {"id": _clean_uri(row["nationality"]), "label": _clean_literal(row.get("label"))}
        if value not in entry["nationality"]:
            entry["nationality"].append(value)

    for row in store.query(BIRTHPLACE_QUERY).to_dicts():
        entry = _ensure(_clean_uri(row["composer"]))
        value = {"id": _clean_uri(row["birthPlace"]), "label": _clean_literal(row.get("label"))}
        if value not in entry["birthPlace"]:
            entry["birthPlace"].append(value)

    for row in store.query(FEATURED_AT_QUERY).to_dicts():
        entry = _ensure(_clean_uri(row["composer"]))
        entry["featuredAt"].append({
            "performance": _clean_uri(row["performance"]),
            "title": row.get("title"),
            "date": row.get("date"),
        })

    return list(composers.values())


# --- Filtering safely ---
# Don't string-format user input directly into a SPARQL query (injection risk,
# same category of bug as SQL injection). maplib's query() supports a
# `parameters` argument for VALUES-style parameter binding, which is the
# safe way to filter by, say, a specific org or year:
#
#   store.query(CONCERT_QUERY_WITH_VAR, parameters=...)
#
# Check maplib's docs/examples for the exact parameters= usage before
# wiring up a filtered endpoint like /concerts?org=RSO.