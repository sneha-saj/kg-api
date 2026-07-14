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
            ?programme cmo:contains-music-by ?composer .
            OPTIONAL { ?composer foaf:firstName ?composerFirst }
            OPTIONAL { ?composer foaf:familyName ?composerLast }
        }
    }
}
ORDER BY ?date
"""


def get_concerts(store) -> list[dict]:
    """Returns a list of concerts with venue, programme, and (once the
    pipeline populates cmo:contains-music-by) composer info.
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