# Retry and Health

Jatai retries delivery when it cannot process a file.

## Retry behavior

- Retry metadata is stored in `.retry` files.
- Delay follows exponential backoff.
- After max retries, the original file is moved to `INBOX` with the error prefix.

## Operational tips

- Keep daemon logs in `~/.jatai.log` under observation.
- Use `jatai status` to verify local node activity.
