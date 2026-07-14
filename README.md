# kg-api

A small FastAPI server that holds a knowledge graph in memory (via [maplib](https://github.com/DataTreehouse/maplib)) and exposes:

- `POST /upload` — upload a `.ttl` file, merges it into the graph
- `POST /sparql` — run a SPARQL query, get JSON rows back
- `GET  /sparql?query=...` — same, for quick testing in a browser or Yasgui
- `GET  /health` — basic liveness check

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

## Trying it out

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Upload a file:

```bash
curl -F "file=@yourfile.ttl" http://127.0.0.1:8000/upload
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

## How to use this from a frontend

There's no REST resource model here (no `/entities`, `/nodes`, etc.) — the only way to read data
is by sending a SPARQL query to `/sparql`. Treat this less like a typical CRUD API and more like a
database with one query endpoint.

Uploading a file:

```js
const form = new FormData();
form.append("file", fileInput.files[0]); // must end in .ttl
await fetch("http://127.0.0.1:8000/upload", { method: "POST", body: form });
```

Querying data (the endpoint you'll actually build the app on):

```js
const res = await fetch("http://127.0.0.1:8000/sparql", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: "SELECT * WHERE { ?s ?p ?o } LIMIT 10" }),
});
const { rows } = await res.json(); // array of plain objects, one per row
```

### Things to know before writing queries

- **CORS is wide open** (`allow_origins=["*"]`) in `app/main.py` right now, so you can hit it from
  `localhost` with zero config. That will get locked down to a specific origin before deploying
  anywhere beyond your own machine, so don't hardcode assumptions around it staying open.
- **It's a single shared graph**, not scoped per file/session — every uploaded file's triples are
  queryable together, all the time.
- **State is in-memory**, backed by `.ttl` files on disk for persistence across restarts. There's
  no database, no auth, no pagination on `/sparql` — if you need paging, add `LIMIT`/`OFFSET` in
  your SPARQL yourself.
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
