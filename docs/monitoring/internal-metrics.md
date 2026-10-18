# Internal metrics

Every night at 00:00 UTC, Telegraf on usegalaxy.be runs a set of SQL queries
on the Galaxy database. Each query counts something for the previous day, such
as new users, jobs or CPU hours, per Flemish institution and per VIB centre.
Telegraf writes the results to the `internal_metrics` database in InfluxDB, and
the **Internal metrics** dashboard in Grafana shows them.

## Files

| In this repo | On usegalaxy.be, in `/usr/local/share/galaxy-metrics/` |
|--------------|--------------------------------------------------------|
| `templates/galaxy/monitoring/galaxy-metrics-queries-daily.sql.j2` | `queries_daily.sql`, the queries |
| `files/galaxy/monitoring/galaxy-metrics-internal` | `psql_query_metrics_telegraf.py`, run by Telegraf |
| `files/galaxy/monitoring/galaxy-metrics-backfill` | `backfill.py`, fills in past days |
| `files/galaxy/monitoring/galaxy-metrics-check` | `check.py`, compares InfluxDB with the database |
| `files/grafana/dashboards/internal-metrics.json` | The dashboard, on the monitoring server |

Telegraf runs `psql_query_metrics_telegraf.py` once a day. The script does
nothing more than run every query in `queries_daily.sql`, one after the other,
and print the results in InfluxDB's text format: text columns (institution, VIB
centre, Data Core or not) become labels, number columns become the values.
Telegraf adds the time and sends the lines to InfluxDB. To add a metric, add a
query to the SQL file; the script needs no change.

The Telegraf settings are in `inventories/host_vars/usegalaxy.be/monitoring.yml`.

To deploy the scripts and queries, then the dashboard:

```bash
ansible-playbook playbooks/infrastructure/07-monitoring.yml --limit usegalaxy.be --tags monitoring-scripts --diff
ansible-playbook playbooks/infrastructure/07-monitoring.yml --limit monitoringservers --tags grafana --diff
```

A change to the queries restarts Telegraf.

## Reading the numbers

- A point dated day X holds the numbers for day X - 1, because the queries
  run just after midnight and count the day before.
- Every metric is stored twice: per Flemish institution and per VIB centre.
  Users who match neither are counted under `Others`, so both add up to the
  same total.
- Only registered users are counted.
- Data Core team and service accounts are marked. Set the dashboard filter
  **VIB Data Core** to **Exclude** for official numbers.

| Metric | What it counts |
|--------|----------------|
| New users | Accounts created that day |
| Newly active users | Users whose first job was that day |
| Active users | Users who ran a job that day |
| Jobs submitted | Jobs created that day |
| Jobs by state | Those jobs, by their state at the end of the day |
| Jobs executed | Those jobs that started running |
| CPU hours | Run time of those jobs, times their cores, in hours |
| Data uploaded | Size of the files uploaded that day, each file once, in GiB |

A job or upload still running at midnight is never added to CPU hours, jobs
executed or data uploaded. Days filled in later with the backfill script do
include them.

On the dashboard, the graphs show one value per day. The stat panels and the
"by institution" tables add up all days in the time range picked at the top
right, so they are totals for that range. "Peak daily active users" is the
exception: it shows the busiest single day. Active users have no total, because
the same user is active on many days.

In InfluxDB, each metric is named after its `-- CATEGORY:` line in the
queries, in lower case with `_` for spaces, for example
`jobs_submitted_-_flemish_institutions`.

## Filling in past days

`backfill.py` runs the same queries for past days and writes them as Telegraf
would have. `--end` is the first day it does not fill. Do not fill a day that
already has data: the dashboard would add both.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/backfill.py \
  --start 2026-03-21 --end 2026-03-22 --dry-run
```

The database login works as is for galaxy_master. The InfluxDB login is the one
Telegraf uses: `influxdb_users.regular[1]` in the vault.

## Checking the numbers

`check.py` compares what is in InfluxDB with the Galaxy database. It only
reads. Run it after changing the queries, the dashboard or the backfill.

```bash
ssh usegalaxy.be
INFLUXDB_USER=... INFLUXDB_PASSWORD=... \
  /srv/galaxy/shared/etc/venv-py3.11/bin/python3 /usr/local/share/galaxy-metrics/check.py \
  --start 2026-10-03 --end 2026-10-17
```

By default it checks the last 14 days. It ends with `RESULT: OK` or
`RESULT: MISMATCH`, then prints the totals the dashboard should show and a link
to the dashboard for the same days, so you can compare them by eye.

If you change the check or the queries, keep each query to a single day.
Queries over months can fill the database server's disk with temporary files.

### Checking by hand

You can also run the queries yourself for a period and compare the result with
the dashboard.

1. On usegalaxy.be, run all queries for the period. `START` is the first day,
   `END` the day after the last day. Keep the period to a month or two.

   ```bash
   START=2026-10-03
   END=2026-10-17
   sed -e "s/^-- CATEGORY: \(.*\)/\\\\echo \1/" \
       -e "s/date_trunc('day', current_date - interval '1 day')/'$START'::date/g" \
       -e "s/date_trunc('day', current_date)/'$END'::date/g" \
       /usr/local/share/galaxy-metrics/queries_daily.sql | psql -X
   ```

   This prints one table per metric, with its name above it.

2. In Grafana, open the **Internal metrics** dashboard and set the time range
   one day later than the period, because each day is stored on the day after:
   from `START + 1 day` 00:00:00 to `END` 23:59:59. Set the time zone to UTC
   (time picker, "Change time settings"). For the example above: from
   2026-10-04 00:00:00 to 2026-10-17 23:59:59.

3. Leave **Institution** on All. Set **VIB Data Core** to All and add up the
   `true` and `false` rows, or set it to Exclude and use only the `false` rows.

4. Compare the totals: Total jobs, Registered users, Active registered users
   and Total CPU hours, and the "by institution" tables. Jobs executed and CPU
   hours can be a little higher in your query, for jobs that were still running
   at midnight. Active users only match for a single day.

Check results and known gaps in the data are in the internal admin docs
(usegalaxy-be-doc, `internal-metrics.md`).
