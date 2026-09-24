# Security Policy

- **No secrets in the repo.** API keys live in `.env` (gitignored) only.
  If a key is ever committed, rotate it immediately and force-push
  history removal.
- **Reporting.** Use GitHub's private vulnerability reporting (Security
  → Advisories) rather than public issues for anything sensitive.
- **Scope.** This system reads public sports/odds APIs; it executes no
  trades and stores no personal data beyond operator config.
