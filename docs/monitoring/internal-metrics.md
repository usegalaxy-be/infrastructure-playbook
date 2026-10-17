# Internal metrics

Daily usage per institution and VIB center, from the Galaxy database to the
**Internal metrics** Grafana dashboard.

```
Galaxy DB
  │  Telegraf exec input galaxy_internal_metrics on usegalaxy.be, daily at 00:00 UTC
  ▼
InfluxDB monitoring.usegalaxy.be:8086, database internal_metrics
  │  Grafana datasource "Metrics" (uid be-internal-metrics)
  ▼
Dashboard "Internal metrics"
```

| File | Deployed as (usegalaxy.be, `/usr/local/share/galaxy-metrics/`) |
|------|------|
| `templates/galaxy/monitoring/galaxy-metrics-queries-daily.sql.j2` | `queries_daily.sql` |
| `files/galaxy/monitoring/galaxy-metrics-internal` | `psql_query_metrics_telegraf.py` (run by Telegraf) |
| `files/galaxy/monitoring/galaxy-metrics-backfill` | `backfill.py` |
| `files/galaxy/monitoring/galaxy-metrics-check` | `check.py` |
| `files/grafana/dashboards/internal-metrics.json` | Grafana |

Telegraf input and outputs: `inventories/host_vars/usegalaxy.be/monitoring.yml`.

```bash
ansible-playbook playbooks/infrastructure/07-monitoring.yml --limit usegalaxy.be --tags monitoring-scripts --diff
ansible-playbook playbooks/infrastructure/07-monitoring.yml --limit monitoringservers --tags grafana --diff
```

## How the SQL becomes data

- Each `-- CATEGORY: <name>` block is one measurement, named lowercase with
  `_` for spaces: `jobs_submitted_-_flemish_institutions`.
- String columns become tags, numbers become fields.
- Every metric exists per Flemish institution (tag `institution`) and per VIB
  center (tag `vib_domain`). Both have an `Others` bucket, so each sums to the
  total.
- Tag `is_vib_data_core` marks the Data Core accounts (`vault_vib_data_core_emails`).
  Set the dashboard filter **VIB Data Core** to **Exclude** for official numbers.
- **A point stamped on UTC day X holds day X - 1.** The queries count
  yesterday, and Galaxy stores times in UTC.

## Metrics

Registered users only. "Late" means the stored value can differ from a later re-run.

| Measurement | Counts | Late |
|-------------|--------|------|
| `new_users_-_*` | Accounts created that day | Per institution: purged users move to `Others` |
| `newly_active_users_-_*` | Activated users whose first job was that day | Rarely |
| `active_users_-_*` | Activated users with a job that day | Rarely |
| `jobs_submitted_-_*` | Jobs created that day | History imports add jobs with old dates |
| `jobs_by_state_-_*` | Those jobs by state at the end of the day | No |
| `jobs_executed_-_*` | Those jobs that ever reached `running` | Yes: jobs queued at 00:00 stay "never executed" |
| `cpu_hours_-_*` | `runtime_seconds × galaxy_slots / 3600` of those jobs | Yes: jobs running at 00:00 are never counted |
| `total_data_uploaded_-_*` | Datasets from upload jobs, any storage, each once, GiB | Yes: uploads running at 00:00 |

Backfilled days were computed later, so they include the late jobs and
uploads. Points written before the data uploaded fix count every copy of every
new dataset (about double) until that measurement is dropped and backfilled again.

## Backfill

Writes past days with the same timestamps as Telegraf. `--end` is exclusive.
A day written twice is summed twice.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/backfill.py \
  --start 2026-03-21 --end 2026-03-22 --dry-run
```

The DB login comes from galaxy_master's environment and `~/.pgpass`. The
InfluxDB login is `influxdb_users.regular[1]` (vault), as in the
`internal_metrics` output of `/etc/telegraf/telegraf.conf`.

## Check

Read-only. Run after changing the SQL, the dashboard or the backfill.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/check.py \
  --start 2026-10-03 --end 2026-10-17
```

Default: the last 14 days. Ends with `RESULT: OK` or `RESULT: MISMATCH`.

1. Collection: one point per day, no duplicates.
2. Totals: plain per-day SQL against both the Flemish and VIB center sums.
3. Series: the deployed SQL re-run against every stored series (`--skip-series` skips it).
4. Panels: the values the stat panels should show, and a dashboard link for the window.

Late metrics are reported, not failed. Open the link and compare the stat
panels with part 4.

Keep every check query to one day and avoid per-job subqueries: longer windows
fill the DB server's temp space, and some days have tens of thousands of jobs.

By hand, for one day (data day 2026-10-15 is stored on 2026-10-16):

```sql
-- psql on usegalaxy.be
SELECT count(*) FROM job WHERE user_id IS NOT NULL
  AND create_time >= '2026-10-15' AND create_time < '2026-10-16';
-- InfluxQL, database internal_metrics
SELECT sum("total_jobs_submitted") FROM "jobs_submitted_-_flemish_institutions"
  WHERE time >= '2026-10-16T00:00:00Z' AND time < '2026-10-17T00:00:00Z'
```

Check results and known data gaps: internal admin docs (usegalaxy-be-doc, `internal-metrics.md`).
