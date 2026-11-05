# pdg.galaxy_session_cleanup

Galaxy keeps a row in `galaxy_session` for every browser session, with the visitor's IP address and host name. It never removes these rows. This role installs a script and a daily cron that clean the table in two steps.

First, the script deletes sessions that have not been used for a while: 14 days for anonymous sessions and 90 days for logged-in ones. A user's newest session is never deleted, as in Galaxy's own `delete_galaxy_sessions.py`. Galaxy shows it as the user's last login in the admin users list and reopens its history at the next login. A logged-in user whose session is deleted has to log in again. Jobs, events and user actions of a deleted session keep their data, and only lose the link to the session.

Then it replaces the IP address and host name of every remaining session older than 14 days with `redacted`. Galaxy only reads these columns in the admin job details and in the name of jobs of anonymous users (`anonymous@<ip>`). That job name code fails on NULL or an empty string, so the script writes a placeholder instead.

Both steps run in batches of 50,000 rows, so each statement holds its locks only briefly. The first run on a large table takes a while: about 6 seconds per batch on test.

The script connects with the `PG*` settings below and takes the password from the run user's `~/.pgpass`, which `hxr.postgres-connection` writes. Output goes to the journal:

```bash
journalctl -t galaxy-session-cleanup
```

To see what a run would change without changing anything:

```bash
DRY_RUN=1 /usr/local/bin/galaxy-session-cleanup
```

## Role variables

| Variable | Default | Description |
|----------|---------|-------------|
| `galaxy_session_cleanup_pghost` / `_pguser` / `_pgdatabase` | `""` (required) | Database connection. |
| `galaxy_session_cleanup_user` | `galaxy` | Runs the cron; needs a `~/.pgpass` entry. |
| `galaxy_session_cleanup_anonymous_days` | `14` | Delete anonymous sessions unused for this many days. |
| `galaxy_session_cleanup_user_days` | `90` | Delete logged-in sessions unused for this many days. |
| `galaxy_session_cleanup_ip_days` | `14` | Replace the IP address of sessions older than this. |
| `galaxy_session_cleanup_placeholder` | `redacted` | Value written instead of the IP address. |
| `galaxy_session_cleanup_batch_size` | `50000` | Rows per statement. |
| `galaxy_session_cleanup_lock_timeout` | `5s` | A statement gives up when it waits longer for a lock; the next run continues. |
| `galaxy_session_cleanup_cron_enabled` | `true` | Set to `false` to install the script without the cron. |
| `galaxy_session_cleanup_cron_hour` / `_minute` | `3` / `15` | Cron schedule. |
