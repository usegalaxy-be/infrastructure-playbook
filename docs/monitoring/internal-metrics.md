# Internal metrics

How the daily usage numbers per institution and per VIB center get from the
Galaxy database to the **Internal metrics** Grafana dashboard, what each
number means, and how to check that the dashboard matches the database.

Files:

| File | Purpose |
|------|---------|
| `templates/galaxy/monitoring/galaxy-metrics-queries-daily.sql.j2` | The SQL, one block per metric |
| `files/galaxy/monitoring/galaxy-metrics-internal` | Telegraf exec script: runs the SQL, prints line protocol |
| `files/galaxy/monitoring/galaxy-metrics-backfill` | Same SQL for past days, writes to InfluxDB directly |
| `files/galaxy/monitoring/galaxy-metrics-check` | Read-only check of InfluxDB against the database |
| `files/grafana/dashboards/internal-metrics.json` | The dashboard |
| `inventories/host_vars/usegalaxy.be/monitoring.yml` | Telegraf input `galaxy_internal_metrics` and the two outputs |
| `inventories/group_vars/monitoring/monitoring.yml` | Grafana datasource `Metrics` (uid `be-internal-metrics`) |

On usegalaxy.be the playbook installs them in `/usr/local/share/galaxy-metrics/`:
`queries_daily.sql` (rendered template), `psql_query_metrics_telegraf.py`
(galaxy-metrics-internal), `backfill.py` and `check.py`.

Deploy:

```bash
# Scripts and SQL on usegalaxy.be (a changed SQL file restarts Telegraf)
ansible-playbook playbooks/infrastructure/07-monitoring.yml \
  --limit usegalaxy.be --tags monitoring-scripts --diff
# Dashboard
ansible-playbook playbooks/infrastructure/07-monitoring.yml \
  --limit monitoringservers --tags grafana --diff
```

## Pipeline

```
Galaxy DB
  │  daily at 00:00 UTC: Telegraf exec input galaxy_internal_metrics on usegalaxy.be
  │  runs psql_query_metrics_telegraf.py, which runs every query in queries_daily.sql
  ▼
line protocol on stdout, tagged dest=internal_metrics by the input
  │  Telegraf output with tagpass dest=internal_metrics (the other output tagdrops it)
  ▼
InfluxDB monitoring.usegalaxy.be:8086, database internal_metrics
  │  Grafana datasource "Metrics", uid be-internal-metrics
  ▼
Grafana dashboard "Internal metrics" (also used by the tool-usage and tool-tests dashboards)
```

How the SQL becomes measurements:

- Each `-- CATEGORY: <name>` block in `queries_daily.sql` is one query and one
  InfluxDB measurement: the name lowercased, spaces replaced by `_`, so
  `Jobs submitted - Flemish institutions` becomes
  `jobs_submitted_-_flemish_institutions`.
- String columns become tags, numeric columns become fields. A row without any
  numeric value is dropped.
- Every metric exists twice: `- Flemish institutions` (tag `institution`) and
  `- VIB centers` (tag `vib_domain`). Both map unknown domains to `Others`, so
  either one sums to the total for all registered users.
- Every row has the tag `is_vib_data_core`: `true` for the Data Core team and
  service accounts listed in `vault_vib_data_core_emails`. The template fills
  that list in from the vault; the repo holds no addresses. Set the dashboard
  filter **VIB Data Core** to **Exclude** for official numbers.
- Telegraf adds the tags `host` and `dest`. Backfilled points do not have them.
  The dashboard never groups by them, so this makes no difference to the panels.

The same database also holds `tool_usage` and `tool_usage_monthly` from the
`galaxy_tool_usage` input (`galaxy-tool-usage`), and the download usage from the
`galaxy_download_usage` input (`galaxy-download-usage`). This page does not
cover them, and the check skips them.

## Which day a point holds

The queries count *yesterday*: `create_time` from
`date_trunc('day', current_date - interval '1 day')` up to
`date_trunc('day', current_date)`. Galaxy stores `create_time` in UTC.

- Telegraf runs the 24h input at 00:00 UTC, so points carry a timestamp
  between 00:00:01 and 00:00:04 UTC. **A point stamped on UTC day X holds the
  data for day X - 1.** The backfill uses the same rule (00:00:01 UTC).
- The DB server's TimeZone is `Europe/Berlin`. At 00:00 UTC it is already day
  X in Berlin, so `current_date` is X and the window is UTC day X - 1, as
  intended. If the collection time ever moved to between 22:00 and 24:00 UTC,
  the window would shift by a day.
- The dashboard uses the browser time zone, so a point shows at 01:00 or 02:00
  on day X. For a calendar month, set the time range in UTC from the 2nd of the
  month to the 1st of the next month (23:59), or use the link `check.py` prints.
- If Telegraf is down at 00:00 UTC, that day is never collected. Fill it with
  the backfill (below).

## What each number means

All counts are for registered users only (jobs with a `user_id`).

| Measurement | Field(s) | Definition | Can change after collection |
|-------------|----------|------------|-----------------------------|
| `new_users_-_*` | `new_users_count` | Accounts created that day | Total no. Per institution yes: purging a user rewrites the email, so they move to `Others` |
| `newly_active_users_-_*` | `newly_active_users_count` | Activated users whose first job was that day | Only through `active` and email changes |
| `active_users_-_*` | `active_users_count` | Activated users with at least one job that day | Only through `active` and email changes |
| `jobs_submitted_-_*` | `total_jobs_submitted` | Jobs created that day | Only through history imports (below) |
| `jobs_by_state_-_*` | `job_count` per tag `state` | Jobs created that day, by their last state in `job_state_history` before the day ended | No |
| `jobs_executed_-_*` | `jobs_submitted`, `jobs_executed`, `jobs_never_executed` | Executed: `job_state_history` has a `running` row, at any time | Yes: a job still queued at 00:00 counts as never executed for good |
| `cpu_hours_-_*` | `cpu_hours` | `runtime_seconds × galaxy_slots / 3600` of that day's jobs, allocated not used | Yes: a job still running at 00:00 has no runtime yet and is never counted |
| `total_data_uploaded_-_*` | `total_data_uploaded_gb` | Size of `tier1_data` datasets created that day | Yes, and over-counts (below). No panel uses it |

Things to know before reporting a number:

- **CPU hours and executed jobs are a snapshot taken at midnight.** The daily
  run never revisits a day, so long jobs submitted late in the day are missing
  from CPU hours. Backfilled days were computed when the backfill ran, weeks or
  years later, so they *do* include those jobs. Old and recent days are
  therefore not on quite the same basis.
- **History imports backdate jobs.** Importing a history archive inserts its
  jobs with their original `create_time`, after that day was collected. A
  re-run then finds more jobs than InfluxDB holds; the check recognises these
  by their first `job_state_history` row coming after that day.
- **`total_data_uploaded` counts every copy.** The query joins each dataset to
  all its history items, so a dataset copied into a second history counts
  twice. It also counts tool outputs, not just uploads, and `total_size` is
  filled in when the job finishes. Fix the query before putting it on a panel.
- **The institution mapping is a substring match on the email domain**, first
  match wins, VIB first (`vib|psb|ccb|...|irc|cmn` anywhere in the domain).

## Backfill

`backfill.py` runs the same queries for a range of past days and writes the
points with the timestamp the daily run would have used. `--end` is exclusive.
A day written twice (by the backfill and by Telegraf, or by two backfill runs
with different timestamps) is summed twice by every panel. The check below
reports such duplicates.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/backfill.py \
  --start 2026-03-21 --end 2026-03-22 --dry-run   # drop --dry-run to write
```

The database account comes from galaxy_master's login environment and
`~/.pgpass` on usegalaxy.be. The InfluxDB account is the one Telegraf writes
with: `influxdb_users.regular[1]` in `inventories/group_vars/all/vault/influx_vault.yml`,
also in the `internal_metrics` output of `/etc/telegraf/telegraf.conf` on usegalaxy.be.

Which days are backfilled, and the results of past checks, are in the
internal admin docs (usegalaxy-be-doc, `internal-metrics.md`).

## Checking the dashboard against the database

Run this after changing the SQL, the dashboard or the backfill, and before
reporting numbers from a period you have not checked yet.

**1. Run the check** on usegalaxy.be. It is read-only on both sides.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/check.py \
  --start 2026-10-03 --end 2026-10-17
```

`--start` and `--end` are data days; `--end` is exclusive and can be today at
the latest. The default is the last 14 days. It prints four parts and ends with
`RESULT: OK` (exit 0) or `RESULT: MISMATCH` (exit 1):

1. **Collection.** One point per day for every measurement. Lists days that
   have jobs in the database but no point, and days with more than one point.
2. **Totals.** Plain SQL without the institution mapping, run per day (jobs, new
   users, newly active users, active users per day, executed jobs, CPU hours),
   against the sums of both the Flemish and the VIB center measurements.
   Executed jobs and CPU hours are compared "as collected": counting only what
   had happened by the end of each day. This matches the daily run exactly,
   while backfilled days differ (see above).
3. **Series.** Re-runs the deployed `queries_daily.sql` for each day and
   compares every stored series (measurement, tags, field). This covers the
   institution mapping and the Data Core tag. `--skip-series` skips it.
4. **Panels.** The values the stat panels should show for the window, and a
   dashboard link with exactly that time range (in UTC).

Differences in the measurements listed as "can change after collection" are
reported with the reason and do not fail the check.

Every SQL query covers a single day. Do not replace them with one query over
the whole window: over months, that builds large temp files on the DB server.
Each query also has a 120s `statement_timeout`; the script names the query and
day if one hits it. A long window just takes longer: 4 to 6 minutes per year
without part 3, about 1s per day for part 3. Avoid per-job subqueries: some
days have tens of thousands of jobs from one user.

**2. Compare the panels.** Open the printed link, keep Institution and VIB
Data Core on **All**, and compare **Total jobs**, **Registered users**,
**Active registered users**, **Peak daily active users** and **Total CPU
hours** with part 4. If Total jobs shows the number in the parenthesised line
instead, the stat shows one institution instead of the sum.

**3. By hand, for one day** (optional). This is the same comparison without
the script, for example when the script itself is in doubt. Data day 2026-10-15
is stored at 2026-10-16 00:00 UTC:

```sql
-- psql on usegalaxy.be
SELECT count(*) FROM job
 WHERE user_id IS NOT NULL
   AND create_time >= '2026-10-15' AND create_time < '2026-10-16';
SELECT count(*) FROM galaxy_user
 WHERE create_time >= '2026-10-15' AND create_time < '2026-10-16';
SELECT count(DISTINCT job.user_id) FROM job JOIN galaxy_user gu ON gu.id = job.user_id
 WHERE gu.active AND job.create_time >= '2026-10-15' AND job.create_time < '2026-10-16';
```

```sql
-- InfluxQL, database internal_metrics (curl .../query or Grafana Explore on "Metrics")
SELECT sum("total_jobs_submitted") FROM "jobs_submitted_-_flemish_institutions"
 WHERE time >= '2026-10-16T00:00:00Z' AND time < '2026-10-17T00:00:00Z'
SELECT sum("new_users_count") FROM "new_users_-_flemish_institutions"
 WHERE time >= '2026-10-16T00:00:00Z' AND time < '2026-10-17T00:00:00Z'
SELECT sum("active_users_count") FROM "active_users_-_flemish_institutions"
 WHERE time >= '2026-10-16T00:00:00Z' AND time < '2026-10-17T00:00:00Z'
```

Each pair should be equal. Then set the dashboard to that one day (UTC
2026-10-16 00:00 to 23:59) and the stat panels should show the same numbers.
