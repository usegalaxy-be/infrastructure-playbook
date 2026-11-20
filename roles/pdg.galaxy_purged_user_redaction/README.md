# pdg.galaxy_purged_user_redaction

When Galaxy purges a user through its API or the admin page, it replaces the e-mail address and username with a hash, also in the names of the user's roles. The daily `gxadmin galaxy cleanup` purges deleted users with `pgcleanup.py`'s `purge_deleted_users` action, which leaves the e-mail address and username in place. Its GDPR variant needs the `pgcrypto` extension and does not redact roles.

This role installs a script and a daily cron that finish the job for every purged user that still has an e-mail address. It replaces the e-mail address and username with a SHA-256 hash of the value plus a random string, in `galaxy_user` and in the names and descriptions of the user's roles. It also deletes the preferences of purged users, which can hold passwords for external services, and their remaining sessions. All changes run in one statement, using only built-in PostgreSQL functions.

This role is a stopgap. It can go once `gxadmin galaxy cleanup` can use `pgcleanup.py`'s GDPR purge, and that purge works without `pgcrypto` and also redacts the user's roles.

The script connects with the `PG*` settings below and takes the password from the run user's `~/.pgpass`, which `hxr.postgres-connection` writes. Output goes to the journal:

```bash
journalctl -t galaxy-purged-user-redaction
```

To see what a run would change without changing anything:

```bash
DRY_RUN=1 /usr/local/bin/galaxy-purged-user-redaction
```

## Role variables

| Variable | Default | Description |
|----------|---------|-------------|
| `galaxy_purged_user_redaction_pghost` / `_pguser` / `_pgdatabase` | `""` (required) | Database connection. |
| `galaxy_purged_user_redaction_user` | `galaxy` | Runs the cron; needs a `~/.pgpass` entry. |
| `galaxy_purged_user_redaction_lock_timeout` | `5s` | The statement gives up when it waits longer for a lock; the next run tries again. |
| `galaxy_purged_user_redaction_cron_enabled` | `true` | Set to `false` to install the script without the cron. |
| `galaxy_purged_user_redaction_cron_hour` / `_minute` | `3` / `30` | Cron schedule. |
