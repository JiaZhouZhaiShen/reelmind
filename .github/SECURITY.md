# Security Policy

## Supported Versions

Security updates are applied to the latest release. We recommend always running the newest tag.

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities. Instead, report privately to the maintainers so the issue can be addressed before disclosure.

Include:
- Affected version / commit
- Steps to reproduce (if safe to share)
- Impact description

## Deployment security notes

- Replace `DB_PASSWORD` and `JWT_SECRET` (`.env.example` uses placeholder `change-me` values).
- `.env` is git-ignored — never commit real credentials.
- No Docker socket is mounted to containers.
- Terminate TLS at your edge proxy before exposing port 2588 publicly.

## Secret scan

Before any public push, ensure no real tokens/keys are tracked: scan for `ghp_|sk-|AKIA|PRIVATE KEY` and confirm `.env`, `backups/`, `*.bak` are absent from the index.
