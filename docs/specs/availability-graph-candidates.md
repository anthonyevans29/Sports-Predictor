# The availability record's graph projection: the embedded candidates (one page)

Lane availability-record, #830, step 5 (due 2026-11-20). ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4, verbatim
in part: "a nightly rebuild of the record into an EMBEDDED graph engine on the host — file-based, no server, Cypher —
[...] Code's first PR for this step is a one-page comparison of the embedded candidates — name, licence, maintenance
state as of the PR's date (that field moved this year; the state is checked, not remembered), Python binding, Cypher
dialect, file format — and I pick on it; nothing is installed before the pick." Addendum 344 item 3 (2026-11-11 17:55
ET) names what the pick will require (identity, the exact pinned wheel and its sha256, a host-only optional install,
the transitive dependencies, the licence as the metadata states it): the second table carries those facts for every
candidate that fits.

**Nothing is installed by this page or its PR.** No dependency, no import, no code. The architect picks; the rebuild
(`availability-graph-rebuild`, due 11-25) follows the pick. This page states no preference.

**How each field was read (law 1), on 2026-11-11.**
- **The package index:** version, upload times, licence, project URLs, Python range, wheels and their sha256, and dependencies come from the Python Package Index's JSON for each package (`https://pypi.org/pypi/<name>/json`, `.../<name>/<version>/json`). That is the index's own record as of the PR's date.
- **Repository pages:** each repository page on github.com was read through a fetch: its archive notice, its install line, its licence statement.
- **LadybugDB's file-format page:** docs.ladybugdb.com was refused by this session's network. Its page "On-disk files managed by Ladybug" was read through the search tool's extract, quoted below.
- **Not read:** a field marked *not read* was not read from a primary record. No package was installed to inspect a file.

**The host the projection runs on:** Ubuntu 24.04 LTS (hosting-h1.md), glibc 2.39, the system Python 3.12. CI and the
laptop also run 3.10; the projection is host-only (252 item 4), so its tests skip where the engine is absent.

| Candidate (PyPI package) | Licence (the package metadata) | Maintenance state, 2026-11-11 | Python binding | Cypher | File format | Fits 252's words? |
|---|---|---|---|---|---|---|
| **Kùzu** (`kuzu`) | `MIT` | **Archived** by its owner on 2025-10-10 (the repository's notice: "This repository was archived by the owner on Oct 10, 2025"). Last release 0.11.3, uploaded 2025-10-10. | Native, in-process (C++ core). Wheels cp38–cp314, manylinux 2.27/2.28 x86_64. | Kùzu's own dialect (openCypher-based; typed schema: `CREATE NODE TABLE`, `REL TABLE`). | One database file from 0.11.0, with `.wal` / `.shadow` / `.tmp` companions (the lineage's file format, LadybugDB's page below; a third-party migration note says the same of Kùzu 0.11.0+). | Yes, but **unmaintained**: no fix ever lands. |
| **LadybugDB** (`ladybug`, import `lbug`) | `MIT` | **Active.** The community fork of Kùzu; its README says "The database was formerly known as Kuzu". Releases 0.22.0 (2026-10-25), 0.22.1 (10-28) and 0.22.3 (11-06), and a 0.23.0 dev build uploaded 2026-11-11. | Native, in-process. Requires Python >=3.10, <3.15. Wheels **cp310–cp314**: manylinux 2.27/2.28 x86_64, manylinux 2.26/2.28 aarch64, musllinux 1.2. | Kùzu's dialect, kept by the fork. | **One file from 0.11.0**. Its documentation, verbatim: "Before version 0.11.0, Ladybug required the database path to be a directory, and created multiple files within that directory." The WAL (`<db>.wal`) is "only created when write transactions are committed in the database and is removed when a checkpoint succeeds"; the shadow file (`<db>.shadow`) is "only created during a checkpoint". Its 0.17.0 notes: a file upgraded to a new storage version cannot be opened by older binaries. | Yes. Maintained. |
| **RyuGraph** (`ryugraph`) | `MIT` | **Quiet.** A fork of Kùzu by Predictable Labs. Releases 25.9.0 (2025-10-24), 25.9.1 (11-16) and 25.9.2 (2025-12-06); **none in the eleven months since**. Its README: "RyuGraph no longer provides the official extension server". | Native, in-process. Wheels cp38–cp312 only. | Kùzu's dialect. | As Kùzu (the lineage's single file). | Yes. Maintenance in doubt (no 2026 release). |
| **CypherLite** (`cypherlite`) | `MIT OR Apache-2.0` | **One day of releases.** Nine releases, 1.2.0 to 2.0.1, all uploaded 2026-03-15 (15:08–19:43Z); none in the eight months since. Its repository (Epsilondelta-ai/CypherLite) shows 63 commits, 2 stars and 0 forks, and no archive notice. | PyO3, in-process; "PyO3-based bindings via `pip install cypherlite`". One abi3 wheel (cp38+), manylinux 2.17 x86_64. | **An openCypher subset**, per its README: "`MATCH`, `CREATE`, `MERGE`, `SET`, `DELETE`, `RETURN`, `WHERE`, `WITH`, `ORDER BY`". | **One `.cyl` file**: "No server process, zero configuration, single `.cyl` file". | Yes on the words: embedded, one file, no server, a Cypher subset. Young: a one-day release history, no adoption shown. |
| **lance-graph** (`lance-graph`) | Classifier: Apache Software License (the metadata's `license` field is empty) | **Young.** 0.5.4 (2026-03-21). | Rust-backed, in-process (`CypherQuery(...).execute(...)`). One abi3 wheel (cp39+), manylinux 2.39 x86_64, 52 MB. An optional FastAPI web service ships beside it. | **A subset** of Cypher, translated to DataFusion SQL. Its README shows `MATCH`, `WHERE`, `RETURN … AS`, `LIMIT`; optional matches and subqueries are "parsed but not executed yet" (its 0.5.0 README). | **Lance datasets, directories on disk.** Its knowledge-graph layer has "Storage helpers that persist node and relationship tables as Lance datasets"; its CLI "writes datasets under `./knowledge_graph_data`". | File-backed and in-process, so it fits. Its drawbacks: partial Cypher, and 64 transitive dependencies (below). |
| **Bighorn** | *not read* | Named as a 2025 fork of Kùzu by one listing (gdb-engines). **No PyPI package of that name**, and no release found. | *not read* | *not read* | *not read* | Not assessable: no installable package. |
| **FalkorDBLite** (`falkordblite`, import `redislite`) | Wrapper: BSD (classifier). **The engine it embeds, FalkorDB, is SSPL v1** (FalkorDB's licence page), which is not OSI-approved. | **Active.** 0.8.0 (2026-02-04) to 0.11.0 (2026-10-19); Beta. | Python >=3.12 only. Wheels cp312–cp314, manylinux 2.38 x86_64. | openCypher (FalkorDB's). | A database file at a path; its description states persistence. | **No: it runs a server.** It "provides a built-in Redis server with FalkorDB module that is automatically installed, configured and managed" (its PyPI description). That is a child process, not in-process. |

**Set aside on 252's words:**
- **Neo4j** and **Memgraph** are servers.
- **DuckDB** 2.0.0 with DuckPGQ uses SQL/PGQ, not Cypher.
- **CozoDB** (`cozo-embedded`) is Datalog, with its last release 2023-12-30.
- **grand-cypher** is Cypher over in-memory NetworkX graphs, with no file format.

## What the pick will require (addendum 344 item 3), for every candidate that fits

| Candidate | (a) Identity: the index's project URLs, and what the repository says back | (b) The version a rebuild would pin, and its host wheel (cp312, manylinux x86_64) with the index's sha256 | (c) Host-only optional install | (d) Transitive dependencies (runtime, Linux, Python 3.12) | (e) Licence, as the metadata states it |
|---|---|---|---|---|---|
| Kùzu | `home_page` and Repository: `https://github.com/kuzudb/kuzu` (archived). | `kuzu==0.11.3`: `kuzu-0.11.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`, sha256 `1bb3b833ca2d1d919423cb3e0150592c2587562ab85259277f622e6f06e0b487` | Yes: one hashed line | **0** (`requires_dist` is empty) | `MIT` |
| LadybugDB | `home_page` `https://github.com/LadybugDB/ladybug`; Repository `https://github.com/LadybugDB/ladybug-python` (both in the LadybugDB organisation). That repository's README names the package: `pip install ladybug`. | `ladybug==0.22.3`: `ladybug-0.22.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`, sha256 `d58f4457ce6fd0bc36656426cd663972429b94c8a9e49e153dd37d04f256b9c4` | Yes: one hashed line | **0** (every `requires_dist` entry is under `extra == "dev"`) | `MIT` |
| RyuGraph | `home_page` and Repository: `https://github.com/predictable-labs/ryugraph`. Its README names no pip package (one direction only). | `ryugraph==25.9.2`: `ryugraph-25.9.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`, sha256 `c410c844f6d5c32c9d2d6f57ce6d3382a578810573607774d7f4f95ef59d3893` | Yes: one hashed line | **0** | `MIT` |
| CypherLite | Homepage and Repository: `https://github.com/Epsilondelta-ai/CypherLite`. Its README names the package: `pip install cypherlite`. | `cypherlite==2.0.1`: `cypherlite-2.0.1-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`, sha256 `4fadaeaf4b73d9c74377f96a2c624ba88a5363845efc3eea443281c3cb552bd2` | Yes: one hashed line | **0** | `MIT OR Apache-2.0` |
| lance-graph | **No project URLs in the index's metadata**; author "Lance Devs <dev@lancedb.com>". The index alone does not tie it to a repository. | `lance-graph==0.5.4`: `lance_graph-0.5.4-cp39-abi3-manylinux_2_39_x86_64.whl`, sha256 `08503a5151ff6321f5e696620c39ae3d5370b5d49ff8562966e763bd93e760ff` | Possible, but `--require-hashes` then needs every one of its 64 dependencies hashed and pinned | **64**: aiohappyeyeballs, aiohttp, aiosignal, annotated-doc, annotated-types, anyio, attrs, certifi, cffi, charset-normalizer, click, cryptography, decorator, fastapi, frozenlist, fsspec, gcsfs, google-api-core, google-auth, google-auth-oauthlib, google-cloud-core, google-cloud-storage, google-cloud-storage-control, google-crc32c, google-resumable-media, googleapis-common-protos, grpc-google-iam-v1, grpcio, h11, httpcore2, httpx2, httpx2-jsfetch, idna, jiter, lance-namespace, lance-namespace-urllib3-client, multidict, numpy, oauthlib, openai, opentelemetry-api, propcache, proto-plus, protobuf, pyarrow, pyasn1, pyasn1-modules, pycparser, pydantic, pydantic-core, pylance, python-dateutil, pyyaml, requests, requests-oauthlib, sniffio, starlette, truststore, typing-extensions, typing-inspection, tzdata, urllib3, uvicorn, yarl | Classifier "Apache Software License"; the `license` field is empty |

**On (c), the mechanics, stated and not built** (nothing is installed before the pick):
- A host-only file of its own (for example `requirements-graph.txt`, never `requirements.txt`) holds one line: `<name>==<version> --hash=sha256:<the index's digest>`.
- It is installed on the host only, by `pip install --require-hashes --only-binary :all: -r <that file>`. pip refuses any distribution whose hash is not listed, so a zero-dependency wheel installs alone.
- The projection's tests skip where the module is absent (`pytest.importorskip`), so the laptop and CI never need it.

**A look-alike, read in passing (344 item 3(a)'s risk):**
- The index also serves `real_ladybug` (0.15.0–0.15.3, 2026-03-01 to 04-01). Its Changelog and Homepage name LadybugDB, but its `home_page` and Repository are `https://github.com/lbugdb/lbug`, which **returns 404**.
- The package LadybugDB's own repository names is `ladybug`.

**What the pick decides, stated without a preference** (the architect's call):
- **Five candidates fit "embedded, file-based, no server, Cypher" as written:**
  - Kùzu, LadybugDB and RyuGraph share one dialect and one storage lineage, each with zero runtime dependencies.
  - CypherLite: a Cypher subset, one file, zero dependencies, one day of releases.
  - lance-graph: a Cypher subset over Lance datasets, 64 dependencies, no repository named in its metadata.
- **Of the five, only LadybugDB has released in the last five months.**
- **FalkorDBLite** is set aside on "no server".

The projection is rebuilt whole from SQLite nightly and is deletable without loss (252 item 4). An engine that dies costs a rebuild on another engine, not data.

Sources (read 2026-11-11):
- PyPI JSON: [kuzu](https://pypi.org/pypi/kuzu/json), [ladybug](https://pypi.org/pypi/ladybug/json), [ladybug 0.22.3](https://pypi.org/pypi/ladybug/0.22.3/json), [real_ladybug](https://pypi.org/pypi/real_ladybug/json), [ryugraph](https://pypi.org/pypi/ryugraph/json), [cypherlite](https://pypi.org/pypi/cypherlite/json), [lance-graph](https://pypi.org/pypi/lance-graph/json), [falkordblite](https://pypi.org/pypi/falkordblite/json), [duckdb](https://pypi.org/pypi/duckdb/json), [cozo-embedded](https://pypi.org/pypi/cozo-embedded/json), [grand-cypher](https://pypi.org/pypi/grand-cypher/json).
- Repositories: [kuzudb/kuzu](https://github.com/kuzudb/kuzu), [LadybugDB/ladybug](https://github.com/LadybugDB/ladybug), [LadybugDB/ladybug-python](https://github.com/LadybugDB/ladybug-python), [predictable-labs/ryugraph](https://github.com/predictable-labs/ryugraph), [Epsilondelta-ai/CypherLite](https://github.com/Epsilondelta-ai/CypherLite), [lance-format/lance-graph](https://github.com/lance-format/lance-graph), [FalkorDB/falkordblite](https://github.com/FalkorDB/falkordblite); `https://github.com/lbugdb/lbug` (404).
- Documentation: [LadybugDB, on-disk files](https://docs.ladybugdb.com/developer-guide/files/), read through the search tool's extract (this session's network refuses the domain); [LadybugDB v0.17.0 notes](https://blog.ladybugdb.com/post/graph-lake-icebug-format/); [FalkorDB licence](https://docs.falkordb.com/references/license); [lance-graph 0.5.0 README](https://docs.rs/crate/lance-graph/0.5.0/source/README.md).
- Secondary: [gdb-engines: Kùzu](https://gdb-engines.com/db/kuzu/) (Bighorn named); [a Kùzu-to-LadybugDB migration note](https://oneuptime.com/blog/post/2026-08-12-kuzu-to-ladybugdb-packages-apis-extensions-database-files/view).
