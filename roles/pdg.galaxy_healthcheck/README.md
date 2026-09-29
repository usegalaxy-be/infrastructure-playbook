# galaxy_healthcheck

Installs a scheduled, non-gating Galaxy job healthcheck. It submits a configurable set of
tools to a Galaxy instance via [BioBlend](https://bioblend.readthedocs.io/), waits for each
to finish, and optionally records per-tool results to InfluxDB. It is a health probe: job
failures are reported, never a cause for the role or the schedule to fail.

The recurring run is a self-contained Python script; this role only provisions it (script,
virtualenv, config, cron, log rotation). No Ansible, SSH agent, or vault access is needed at
run time.

## Requirements

- A target host with Python 3 and network access to the Galaxy instance.
- A Galaxy API key with permission to run the chosen tools.

## Role variables

| Variable | Default | Description |
|----------|---------|-------------|
| `galaxy_healthcheck_url` | `""` (required) | Base URL of the Galaxy instance to probe. |
| `galaxy_healthcheck_api_key` | `""` (required) | Galaxy API key. Set from a vault. |
| `galaxy_healthcheck_tools` | `[]` | List of `{tool_id, inputs}` to submit. |
| `galaxy_healthcheck_dir` | `/opt/galaxy-healthcheck` | Install directory. |
| `galaxy_healthcheck_user` / `_group` | `root` | Owner of the installed files and cron. |
| `galaxy_healthcheck_log` | `/var/log/galaxy-job-healthcheck.log` | Log file (one summary line per run; rotated weekly). |
| `galaxy_healthcheck_job_timeout` | `600` | Max seconds to wait per job. |
| `galaxy_healthcheck_poll_interval` | `15` | Seconds between job-state polls. |
| `galaxy_healthcheck_retries` | `3` | Attempts per tool (initial + retries); a tool is reported failed only after failing this many in a row. |
| `galaxy_healthcheck_retry_delay` | `30` | Seconds to wait before re-running the failed tools. |
| `galaxy_healthcheck_cron_hour` / `_minute` | `*/2` / `0` | Cron schedule. |
| `galaxy_healthcheck_run_require_ok` | `true` | On-demand run: fail the play unless every tool passed. |
| `galaxy_healthcheck_keep_history` | `false` | On-demand run: keep the test history instead of purging it. |
| `galaxy_healthcheck_influx_url` | `""` | InfluxDB write URL; empty disables metrics. |
| `galaxy_healthcheck_influx_db` | `galaxy` | InfluxDB database. |
| `galaxy_healthcheck_influx_user` / `_pass` | `""` | InfluxDB basic-auth credentials. |
| `galaxy_healthcheck_influx_measurement` | `galaxy_job_healthcheck` | Measurement for per-tool `ok` field. |
| `galaxy_healthcheck_influx_error_measurement` | `galaxy_job_healthcheck_error` | Measurement for failure stderr. |
| `galaxy_healthcheck_pip_packages` | `[bioblend]` | Packages installed into the venv. |
| `galaxy_healthcheck_virtualenv_command` | `python3 -m venv` | Command used to create the venv. |

## InfluxDB metrics

When `galaxy_healthcheck_influx_url` is set, each run writes line protocol:

```
<measurement>,host=<host>,tool=<tool_id> ok=<0|1>i,attempts=<n>i
<error_measurement>,host=<host>,tool=<tool_id>,outcome=<transient|persistent> error="<stderr>"
```

`ok` is the final state after retries: a tool that fails then recovers is `ok=1` with
`attempts>1`. The error line is written whenever a tool failed at least once, tagged
`outcome=transient` if it recovered or `persistent` if it never did. Alert on `min(ok)`
for hard failures; watch `attempts>1` / `outcome=transient` for intermittent flakiness.

## Example

```yaml
- role: galaxy_healthcheck
  vars:
    galaxy_healthcheck_url: "https://galaxy.example.org"
    galaxy_healthcheck_api_key: "{{ vault_galaxy_admin_api_key }}"
    galaxy_healthcheck_tools:
      - tool_id: some_test_tool
        inputs: {}
    galaxy_healthcheck_influx_url: "http://influx.example.org:8086"
```

## Run manually

Through Ansible, with `tasks_from: run.yml`: runs the provisioned healthcheck once and fails
the play unless the summary line of that run reports every tool OK.

```yaml
- ansible.builtin.include_role:
    name: galaxy_healthcheck
    tasks_from: run.yml
```

On the host:

```sh
{{ galaxy_healthcheck_dir }}/run-healthcheck.sh
tail <galaxy_healthcheck_log>   # one summary line per run
```
