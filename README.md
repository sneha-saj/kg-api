# kg-api

A small FastAPI server that holds a knowledge graph in memory (via [maplib](https://github.com/DataTreehouse/maplib)) and exposes:

- `GET  /concerts` — shaped JSON: every concert with venue, programme, and full composer profiles
- `GET  /composers` — shaped JSON: every composer with enrichment data (gender, nationality,
  birthplace, birth/death dates, performances)
- `POST /upload` — upload a `.ttl` file (bearer token required), merges it into the graph
- `POST /sparql` — run a SPARQL query, get JSON rows back
- `GET  /sparql?query=...` — same, for quick testing in a browser or Yasgui
- `GET  /health` — basic liveness check

`/concerts` and `/composers` are "shaped" endpoints — fixed SPARQL queries wrapped into
predictable, nested JSON. `/sparql` is the
low-level escape hatch for anything the shaped endpoints don't cover. See
[Shaped endpoints](#shaped-endpoints-concerts--composers) below for exact response shapes.

Every `.ttl` file is loaded into a single shared default graph. An upload
writes the file to `knowledge/assertions/` and then rebuilds the whole in-memory graph from
every `.ttl` on disk, so other files' triples aren't lost — they're just re-read along with it.

## Requirements

- Python 3.10+
- A `maplib` install. The core (mapping, SPARQL query/update, Turtle/N-Triples/RDF-XML I/O) is
  open source and installs with plain `pip install maplib`. SHACL validation and reasoning are
  licensed add-ons — not needed for this API as it stands today.

## Setup

Clone the repo, then from the project root:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Confirm maplib actually works inside the venv (not just installed elsewhere on your machine):

```bash
python3 -c "
from maplib import Model
m = Model()
m.reads('@prefix ex: <http://example.org/> . ex:a ex:knows ex:b .', format='turtle')
print(m.query('SELECT * WHERE { ?s ?p ?o }'))
"
```

You should see a 1-row Polars DataFrame printed. If you get `ModuleNotFoundError: No module named 'maplib'`,
your venv isn't actually active for that shell — see [Troubleshooting](#troubleshooting) below.

## Adding data

Either drop `.ttl` files into `knowledge/assertions/` before starting the server (they're loaded
automatically on startup), or upload them once it's running (see below). The `knowledge/assertions/`
folder is created automatically if it doesn't exist.

## Running

From the project root, with the venv active:

```bash
python3 -m uvicorn app.main:app --reload --workers 1
```

Using `python3 -m uvicorn ...` instead of the bare `uvicorn` command avoids a common gotcha where
your shell's `uvicorn` binary resolves to a different (e.g. globally installed) Python than the one
your venv's `python3` points to, causing `ModuleNotFoundError: No module named 'maplib'` even though
maplib is correctly installed in the venv.

`--workers 1` is required, not optional — the graph is held in a single process's memory. Multiple
workers would each get their own independent copy of the graph, and an upload to one worker wouldn't
be visible from another.

You should see:

```
[startup] loaded N .ttl file(s) from .../knowledge/assertions
INFO:     Uvicorn running on http://127.0.0.1:8000
```

`/upload` is bearer-token protected — without `UPLOAD_TOKEN` set, every upload gets `401` regardless
of what token (if any) you send:

```bash
UPLOAD_TOKEN=dev-token python3 -m uvicorn app.main:app --reload --workers 1
```

`/concerts`, `/composers`, and `/sparql` need no token.

## Trying it out

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Shaped endpoints — no SPARQL needed:

```bash
curl http://127.0.0.1:8000/concerts
curl http://127.0.0.1:8000/composers
```

Upload a file (requires `UPLOAD_TOKEN` to be set when the server starts — see below):

```bash
curl -F "file=@yourfile.ttl" \
  -H "Authorization: Bearer $UPLOAD_TOKEN" \
  http://127.0.0.1:8000/upload
```

Run a query:

```bash
curl -X POST http://127.0.0.1:8000/sparql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"}'
```

Or in a browser, for a quick eyeball check:

```
http://127.0.0.1:8000/sparql?query=SELECT * WHERE { ?s ?p ?o } LIMIT 10
```

## Testing

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

Tests never touch `knowledge/assertions/` — each test gets a `KnowledgeGraphStore` backed by a
fresh scratch directory (pytest's `tmp_path` fixture), so they're isolated and don't require any
real data to be loaded.

- `tests/test_store.py` — unit tests on `KnowledgeGraphStore` (upload, reload-from-disk, re-upload
  replacing only that file's triples, bad Turtle raising).
- `tests/test_resolvers.py` — unit tests on `get_concerts` and `get_composers`, using synthetic
  `.ttl` fixtures that exercise the real predicate variants found in the data (`cmo:has-venue` vs
  `cmo:takes-place-at`, `cmo:has-programme` vs `cmo:hasProgramme`), the composer join
  (`schema:hasPart`/`schema:composer`), and that a concert's composer entries match `/composers`'
  output exactly.
- `tests/test_api.py` — integration tests against the actual HTTP endpoints via FastAPI's
  `TestClient`, with `app.main.store` monkeypatched to a scratch-backed store so nothing depends on
  or mutates real data.

## Shaped endpoints (`/concerts` / `/composers`)

Both are read-only, no query params, no pagination — they return every concert or composer
currently in the graph. Defined in `app/resolvers.py`.

### `GET /concerts`

Array of concert objects:

| Field | Type | Notes |
|---|---|---|
| `id` | `string` | Concert URI |
| `title` | `string \| null` | |
| `date` | `string \| null` | ISO datetime |
| `venue` | `string \| null` | |
| `programme` | `string \| null` | |
| `composers` | `Composer[]` | Full profile per composer — same shape as `/composers` below |

Composers are joined via the raw extraction chain (`schema:hasPart` → `schema:composer`), not
`cmo:featured-at` — that predicate is a time-dependent fact from `xclam-pipeline`'s materialized
inference layer, not part of the assertions this API loads, so it would silently under-report.

```json
{
  "id": "https://knowledge.semanticscore.net/knowledge/musiikkitalo-20230926T1900",
  "title": "Rameau: Les Boréades",
  "date": "2023-09-26T19:00:00+00:00",
  "venue": "Musiikkitalo, Concert Hall",
  "programme": "\"Rameau: Les Boréades\"",
  "composers": [
    {
      "id": "https://knowledge.semanticscore.net/knowledge/jean-philippe-rameau",
      "name": "Jean-Philippe Rameau",
      "gender": ["Male"],
      "nationality": [{ "id": "...", "label": "France" }],
      "birthPlace": [{ "id": "...", "label": "France" }],
      "birthDate": "1683-09-25",
      "deathDate": "1764-09-12",
      "birthYear": null,
      "deathYear": null,
      "featuredAt": [
        { "performance": "...", "title": "...", "date": "..." }
      ]
    }
  ]
}
```

### `GET /composers`

Array of composer objects — the exact shape embedded in `/concerts`:

| Field | Type | Notes |
|---|---|---|
| `id` | `string` | Composer URI |
| `name` | `string \| null` | |
| `gender` | `string[]` | Multi-valued; a clean label (`"Male"`) or, for some KANTO-sourced composers with no label triples, the raw GSSO ontology URI |
| `nationality` | `{id, label}[]` | Multi-valued — a composer can legitimately have more than one |
| `birthPlace` | `{id, label}[]` | Multi-valued |
| `birthDate` / `deathDate` | `string \| null` | Full ISO date, when known precisely |
| `birthYear` / `deathYear` | `string \| null` | Year-only precision (KANTO/FINAF-sourced composers) |
| `featuredAt` | `{performance, title, date}[]` | Every performance this composer is linked to, not just one concert |

Both `/concerts` and `/composers` return the *same* composer dicts (by id) — a composer's profile
is guaranteed identical however you fetched it, so the frontend never needs a second lookup to
render a composer's details from a concert card.

## How to use this from a frontend

Fetching every concert or composer:

```js
const concerts = await fetch("http://127.0.0.1:8000/concerts").then((r) => r.json());
const composers = await fetch("http://127.0.0.1:8000/composers").then((r) => r.json());
```

Uploading a file:

```js
const form = new FormData();
form.append("file", fileInput.files[0]); // must end in .ttl
await fetch("http://127.0.0.1:8000/upload", {
  method: "POST",
  headers: { Authorization: "Bearer " + uploadToken },
  body: form,
});
```

For anything the shaped endpoints don't cover, `/sparql` is the escape hatch — send a SPARQL
query, get JSON rows back:

```js
const res = await fetch("http://127.0.0.1:8000/sparql", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: "SELECT * WHERE { ?s ?p ?o } LIMIT 10" }),
});
const { rows } = await res.json(); // array of plain objects, one per row
```

### Things to know before writing queries

- **CORS is locked to a specific allowlist** in `app/main.py` (`views.semanticscore.net` plus local
  dev ports) — hitting this from a new origin needs that origin added there first.
- **It's a single shared graph**, not scoped per file/session — every uploaded file's triples are
  queryable together, all the time.
- **State is in-memory**, backed by `.ttl` files on disk for persistence across restarts. There's
  no database and no pagination on `/sparql`, `/concerts`, or `/composers` — if you need paging,
  add `LIMIT`/`OFFSET` in your SPARQL yourself, or slice the shaped-endpoint arrays client-side.
- **Errors**: `/sparql` returns `400` with `SPARQL error: ...` on a bad query (syntax error,
  unknown prefix, etc.) — good to surface in dev tooling.

## Troubleshooting

**`ModuleNotFoundError: No module named 'maplib'` when starting uvicorn**
Almost always a PATH mismatch: `which uvicorn` and `which python3` point to different Python
installs. Check:

```bash
which uvicorn
which python3
```

If they don't point into the same `venv/bin/` folder, either re-run `pip install -r requirements.txt`
inside the active venv, or just always launch with `python3 -m uvicorn app.main:app --reload --workers 1`,
which sidesteps the issue by using whichever `python3` the venv resolves to.
