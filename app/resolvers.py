"""
Example of a "shaped" endpoint — the GraphQL-resolver equivalent for SPARQL.

Pattern: one function per endpoint. Each function
  1. runs a fixed SPARQL query
  2. gets back flat rows
  3. groups those rows into nested JSON keyed by concert
"""

from datetime import datetime, timezone
from typing import Optional

CONCERT_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX mo: <http://purl.org/ontology/mo/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX schema: <https://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?concert ?title ?date ?venueName ?programmeTitle ?composerFirst ?composerLast
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
        OPTIONAL {
            ?programme schema:hasPart ?composition .
            ?composition schema:composer ?composer .
            OPTIONAL { ?composer foaf:firstName ?composerFirst }
            OPTIONAL { ?composer foaf:familyName ?composerLast }
        }
    }
}
ORDER BY ?date
"""


def get_concerts(store) -> list[dict]:
    """Returns a list of concerts with venue, programme, and composer info
    (composers come from programme_agent.py's schema:hasPart -> MusicComposition
    -> schema:composer chain, not the unused cmo:contains-music-by predicate).
    e.g. [{"id": ..., "title": ..., "date": ..., "venue": ..., "programme": ...,
           "composers": ["Jean Sibelius", ...]}]
    """
    df = store.query(CONCERT_QUERY)
    rows = df.to_dicts()

    concerts: dict[str, dict] = {}
    for row in rows:
        cid = row["concert"]
        if cid not in concerts:
            concerts[cid] = {
                "id": cid,
                "title": row.get("title"),
                "date": row.get("date"),
                "venue": row.get("venueName"),
                "programme": row.get("programmeTitle"),
                "composers": [],
            }

        composer_name = " ".join(
            part for part in (row.get("composerFirst"), row.get("composerLast")) if part
        )
        if composer_name and composer_name not in concerts[cid]["composers"]:
            concerts[cid]["composers"].append(composer_name)

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
    ?composer cmo:featured-at ?performance .
    OPTIONAL { ?performance schema:name ?title }
    OPTIONAL { ?performance schema:startDate ?date }
}
"""

SEARCH_CONCERT_CORE_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX mo: <http://purl.org/ontology/mo/>
PREFIX schema: <https://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT
    ?concert ?title ?date
    ?venue ?venueLabel ?venueSchemaName ?venuePrefLabel
    ?programmeForward ?programmeForwardLabel ?programmeForwardSchemaName ?programmeForwardPrefLabel
    ?programmeReverse ?programmeReverseLabel ?programmeReverseSchemaName ?programmeReversePrefLabel
WHERE {
    ?concert a mo:Performance ;
                     schema:name ?title ;
                     schema:startDate ?date .

    OPTIONAL {
        { ?concert cmo:has-venue ?venue }
        UNION
        { ?concert cmo:takes-place-at ?venue }
        UNION
        { ?concert schema:location ?venue }
        OPTIONAL { ?venue rdfs:label ?venueLabel }
        OPTIONAL { ?venue schema:name ?venueSchemaName }
        OPTIONAL { ?venue skos:prefLabel ?venuePrefLabel }
    }

    OPTIONAL {
        { ?concert cmo:has-programme ?programmeForward }
        UNION
        { ?concert cmo:hasProgramme ?programmeForward }
        OPTIONAL { ?programmeForward rdfs:label ?programmeForwardLabel }
        OPTIONAL { ?programmeForward schema:name ?programmeForwardSchemaName }
        OPTIONAL { ?programmeForward skos:prefLabel ?programmeForwardPrefLabel }
    }

    OPTIONAL {
        ?programmeReverse cmo:is-performed-at ?concert .
        OPTIONAL { ?programmeReverse rdfs:label ?programmeReverseLabel }
        OPTIONAL { ?programmeReverse schema:name ?programmeReverseSchemaName }
        OPTIONAL { ?programmeReverse skos:prefLabel ?programmeReversePrefLabel }
    }
}
ORDER BY ?date
"""

SEARCH_CONCERT_COMPOSER_QUERY = """
PREFIX cmo: <https://knowledge.semanticscore.net/ontology/>
PREFIX mo: <http://purl.org/ontology/mo/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX schema: <https://schema.org/>

SELECT ?concert ?composer ?composerFirst ?composerLast
WHERE {
    ?concert a mo:Performance ;
                     schema:startDate ?date .

    {
        {
            { ?concert cmo:has-programme ?programme }
            UNION
            { ?concert cmo:hasProgramme ?programme }
            UNION
            { ?programme cmo:is-performed-at ?concert }
        }
        {
            {
                ?programme schema:hasPart ?composition .
                ?composition schema:composer ?composer .
            }
            UNION
            {
                ?programme cmo:contains-music-by ?composer .
            }
        }
    }
    UNION
    {
        ?composer cmo:featured-at ?concert .
    }

    OPTIONAL { ?composer foaf:firstName ?composerFirst }
    OPTIONAL { ?composer foaf:familyName ?composerLast }
}
ORDER BY ?date
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


def search_concerts(
    store,
    search_text: Optional[str] = None,
    venue: Optional[str] = None,
    programme: Optional[str] = None,
    composer: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_date: Optional[str] = "2025-09-01",
    limit: int = 250,
    offset: int = 0,
) -> list[dict]:
    """Return concert search results with robust fallback predicate coverage.

    This endpoint is intended for frontend search and keeps filtering logic
    server-side so callers do not need to maintain large SPARQL query strings.
    """
    rows = store.query(SEARCH_CONCERT_CORE_QUERY).to_dicts()
    composer_rows = store.query(SEARCH_CONCERT_COMPOSER_QUERY).to_dicts()

    concerts: dict[str, dict] = {}
    for row in rows:
        cid_raw = row.get("concert")
        if not cid_raw:
            continue

        cid = _clean_uri(cid_raw)
        row_venue = _best_label(
            row.get("venueLabel"),
            row.get("venueSchemaName"),
            row.get("venuePrefLabel"),
            row.get("venue"),
        )
        row_programme = _best_label(
            row.get("programmeForwardLabel"),
            row.get("programmeForwardSchemaName"),
            row.get("programmeForwardPrefLabel"),
            row.get("programmeForward"),
            row.get("programmeReverseLabel"),
            row.get("programmeReverseSchemaName"),
            row.get("programmeReversePrefLabel"),
            row.get("programmeReverse"),
        )

        if cid not in concerts:
            concerts[cid] = {
                "id": cid,
                "title": row.get("title"),
                "date": row.get("date"),
                "venue": row_venue,
                "programme": row_programme,
                "composers": [],
            }
            continue

        # Some result rows for the same concert may miss optional labels.
        # Backfill from later rows when we discover a concrete value.
        if concerts[cid].get("venue") is None and row_venue is not None:
            concerts[cid]["venue"] = row_venue
        if concerts[cid].get("programme") is None and row_programme is not None:
            concerts[cid]["programme"] = row_programme

    composer_map: dict[str, list[dict]] = {}
    for row in composer_rows:
        cid_raw = row.get("concert")
        if not cid_raw:
            continue

        cid = _clean_uri(cid_raw)
        composer_iri = _clean_uri(row.get("composer"))
        composer_name = _composer_name(
            row.get("composerFirst"), row.get("composerLast"), composer_iri
        )
        if not composer_name and not composer_iri:
            continue

        composer_entry = {
            "id": composer_iri,
            "name": composer_name or _iri_tail(composer_iri),
        }
        composer_list = composer_map.setdefault(cid, [])
        if composer_entry not in composer_list:
            composer_list.append(composer_entry)

    for cid, composers in composer_map.items():
        if cid in concerts:
            concerts[cid]["composers"] = composers

    filtered = [concert for concert in concerts.values() if _matches_filters(
        concert=concert,
        search_text=search_text,
        venue=venue,
        programme=programme,
        composer=composer,
        start_date=start_date,
        end_date=end_date,
        min_date=min_date,
    )]

    filtered.sort(key=lambda c: (_sortable_date(c.get("date")) is None, _sortable_date(c.get("date"))))
    safe_offset = max(0, offset)
    safe_limit = max(0, min(limit, 1000))
    if safe_limit == 0:
        return []
    return filtered[safe_offset : safe_offset + safe_limit]


def _best_label(*values):
    for value in values:
        if value is None:
            continue
        cleaned = _clean_literal(_clean_uri(value))
        if isinstance(cleaned, str) and cleaned.strip():
            return cleaned.strip()
    return None


def _iri_tail(value: str) -> str:
    if not value:
        return value
    cleaned = _clean_uri(value)
    tail = cleaned.rstrip("/").split("/")[-1].split("#")[-1]
    return tail or cleaned


def _composer_name(first, last, fallback_iri) -> Optional[str]:
    parts = [part for part in (first, last) if part]
    if parts:
        return " ".join(parts)
    if fallback_iri:
        return _iri_tail(fallback_iri)
    return None


def _sortable_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    text = str(value)
    # maplib dateTime values can use trailing Z, normalize for fromisoformat.
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _matches_filters(
    concert: dict,
    search_text: Optional[str],
    venue: Optional[str],
    programme: Optional[str],
    composer: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    min_date: Optional[str],
) -> bool:
    date_value = _sortable_date(concert.get("date"))

    min_dt = _sortable_date(f"{min_date}T00:00:00") if min_date else None
    start_dt = _sortable_date(f"{start_date}T00:00:00") if start_date else None
    end_dt = _sortable_date(f"{end_date}T23:59:59") if end_date else None

    if min_dt and date_value and date_value < min_dt:
        return False
    if start_dt and date_value and date_value < start_dt:
        return False
    if end_dt and date_value and date_value > end_dt:
        return False

    if venue:
        if (concert.get("venue") or "").strip().lower() != venue.strip().lower():
            return False

    if programme:
        if (concert.get("programme") or "").strip().lower() != programme.strip().lower():
            return False

    if composer:
        composer_target = composer.strip().lower()
        if not any(
            (composer_entry.get("name") or "").strip().lower() == composer_target
            for composer_entry in concert.get("composers", [])
        ):
            return False

    if search_text:
        target = search_text.strip().lower()
        haystack = " ".join(
            [
                str(concert.get("title") or ""),
                str(concert.get("venue") or ""),
                str(concert.get("programme") or ""),
                " ".join(
                    [str(composer_entry.get("name") or "") for composer_entry in concert.get("composers", [])]
                ),
            ]
        ).lower()
        if target not in haystack:
            return False

    return True


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