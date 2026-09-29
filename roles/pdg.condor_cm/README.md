# pdg.condor_cm — LEGACY

> **This role is no longer in use.** It has been superseded by `grycap.htcondor`,
> which is the active role for HTCondor configuration on both galaxy servers
> (`06-galaxy-postrequisites.yml`) and compute workers (`cluster/01-compute-reinit.yml`).

## What this role did

- Installed `/usr/bin/update-hosts` (from `templates/update-hosts.sh.j2`), a script
  that queried `condor_status` for live worker IPs and rewrote `/etc/hosts` hourly.
- Installed `/etc/cron.d/ansible_update_hosts` to run the above script every hour.
- Installed `/etc/cron.d/ansible_condor_auto_approve` for `condor_token_request_auto_approve`.
- Copied operational scripts (iperf, fio benchmarks, etc.) to the galaxy server.

## Migration notes

- `condor_auto_approve` was migrated to a direct `cron` task in `06-galaxy-postrequisites.yml`.
- The `update-hosts` cron and script are removed by cleanup tasks in `06-galaxy-postrequisites.yml`.
- The hourly `/etc/hosts` rewrite was found to strip all non-condor entries (localhost lines,
  static DNS pins) — a side effect that went unnoticed after the role was commented out.
  This was the root cause of `/etc/hosts` changes not persisting on galaxy servers.
- `grycap.htcondor` does not manage `/etc/hosts`. HTCondor communicates by IP (via
  `condor_status`) and does not require hostname resolution of workers.

## Do not re-enable

Do not re-enable this role. If dynamic worker hostname resolution is needed in future
(e.g. for `pssh`), implement it as a properly scoped task in the active playbooks.
