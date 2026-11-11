# The availability record's graph projection: the embedded candidates (one page)

Lane availability-record, #830, step 5 (due 2026-11-20). ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 4, verbatim
in part: "a nightly rebuild of the record into an EMBEDDED graph engine on the host — file-based, no server, Cypher —
[...] Code's first PR for this step is a one-page comparison of the embedded candidates — name, licence, maintenance
state as of the PR's date (that field moved this year; the state is checked, not remembered), Python binding, Cypher
dialect, file format — and I pick on it; nothing is installed before the pick."

**Nothing is installed by this page or its PR.** No dependency, no import, no code. The architect picks; the rebuild
(`availability-graph-rebuild`, due 11-25) follows the pick.

**How each field was read (law 1), on 2026-11-11.** Maintenance state, licence, version, Python range and wheels come
from the Python Package Index's own JSON for each package (`https://pypi.org/pypi/<name>/json`): its upload times and
classifiers, as of the PR's date. Repository states (archived, fork lineage) come from the project pages the search
returned, named under Sources. A field marked *not read* was not read from a primary record in this session. The
session's network refused the projects' own sites, and no package was installed to inspect a file.

**The host the projection runs on:** Ubuntu 24.04 LTS (hosting-h1.md), glibc 2.39, the system Python 3.12. CI and the
laptop run 3.10 as well; the projection is host-only (252 item 4), so its tests must still import on 3.10 or skip there.

| Candidate (PyPI package) | Licence | Maintenance state, 2026-11-11 | Python binding | Cypher | File format | Fits 252's words? |
|---|---|---|---|---|---|---|
| **Kùzu** (`kuzu`) | MIT | **Archived** by its owner on 2025-10-10 (repository read-only). Last release 0.11.3, uploaded 2025-10-10; no release since. | Native, in-process (C++ core). Wheels cp38-cp314, manylinux 2.27/2.28 x86_64. | Kùzu's own Cypher dialect (openCypher-based, strongly typed schema: `CREATE NODE TABLE`, `REL TABLE`). | On-disk database at a path, columnar storage. The exact layout (one file or a directory) was *not read* here. | Embedded, file-based, Cypher: yes. **Unmaintained**: no fix ever lands. |
| **LadybugDB** (`ladybug`, import `lbug`) | MIT | **Active.** Community fork of Kùzu, described by the search's sources as Kùzu's main continuation. Releases 0.22.0 (2026-10-25), 0.22.1 (10-28), 0.22.3 (11-06); a 0.23.0 dev build uploaded 2026-11-11. An earlier package name, `real_ladybug`, stopped at 0.15.3 (2026-04-01). | Native, in-process. Requires Python >=3.10, <3.15. Wheels cp310-cp313, manylinux 2.27/2.28 and musllinux x86_64. | Kùzu's dialect, kept by the fork. | On-disk at a path (`.lbdb` / `.lbug` in its docs' examples), columnar. One file or a directory is *not settled* by the sources read. | Embedded, file-based, Cypher: yes. Maintained. |
| **RyuGraph** (`ryugraph`) | MIT | **Quiet.** Fork of Kùzu by Predictable Labs. Releases 25.9.0 (2025-10-24), 25.9.1 (11-16), 25.9.2 (2025-12-06); **no release in the eleven months since**. It no longer runs Kùzu's extension server (its own page). | Native, in-process. Wheels cp38-cp312 only (none for 3.13+). | Kùzu's dialect. | As Kùzu (on-disk at a path). | Embedded, file-based, Cypher: yes. Maintenance in doubt (no 2026 release). |
| **Bighorn** | *not read* | Named as a 2025 fork of Kùzu by one listing (gdb-engines). **No PyPI package of that name**, and no release was found. | *not read* | Kùzu's, presumably (*not read*) | *not read* | Not assessable: no installable package found. |
| **FalkorDBLite** (`falkordblite`, import `redislite`) | Wrapper: BSD. **The FalkorDB engine it embeds is SSPL v1** (FalkorDB's licence page), which is not OSI-approved. | **Active.** 0.8.0 (2026-02-04) to 0.11.0 (2026-10-19); Beta. | Python package only. Requires Python **>=3.12**: it **does not import on the laptop's or CI's 3.10**. Wheels cp312-cp314, manylinux **2.38** x86_64 (the host's glibc 2.39 meets it). | openCypher (FalkorDB's). | A database file at a path; persistence is stated by its package description. | **Not "no server"**: it "provides a built-in Redis server with FalkorDB module that is automatically installed, configured and managed" (its PyPI description), a child process, not in-process. Licence and Python floor also differ. |
| **lance-graph** (`lance-graph`) | Apache-2.0 | **Young.** 0.5.4 (2026-03-21); its README calls optional matches and subqueries "parsed but not executed yet". | Rust-backed, in-process; Python >=3.9; one abi3 wheel, manylinux 2.39 x86_64 (52 MB). | A **subset** of Cypher, translated to DataFusion SQL over Lance or Arrow tables. | Lance datasets: a directory of columnar files. | In-process and Cypher-shaped, but **not a graph store**: it queries tables you hand it, and its Cypher is partial. |

**Considered and set aside on 252's own words (no row above):**
- **Neo4j** and **Memgraph** are servers.
- **DuckDB** 2.0.0 with DuckPGQ is embedded, but its graph language is SQL/PGQ, not Cypher.
- **CozoDB** (`cozo-embedded`) is Datalog, not Cypher, and its last release was 2023-12-30.
- **grand-cypher** is Cypher over in-memory NetworkX graphs, with no file format.

**What the pick decides, stated without a preference (the architect's call):**
- Three candidates meet "embedded, file-based, no server, Cypher" as written: Kùzu, LadybugDB and RyuGraph, all one dialect and one storage lineage. Of the three, only LadybugDB released in the last five months; Kùzu is archived and RyuGraph's last release is 2025-12-06.
- FalkorDBLite is maintained but runs a server process, carries the SSPL on its engine, and needs Python 3.12.
- lance-graph is in-process but partial Cypher over tables, not a store.

The projection is rebuilt whole from SQLite nightly and deletable without loss (252 item 4), so an engine that dies costs a rebuild on another, not data.

Sources (read 2026-11-11):
- PyPI JSON: [kuzu](https://pypi.org/pypi/kuzu/json), [ladybug](https://pypi.org/pypi/ladybug/json), [real_ladybug](https://pypi.org/pypi/real_ladybug/json), [ryugraph](https://pypi.org/pypi/ryugraph/json), [falkordblite](https://pypi.org/pypi/falkordblite/json), [lance-graph](https://pypi.org/pypi/lance-graph/json), [duckdb](https://pypi.org/pypi/duckdb/json), [cozo-embedded](https://pypi.org/pypi/cozo-embedded/json), [grand-cypher](https://pypi.org/pypi/grand-cypher/json).
- Kùzu's archive date and successors: [kuzudb/kuzu](https://github.com/kuzudb/kuzu), [FalkorDB's Kùzu migration note](https://www.falkordb.com/blog/kuzudb-to-falkordb-migration/), [gdotv: Kùzu's legacy](https://gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape/), [gdb-engines: Kùzu](https://gdb-engines.com/db/kuzu/), [gdb-engines: LadybugDB](https://gdb-engines.com/db/ladybugdb/).
- RyuGraph: [predictable-labs/ryugraph](https://github.com/predictable-labs/ryugraph), [ryugraph.io](https://www.ryugraph.io/).
- LadybugDB: [docs.ladybugdb.com](https://docs.ladybugdb.com/get-started), [lbug on docs.rs](https://docs.rs/crate/lbug/0.15.4).
- FalkorDB: [falkordblite](https://github.com/FalkorDB/falkordblite), [FalkorDB licence](https://docs.falkordb.com/references/license).
- lance-graph: [lance-graph on docs.rs](https://docs.rs/crate/lance-graph/0.5.4).
