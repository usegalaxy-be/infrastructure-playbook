# pdg.galaxy_scratch_cleanup

Galaxy purges data on scratch storage a set number of days after it was created. This role runs
that purge every day with Galaxy's own `pgcleanup.py purge_old_hdas`, limited to the object
stores listed in `galaxy_scratch_cleanup_stores`. The purge marks the datasets purged in the
database. The existing `gxadmin galaxy cleanup` run removes the files later.

The role refuses any object store id that does not contain `scratch`, so permanent storage can
never be listed by mistake.

```yaml
galaxy_scratch_cleanup_enabled: true
galaxy_scratch_cleanup_stores:
  scratch_tier1: 60
```

With `galaxy_scratch_cleanup_dry_run: true` the purge rolls back and only logs what it would
purge, in `galaxy_scratch_cleanup_log_dir`. Setting `galaxy_scratch_cleanup_enabled: false`
stops and disables the timer.

The units are called `scratch-cleanup.service` and `scratch-cleanup.timer`. They must not start
with `galaxy-`, because gravity removes those units when it updates.
