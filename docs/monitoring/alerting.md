# Alerting

How Grafana alerts are tiered, routed and repeated for usegalaxy.be, and what to
do when one of them fires.

Files:

| File | Purpose |
|------|---------|
| `templates/grafana/alert_rules.yml.j2` | The rules themselves |
| `templates/grafana/notification_policies.yml.j2` | Tier to cadence mapping |
| `templates/grafana/contact_points.yml.j2` | Teams webhooks (prod + test channels) |
| `files/grafana/dashboards/alerting-overview.json` | Dashboard: is anything firing right now |

Deploy:

```bash
ansible-playbook playbooks/infrastructure/07-monitoring.yml \
  --limit monitoringservers --tags grafana --diff
```

Grafana file provisioning only adds and updates rules by `uid`. It never removes
a rule you deleted from the template. To retire one, add its uid to the
top-level `deleteRules:` list at the bottom of `alert_rules.yml.j2`.

## Severity tiers

Pick the tier from the response the alert should produce, not from how alarming
the number looks.

| Tier | Means | First notification | Repeats while unresolved |
|------|-------|--------------------|--------------------------|
| `critical` | Drop what you are doing | 30s | every 12h |
| `warning` | Look at it today, in working hours | 5m | every 24h |
| `info` | Context, not action | 10m | every 7d |

Rules for choosing:

- If you would not interrupt a meeting for it, it is not `critical`.
- If you would not act on it within a working day, it is not `warning`.
- If nobody would ever act on it, it should be a dashboard panel, not an alert.

A `critical` alert must also be *specific*. "Something is wrong with storage" is
not actionable; "prod root disk has under 2GB free" is.

## Dashboard

Teams gets you notified when a rule fires and repeats. It does not tell you at
a glance what is firing *right now*, or whether something that fired earlier
has gone back to `Normal`. The **Alerting Overview** dashboard
(`files/grafana/dashboards/alerting-overview.json`, uid `be-alerting-overview`)
covers that gap, using Grafana's built-in Alert List panel rather than a new
InfluxDB query, so it always reflects current rule state:

- **Currently Active**: four stat tiles (Critical / Warning / Info / NoData-Error
  firing counts) for a glance-and-move-on check, then one list of every rule not
  in `Normal` state, grouped by severity. Empty means nothing needs attention.
- **Full Status Board**: two side-by-side lists, `env=prod` and `env=test`,
  showing every rule regardless of state. This is the one to check to confirm
  an alert actually recovered, not just stopped repeating.

It reads `severity` and `env` off the same labels the routing rules use
(above), so any rule added under [Adding an alert](#adding-an-alert) shows up
here automatically without touching this file. It does not filter by folder:
the Alert List panel's folder filter needs the folder's Grafana-assigned UID,
which file provisioning does not let us pin, so filtering is done by label
only. `Galaxy Alerts` is the only alerting folder in this Grafana instance, so
in practice this is not a gap — if a second folder is ever added, panels here
will start showing its rules too.

## Why the repeats are so far apart

The previous config repeated `critical` hourly. A root disk sitting just over
85% for 19 hours produced 19 identical messages, none of which said anything the
first one had not. Repeating an alert you have already seen does not add
information, it just trains you to ignore the channel.

12h for `critical` is chosen so that an alert firing overnight resurfaces once
during the next working day, and no more often than that. It is a local
calibration rather than a standard: Alertmanager's own default is 4h, and common
values run from 1h to 12h. Tune it if a real incident is ever missed because of
it, not because the channel feels quiet.

`repeat_interval` is only checked once per `group_interval`, so keep it a whole
multiple of `group_interval` or Grafana silently rounds it up.

## Grouping

Alerts are grouped by `grafana_folder`, `severity` and `env`, not by rule name.
One incident that trips five rules arrives as one message listing five alerts,
instead of five separate messages.

This is why every rule needs an `env` label (`prod` or `test`). A rule without
one lands in its own group and notifies separately.

## Recovery thresholds (hysteresis)

A metric hovering on its threshold will fire, resolve and re-fire indefinitely.
Rules that watch a continuous value therefore set a separate recovery threshold:
the alert fires above one number and only clears below a lower one.

```yaml
conditions:
  - type: query
    evaluator:                # fire when above 85%
      type: gt
      params: [85]
    unloadEvaluator:          # only clear when back below 80%
      type: lt
      params: [80]
```

This needs the `threshold` expression type, which only takes a single value, so
the rule is a three-step chain: query (`A`), `reduce` (`B`), `threshold` (`C`),
with `condition: C`. The older `classic_conditions` expression does the reduce
and the comparison in one step and cannot express a recovery threshold.

Rules counting discrete events (job errors, stuck jobs, backup age) do not need
this and still use `classic_conditions`.

## Persistence instead of severity guessing

Where the same signal can mean either a hiccup or an outage, use two rules on
one metric rather than trying to pick a single tier.

The TPV test jobs are the worked example. They run every 2h against each
destination and already retry up to 3 times within a batch:

- `be-tpv-job-test-failure` (`warning`): one batch failed. Clears by itself when
  the next batch passes 2h later.
- `be-tpv-job-test-sustained` (`critical`): that tool has not passed in 5.5h,
  and `for: 2h15m` means the condition survived at least one further batch. A
  hiccup that recovers clears the pending state and never pages.

Both `GROUP BY "tool"`, so the message names the destination that failed.

## Runbooks

### Root disk

```bash
ssh usegalaxy.be 'df -h /'
ssh usegalaxy.be 'sudo du -xh --max-depth=2 / | sort -rh | head -20'
```

The root disk is 30GB. Known consumers, in the order they usually grow:

| Path | What it is | Safe to delete |
|------|-----------|----------------|
| `~/.cache/{yarn,pip,node-gyp,pnpm}`, `~/.npm/_cacache` | Galaxy client and venv build caches | Yes. Costs one slower rebuild at the next Galaxy upgrade. |
| `~/.apptainer/cache` | Leftovers from interactive `apptainer build` runs | Yes. Galaxy's own cache is `APPTAINER_CACHEDIR` on NFS and is separate. |
| `~/.esmtp_queue` | Undeliverable cron mail | Yes. See below. |
| `/var/log` | journald | Use `journalctl --vacuum-size=`, do not delete by hand. |

The weekly "Prune admin home caches" cron drops cache files older than
`galaxy_admin_cache_max_age_days` (90). Adjust the list in
`inventories/group_vars/galaxyservers/galaxy.yml`.

### Cron mail queue

`esmtp` is the system MTA but `/etc/esmtprc` configures no relay host, so any
mail handed to it queues under `~/.esmtp_queue` and is never delivered or
expired. Between 2024 and 2026 this reached 3942 messages and 1GB.

The crontab now sets `MAILTO=""`, so cron discards job output instead of mailing
it, and a weekly cron clears anything older than 7 days. Jobs whose failure
matters must log to a file and have a Grafana alert, not rely on cron mail.

### Offsite database backup

```bash
ssh usegalaxy.be 'tail -20 ~/cron.log'
ssh usegalaxy.be '/usr/local/bin/mcli ls vibminio/usegalaxy-be/db_backups/prod/ | tail -3'
```

`backup_db.sh` dumps the database nightly at 00:00 and uploads it to MinIO at
`objectstor.vib.be`. It writes `{{ backup_path }}/.last_offsite_backup` only
after the upload exits 0, and `galaxy-backup-freshness` turns that marker's age
into the `galaxy_backup` measurement.

`be-backup-offsite-stale` (warning) fires after 30h, `be-backup-offsite-critical`
after 50h, so one missed night is a ticket and two is a page. An age of `-1`
means the marker does not exist yet and is treated as stale.

A second, older offsite copy (`send_remote_backup.sh`, scp to
`midas.psb.ugent.be`) failed every night from February 2024 because the host
stopped resolving. Nothing noticed for two and a half years: its only failure
signal was cron mail, which was queueing undelivered. That cron is now removed
in both `pdg.postgres-backup` and `igegu.galaxy_extras`, and the alert above
exists so a silent backup failure cannot repeat.

## Adding an alert

1. Pick the tier from the table above.
2. Set `severity` and `env` labels. Both are required for routing and grouping.
3. Give it a `for:` long enough that a transient spike does not reach anyone.
4. If it watches a continuous value, add a recovery threshold.
5. Put the diagnostic command in the description, not a description of the
   command.
6. Give it its own group. Grafana 11.4.0 hits a UNIQUE constraint on
   `alert_rule.guid` when several rules are batch-inserted into one group.
