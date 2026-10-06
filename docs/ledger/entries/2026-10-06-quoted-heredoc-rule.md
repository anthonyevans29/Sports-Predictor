**2026-10-06 — RULED (ARCHITECT): quoted heredocs only for PR text, a standing rule.**
- **Ruling (verbatim):** "CLAUDE.md: quoted heredocs only for PR text — standing rule."
- **Incident:** an unquoted heredoc for #290's body ran the backticked spans as commands. One of them, `python cli.py nfl-grade` with no DATABASE_URL set, created an empty `data/sports.db` in the cloud container (0 tables; never committed; the laptop and host DBs were untouched). The file and its sidecars were removed on the operator's instruction, and the body was repaired.
- **Recorded:** a Workflow bullet in CLAUDE.md.
