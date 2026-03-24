# Safe Operations

Jatai is designed for local-first communication with deterministic file operations.

## Recommendations

- Avoid running with elevated privileges.
- Keep node folders under user-owned paths.
- Do not symlink `INBOX` or `OUTBOX` to sensitive system directories.

## Hardening checklist

- Validate registry paths before adding manual entries.
- Audit daemon logs regularly.
- Keep dependency versions updated.
