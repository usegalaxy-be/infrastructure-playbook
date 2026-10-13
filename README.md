# Infrastructure playbook of useGalaxy.be

## Description
UseGalaxy.be is hosted at VSC using VSC Tier-1 Cloud with project number VSC_00003, with Red Hat Openstack platform as infrastructure. The dashboard can be found here: https://cloud.vscentrum.be/dashboard/.
It uses Ansible to automate the deployment of useGalaxy.be, which configuration, roles,... are kept in this repository.

## Repository structure

```
.
├── inventories/
│   ├── hosts                  # Single unified inventory (prod + test)
│   ├── group_vars/            # Variables scoped to host groups
│   │   ├── all/               # Vars applied to all hosts
│   │   ├── galaxyservers/     # Vars for Galaxy application servers
│   │   ├── dbservers.yml
│   │   ├── computeservers.yml
│   │   ├── monitoring/
│   │   ├── proxyservers/
│   │   └── ...
│   └── host_vars/             # Host-specific variable overrides
│       ├── usegalaxy.be/
│       └── test.usegalaxy.be/
├── playbooks/
│   ├── infrastructure/        # Numbered deployment playbooks (run in order)
│   │   ├── 00-proxy.yml
│   │   ├── 01-galaxy-init.yml
│   │   ├── 02-database.yml
│   │   ├── 03-galaxy-prerequisites.yml
│   │   ├── 04-galaxy.yml
│   │   ├── 05-galaxy-messaging.yml
│   │   ├── 06-galaxy-postrequisites.yml
│   │   └── 07-monitoring.yml
│   ├── daily/                 # Routine operational playbooks
│   ├── one-off/               # Ad-hoc/one-time tasks
│   ├── legacy/                # Legacy playbooks (not actively maintained)
│   └── wip/                   # Work-in-progress playbooks
├── roles/                     # Ansible roles
├── templates/                 # Jinja2 templates for Galaxy config files
├── files/                     # Static files deployed by playbooks
├── scripts/                   # Operational scripts
└── extra_scripts/             # Miscellaneous utility scripts
```

---

## Network topology

This describes a general pattern, not this deployment's actual addresses —
useful if you're running Galaxy + HTCondor split across two separate
OpenStack projects (e.g. your own project plus a partner organization's, with
no direct network route between them). IPs below are placeholder examples.

### Abbreviations

| Term | Full name | Meaning |
|------|-----------|---------|
| VSC/OpenStack project | — | An isolated tenancy in your cloud provider; two projects have no implicit network route between them |
| NFS | Network File System | Distributed file system protocol used for shared storage |
| VXLAN | Virtual Extensible LAN | Network virtualisation technology that encapsulates Layer 2 frames in UDP, allowing Layer 2 segments to span Layer 3 boundaries (used here to extend the NFS network across hypervisors) |
| Floating IP | — | A publicly routable IP address that OpenStack maps to a VM's private IP address via NAT at the router. The VM itself never sees this IP — only the router does. |
| CCB | Connection Broker for HTCondor | An HTCondor mechanism that lets compute workers behind NAT register with a central broker, then receive incoming connections through the broker rather than directly. See [HTCondor CCB networking](#htcondor-ccb-networking) below. |

### OpenStack networks

A deployment like this typically has a handful of separate L2 segments; VMs are explicitly attached to one or more of them.

| Network | Example subnet | Purpose |
|---|---|---|
| VM management | `192.168.xx.0/24` | General VM management network. **All VMs have an interface here.** Used for SSH, Ansible, API calls, and general inter-VM traffic. |
| NFS data | `192.168.xx.0/24` | NFS data network. Galaxy servers and compute workers that mount NFS shares are attached here. Keeps high-throughput NFS I/O off the VM management network. |
| NFS VXLAN overlay | — | VXLAN overlay for NFS. Used for NFS exports that need to span network boundaries via VXLAN encapsulation. |
| Cloud-infra management | `192.168.xx.0/24` | Cloud provider's own infrastructure management network. |
| Partner project's cloud-infra network | (separate project) | Same purpose, in the partner organization's own OpenStack project. Their compute workers have an interface here. |
| Partner project's VM network | (separate project) | VM management network for the partner organization's project. |

### VM network interfaces

| Host | VM network | NFS network | Cloud-infra network | Role |
|------|-----------|-------------|---------------------|------|
| DB server | `192.168.xx.xx` | — | — | PostgreSQL server |
| Prod Galaxy head | `192.168.xx.x0` | yes | `192.168.xx.x0` | Production Galaxy server + HTCondor central manager |
| Test Galaxy head | `192.168.xx.x1` | yes | `192.168.xx.x1` | Test Galaxy server + HTCondor submit node |
| Proxy | `192.168.xx.xx` | — | — | Nginx reverse proxy |
| NFS server | `192.168.xx.xx` | `192.168.xx.xx` | — | Self-managed NFS server |
| Ansible controller | yes | — | — | Ansible controller (login node) |
| Own compute workers | `192.168.xx.xx` | yes | — | HTCondor compute nodes (standard pool) |
| Partner compute workers | — | — | (their own network) | HTCondor compute nodes (partner pool, separate project) |

### Floating IPs

| Floating IP | Attached to | Purpose |
|-------------|-------------|---------|
| `192.168.xx.x0` | Prod head's cloud-infra port | HTCondor CCB broker address advertised to partner workers by the prod head |
| `192.168.xx.x1` | Test head's cloud-infra port | HTCondor CCB schedd address advertised to partner workers by the test head |

### Which IP to use for what

- **SSH / Ansible / rsync**: always use the VM network. All VMs are reachable here and this is where port 22 is expected.
- **NFS mounts**: Galaxy servers and compute workers use the NFS network to reach the NFS server. This avoids saturating the VM management network with storage I/O.
- **PITR rsync (DB → NFS)**: if the DB server has no NFS network interface, it reaches the NFS server via the VM network instead. Rsync over SSH only needs port 22 — no separate rsync daemon port is involved.
- **HTCondor (partner-project workers)**: workers in the partner project cannot reach your VM or cloud-infra networks directly. They communicate with the Galaxy heads exclusively via floating IPs. See [HTCondor CCB networking](#htcondor-ccb-networking) below.

---

## HTCondor CCB networking

This section explains why cross-project worker connectivity requires special network rules and what each piece of configuration does. It is deliberately detailed because the setup is non-obvious. Addresses are the same RFC 5737 documentation-only examples as above.

### Why partner-project workers need floating IPs

Partner-project compute workers live in a separate OpenStack project with their own private networks. The Galaxy head VMs live in your own project's networks. These two projects have **no direct IP route between them** — a packet from a partner worker addressed to a VM-network IP simply has no path and is dropped.

The only way the two projects can reach each other is via **floating IPs**: publicly routable IP addresses that the cloud router translates to a VM's private IP. Partner workers have a route to the floating-IP range via their own project's router.

### HTCondor CCB — how workers behind NAT connect

In a standard HTCondor setup, the central manager (on the Galaxy head) connects directly to each compute worker when it wants to assign a job. This fails for partner workers because the Galaxy head has no route to their private network.

**CCB (Connection Brokering)** reverses this: each compute worker **registers itself** with the central manager at startup, keeping an open outbound connection. When the central manager wants to assign a job, it tells the worker (via that existing connection) to open a **new inbound connection** to the job scheduler (schedd). The schedd never initiates a connection to the worker; the worker always connects outward.

This works for partner workers because they can reach the Galaxy head's floating IP, so the outbound registration connection succeeds.

### `TCP_FORWARDING_HOST` — advertising the right address

When HTCondor daemons advertise themselves in the pool, they normally advertise their private IP address. A partner worker cannot reach that address, so the CCB reverse connection would fail.

`TCP_FORWARDING_HOST` tells the HTCondor daemon to advertise a **different address** — in this case, the floating IP — instead of the private IP. Partner workers then know which address to call back to for their CCB connections.

| Host | `TCP_FORWARDING_HOST` | Why |
|------|-----------------------|-----|
| Prod head | its floating IP | Partner workers make CCB reverse connections here |
| Test head | its floating IP | Partner workers make CCB reverse connections here |

Ansible variable: `condor_tcp_forwarding_host` in each host's `postrequisites.yml`.

### The hairpin NAT problem

Setting `TCP_FORWARDING_HOST` creates a new problem. HTCondor daemons on the Galaxy head itself (e.g. `condor_q`, the schedd) now also try to reach their own address via the floating IP. But **a VM cannot reach its own floating IP from within the same VM network**: the floating IP lives on the router, and the router does not send the traffic back into the VM — the packet goes out, hits the router, and is dropped because there is no path back in.

This is called **hairpin NAT**: traffic trying to "hairpin" back from the router to the same VM it came from.

**Fix — iptables DNAT rule in the OUTPUT chain**: before a packet to the head's own floating IP even leaves the Galaxy head, the kernel rewrites its destination to the VM's own private IP. The packet never reaches the router; it loops back locally.

```
packet to <own-floating-ip>:9618
  → OUTPUT chain DNAT rule fires
  → destination rewritten to <own-vm-network-ip>:9618
  → packet delivered locally
```

This is in `06-galaxy-postrequisites.yml` under "Add iptables NAT OUTPUT DNAT rule for condor CCB hairpin NAT".

### Peer schedd hairpin — the second layer

If you run more than one scheduler (schedd) in the same HTCondor pool — e.g. a prod head and a test head — the central manager needs to talk to all of them, including ones that only exist because of this same floating-IP setup. Each head has the same hairpin NAT problem reaching its peer's floating IP directly from within the VM network.

A second set of DNAT rules handles this: each head has a rule redirecting its **peer's** floating IP to the peer's VM-network IP.

| On host | Destination rewritten from | To |
|---------|--------------------------|-----|
| Prod head | peer's floating IP:9618 | peer's VM-network IP:9618 |
| Test head | peer's floating IP:9618 | peer's VM-network IP:9618 |

Ansible variable: `condor_peer_schedd_dnat` (list of `{floating_ip, vm_ip}` pairs) in each host's `postrequisites.yml`.

### The routing interface problem

Just adding DNAT rules is not enough. Each Galaxy head may also have a separate cloud-infra network interface whose DHCP pushes a route covering the floating-IP range, so the kernel sends packets there by default instead of via the VM-network interface.

When a DNAT rule fires on a packet that arrived via the wrong interface, the reply travels back via that same interface — but the reply's source is on a network the peer cannot reach. The connection fails.

**Fix — host route**: a `/32` host route for each peer's floating IP forces those specific packets to leave via the VM-network interface instead. The DNAT then fires with the VM-network source IP, which the peer can reply to normally.

```bash
ip route replace <peer-floating-ip>/32 dev <vm-network-interface>
```

This is applied immediately by the "Apply host routes" task in `06-galaxy-postrequisites.yml`, and made persistent across reboots by a NetworkManager dispatcher script (deployed by the same playbook).

### Configuration summary

| File | What it sets |
|------|-------------|
| `host_vars/<prod-head>/postrequisites.yml` | `condor_tcp_forwarding_host`; `condor_peer_schedd_dnat` pointing at the test head |
| `host_vars/<test-head>/postrequisites.yml` | `condor_tcp_forwarding_host`; `condor_peer_schedd_dnat` pointing at the prod head |
| `templates/htcondor/condor_config.local.j2` | Sets `CONDOR_HOST`, `CCB_ADDRESS`, `TCP_FORWARDING_HOST` from the above variables |
| `templates/network/condor-peer-routes.j2` | NetworkManager dispatcher script that re-applies host routes when the VM-network interface comes up |
| `playbooks/infrastructure/06-galaxy-postrequisites.yml` | Installs iptables rules (self-hairpin + peer DNAT) and host routes |

Full addresses for this deployment are in the internal `networking.md` doc.

---

## Variable organisation

Variables are split into purpose-named files that mirror the infrastructure playbooks:

| File | Purpose |
|------|---------|
| `galaxy.yml` | Core Galaxy application settings |
| `prerequisites.yml` | Pre-Galaxy setup (CVMFS, conda, etc.) |
| `database.yml` | PostgreSQL configuration |
| `messaging.yml` | RabbitMQ / job messaging |
| `postrequisites.yml` | Post-install tasks (backup, TIaaS, etc.) |
| `monitoring.yml` | Monitoring stack (InfluxDB, Telegraf, etc.) |
| `proxy.yml` | Nginx reverse-proxy config |
| `legacy.yml` | Commented-out / deprecated vars (kept for reference) |

These files exist at both `inventories/group_vars/all/` (shared across all hosts) and `inventories/group_vars/galaxyservers/` (Galaxy-server specific).

## Inventory

A single `inventories/hosts` file covers both production and test environments. Use `--limit` to target a specific environment or group:

```bash
ansible-playbook playbooks/infrastructure/04-galaxy.yml --limit testgalaxyservers
ansible-playbook playbooks/infrastructure/04-galaxy.yml --limit prodgalaxyservers
ansible-playbook playbooks/infrastructure/04-galaxy.yml --limit galaxyservers
```

`group_vars/` and `host_vars/` live inside `inventories/` so Ansible resolves them automatically regardless of where playbooks are located.

## Git hooks

`scripts/git-hooks/pre-push` refuses a push when a commit does not descend from this repository's first commit (history from elsewhere), or when [gitleaks](https://github.com/gitleaks/gitleaks) finds a secret in the commits being pushed. Git does not install hooks on clone, so enable it once per clone, after installing gitleaks:

```bash
git config core.hooksPath "$(git rev-parse --show-toplevel)/scripts/git-hooks"
```

Use the absolute path: worktrees then share this clone's copy of the hook. A relative path would make each worktree look for the hook in its own checkout, and branches without it would push unchecked.

## Vault password setup

Ansible vault is used to encrypt secrets. The vault password is never stored on
the controller VM — instead it is forwarded as an SSH environment variable from
your local machine at login time. `ansible.cfg` points `vault_password_file` at
`~/.vault-pass.sh`, which reads `$ANSIBLE_VAULT_PASSWORD` from the environment,
so no `--vault-password-file` flag is needed when running playbooks.

### One-time setup per client machine

**1. Set `ANSIBLE_VAULT_PASSWORD` on your local machine**

For a temporary session export (not persisted to disk):
```bash
export ANSIBLE_VAULT_PASSWORD="your-vault-password"
```

For a permanent export, add to `~/.zshenv` (loaded for all shells):
```bash
export ANSIBLE_VAULT_PASSWORD="your-vault-password"
```

> **Future work:** retrieve the password directly from Keeper or another password
> manager CLI instead of storing it in `~/.zshenv`, so it never touches disk.

**2. Add `SendEnv` to your local `~/.ssh/config`**

```
Host vgcn-controller.usegalaxy.be
    SendEnv ANSIBLE_VAULT_PASSWORD
```

**3. Reconnect your SSH session**

The variable is injected at login time. If you are already connected, open a
new tmux window (`Ctrl+b c`) after reconnecting to pick up the forwarded variable.

### How it works on the controller

`sshd` on `vgcn-controller` is configured with `AcceptEnv ANSIBLE_VAULT_PASSWORD`
(alongside `GH_TOKEN`, which uses the same mechanism). On login the variable is
available in your shell session. `~/.vault-pass.sh` (deployed by `pdg.workenv`)
simply echoes it, and Ansible calls the script automatically via `ansible.cfg`.

## HashiCorp Vault setup (DC-managed secrets)

Distinct from the `ansible-vault` password above: some secrets are sourced from
the DC's HashiCorp Vault instance via `community.hashi_vault` lookups instead of
local encrypted files. This is control-node-side setup, not something a
playbook can bootstrap — the interpreter that runs `ansible-playbook` needs
this in place before it can run at all.

Setup steps (Python libraries, Ansible collection, env vars, WireGuard link)
are internal-only — see the team's internal operations doc.

---

## Running the infrastructure playbooks

The numbered playbooks in `playbooks/infrastructure/` are meant to be run in sequence for a full deployment:

```bash
ansible-playbook playbooks/infrastructure/00-proxy.yml
ansible-playbook playbooks/infrastructure/01-galaxy-init.yml
ansible-playbook playbooks/infrastructure/02-database.yml
ansible-playbook playbooks/infrastructure/03-galaxy-prerequisites.yml
ansible-playbook playbooks/infrastructure/04-galaxy.yml
ansible-playbook playbooks/infrastructure/05-galaxy-messaging.yml
ansible-playbook playbooks/infrastructure/06-galaxy-postrequisites.yml
ansible-playbook playbooks/infrastructure/07-monitoring.yml
```

## Daily / operational playbooks

Playbooks in `playbooks/daily/` are lightweight and safe to run frequently without triggering a full redeployment. Each targets `galaxyservers` (both prod and test) unless restricted with `--limit`.

| Playbook | Purpose |
|----------|---------|
| `daily-galaxy-config.yml` | Push configuration changes (galaxy.yml, job_conf.xml, tool panel) without reinstalling dependencies or restarting services. Use after any config file edit. |
| `daily-galaxy-handlers.yml` | Restart Galaxy handler processes and reload systemd units only. Use when config has already been pushed and a service reload is all that's needed. |
| `daily-galaxy-install-deps.yml` | Fetch and install Galaxy Python dependencies (`galaxy_fetch_dependencies: yes`). Use after a Galaxy version bump or when the venv is out of date. |
| `daily-galaxy-tools.yml` | Install new tools and/or test existing tool environments. Controlled by `install_tools` and `test_tools` vars (defaults: skip install, run tests). |
| `daily-galaxy-upgrade.yml` | Apply static config and run `usegalaxy_eu.tpv_auto_lint` to validate TPV routing rules. Use after modifying any TPV YAML files. |
| `daily-galaxy-healthcheck.yml` | Run the job healthcheck once (every probe tool, end to end) and fail unless all pass. Use as the check after any deploy. |
| `daily-update-hosts.yml` | Apply `/etc/hosts` customisations to **all hosts** via `pdg.update_hosts`. Also disables cloud-init host management and ensures the standard localhost block. Run after editing any `group_vars/*/vault_hosts.yml`. |

Typical config-change workflow:

```bash
# 1. Push updated config files
ansible-playbook playbooks/daily/daily-galaxy-config.yml --limit prodgalaxyservers
# 2. Restart handlers to apply changes
ansible-playbook playbooks/daily/daily-galaxy-handlers.yml --limit prodgalaxyservers
```

## Common Operations

Day-to-day Galaxy admin tasks performed directly on the Galaxy server via SSH (not Ansible).

### Viewing Galaxy logs

Galaxy services log exclusively to journald — there are no log files under `/srv/galaxy/`.

```bash
# Recent logs across all gunicorn workers (handlers + web)
sudo journalctl -u "galaxy-gunicorn@*" -n 100 --no-pager

# Follow logs in real time
sudo journalctl -u "galaxy-gunicorn@*" -f

# Filter to a specific instance (services are numbered: @0, @1, @2, ...)
sudo journalctl -u "galaxy-gunicorn@2" -f

# Show logs since a specific time
sudo journalctl -u "galaxy-gunicorn@*" --since "2026-05-12 10:00:00" --no-pager
```

### Restarting Galaxy services

Use `galaxyctl` for graceful restarts — it coordinates handler drain/reload without dropping in-flight jobs.

**Prod** (`usegalaxy.be`):
```bash
# Graceful restart of handlers only
sudo /srv/galaxy/shared/etc/venv/bin/galaxyctl -d \
  --config-file /srv/galaxy/local/config/galaxy.yml graceful handler

# Graceful restart of all Galaxy processes
sudo /srv/galaxy/shared/etc/venv/bin/galaxyctl -d \
  --config-file /srv/galaxy/local/config/galaxy.yml graceful
```

**Test** (`test.usegalaxy.be`):
```bash
sudo /srv/galaxy_test/shared/database/tool-dependencies/venv-26.0/bin/galaxyctl \
  --config-file /srv/galaxy_test/local/config/galaxy.yml graceful handler

sudo /srv/galaxy_test/shared/database/tool-dependencies/venv-26.0/bin/galaxyctl \
  --config-file /srv/galaxy_test/local/config/galaxy.yml graceful
```

**Service layout** (from `gxconfig.yml` — used for targeted `systemctl` restarts):

| Service | Instances | systemd unit |
|---------|-----------|--------------|
| Gunicorn web workers | 2 | `galaxy-gunicorn@0`, `galaxy-gunicorn@1` |
| Job handlers | 3 | `galaxy-handler@0`, `galaxy-handler@1`, `galaxy-handler@2` |
| Workflow scheduler | 1 | `galaxy-workflow-scheduler@0` |

Use `systemctl` to restart a specific instance when a graceful restart left one unit still running:
```bash
# Restart a single stuck instance
sudo systemctl restart galaxy-handler@2
sudo systemctl restart galaxy-gunicorn@1

# Check status of all units
sudo systemctl status "galaxy-gunicorn@*" "galaxy-handler@*" --no-pager
```

For config-only changes, prefer the Ansible playbooks (`daily-galaxy-config.yml` then `daily-galaxy-handlers.yml`) over manual restarts — they ensure config files are rendered from templates before the service reload.

### Checking the HTCondor queue

Run these on the Galaxy server (it is the HTCondor central manager and schedd).

```bash
# All jobs in the queue (own jobs only by default — use -all for all users)
condor_q -all

# Available slots across the pool
condor_status

# Show only idle jobs
condor_q -all -constraint 'JobStatus == 1'

# Diagnose why a specific job is not running (checks requirements vs slot ClassAds)
condor_q -better-analyze <job_id>

# Show slot details including GalaxyGroup, TotalGPUs, Start expression
condor_status -long <slot_name>
```

For claim rejections that are invisible to `-better-analyze` (the slot matched but the startd rejected at claim time), check the SchedLog:
```bash
grep "NOT accepted\|claim" /var/log/condor/SchedLog | tail -50
```

### Recovering from `__SET_METADATA__` failures (`failed_metadata` cascade)

When a `__SET_METADATA__` job fails (e.g. due to a TPV routing problem or a mismatched datatype), the following cascade occurs:

1. **HDA state** is set to `failed_metadata` (stored in the `state` column of `history_dataset_association`, separate from the underlying `dataset.state`).
2. **Downstream jobs** that use this HDA as input are immediately paused by the job handler with the message *"Input dataset '…' failed to properly set metadata."*
3. **Galaxy UI** blocks datatype edits on the HDA because `ok_to_edit_metadata()` returns False for any HDA with an associated non-terminal job — and `paused` is **not** a terminal state (`terminal_states = [ok, error, deleted]`).

Simply restarting the `__SET_METADATA__` jobs with `gxadmin mutate restart-jobs` does not work: the handler checks inputs on every cycle and immediately re-pauses any job whose input HDA is still in `failed_metadata`.

**Fix procedure** (run on `ssh usegalaxy.be`):

```bash
# 1. Clear the failed_metadata state on all affected HDAs
psql -c "
  UPDATE history_dataset_association
  SET state = NULL
  WHERE id IN (
    SELECT DISTINCT h.id
    FROM job j
    JOIN job_to_input_dataset jid ON jid.job_id = j.id
    JOIN history_dataset_association h ON h.id = jid.dataset_id
    WHERE j.tool_id = '__SET_METADATA__'
      AND j.state = 'paused'
      AND j.create_time > now() - interval '8 hours'
      AND h.state = 'failed_metadata'
  );"

# 2. Restart the paused __SET_METADATA__ jobs
psql -qAt -c "
  SELECT DISTINCT j.id
  FROM job j
  JOIN job_to_input_dataset jid ON jid.job_id = j.id
  JOIN history_dataset_association h ON h.id = jid.dataset_id
  WHERE j.tool_id = '__SET_METADATA__'
    AND j.state = 'paused'
    AND j.create_time > now() - interval '8 hours'" \
| gxadmin mutate restart-jobs --commit -

# 3. Resume downstream paused jobs (Trimmomatic etc.)
#
#    Preferred: ask the user to click History menu → "Resume Paused Jobs"
#    in their Galaxy history. Galaxy's Job.resume() sets each paused job
#    back to NEW and recursively propagates to further dependents.
#
#    Admin alternative for bulk/cross-history cases — restarts paused jobs
#    whose inputs are now all clean (subquery excludes legitimately blocked jobs):
psql -qAt -c "
  SELECT DISTINCT j.id
  FROM job j
  WHERE j.state = 'paused'
    AND j.tool_id != '__SET_METADATA__'
    AND j.create_time > now() - interval '8 hours'
    AND NOT EXISTS (
      SELECT 1
      FROM job_to_input_dataset jid
      JOIN history_dataset_association h ON h.id = jid.dataset_id
      JOIN dataset d ON d.id = h.dataset_id
      WHERE jid.job_id = j.id
        AND (h.state IS NOT NULL OR d.state NOT IN ('ok','deferred'))
    )
  ORDER BY j.id" \
| gxadmin mutate restart-jobs --commit -
```

`state = NULL` on the HDA clears the `failed_metadata` flag. The HDA state then falls through to the underlying `dataset.state`, which is unaffected by metadata job failures and remains `ok`.

Adjust the `interval` to match the affected window. Drop `--commit` from `restart-jobs` calls for a dry run.

### Resubmitting failed jobs

**Ad-hoc one-liner** (adjust `tool_id` and interval as needed):

```bash
psql -qAt -c "
  SELECT id FROM job
  WHERE tool_id = '__SET_METADATA__'
    AND state = 'error'
    AND create_time > now() - interval '6 hours'
  ORDER BY id
" | gxadmin mutate restart-jobs --commit -
```

Drop `--commit` from `restart-jobs` to do a dry run that prints the jobs it would restart without changing anything.

**Reusable script** for any tool and time window:

```bash
# extra_scripts/resubmit_failed_jobs.sh <hours> [tool_id_pattern] [--commit]

# Dry run — show what would be restarted
./extra_scripts/resubmit_failed_jobs.sh 6 '__SET_METADATA__'

# Restart all errored spades jobs from the last 24 hours
./extra_scripts/resubmit_failed_jobs.sh 24 'toolshed.g2.bx.psu.edu/repos/nml/spades/spades/%' --commit

# Restart all errored jobs from the last 2 hours regardless of tool
./extra_scripts/resubmit_failed_jobs.sh 2 '' --commit
```

`tool_id_pattern` accepts SQL `LIKE` wildcards (`%` matches any string).

### Querying job state with gxadmin

[gxadmin](https://github.com/galaxyproject/gxadmin) is installed at `~/usegalaxy-be-admin/gxadmin/gxadmin`. Common queries:

```bash
# All errored jobs in the last N hours (with user email and destination)
gxadmin query errored-jobs 6

# Jobs currently in queue (new/queued/running), with user info
gxadmin query queue-details

# Recent jobs across all states for the last N hours
gxadmin query recent-jobs 2

# Info on specific job IDs
gxadmin query job-info 672987 672992

# Tool error rates over the past N weeks
gxadmin query tool-errors --short-tool-id 2
```

### Diagnosing TPV routing failures

When a job fails immediately with `No destinations are available to fulfill request`, the cause is always one of:

1. **Tag conflict** — the tool has contradictory `require` tags (e.g. both `conda` and `singularity` required). Check the `tags=` line in the handler log for the effective tag set after all rules have run.
2. **Core/mem cap exceeded** — the tool's `cores` or `mem` exceeds every destination's `max_accepted_cores`/`max_accepted_mem`. Check the resolved `cores=` value against destination caps in `destinations.yml.j2`.
3. **All matching destinations have the `offline` tag** — all destinations that would otherwise match are currently marked offline.

To validate TPV routing after a config change without submitting real jobs, run the lint playbook:

```bash
ansible-playbook playbooks/daily/daily-galaxy-upgrade.yml --limit prodgalaxyservers
```

---

## TPV (Total Perspective Vortex) Configuration

TPV is the job scheduling framework used by useGalaxy.be to route tool jobs to appropriate execution destinations based on resource requirements, tool properties, and user constraints.

### Configuration files

TPV configuration files are Jinja2 templates rendered onto the Galaxy server during deployment. They are loaded in the order listed in `galaxy_job_conf.yml` under `tpv_config_files`:

| File | Purpose |
|------|---------|
| `tpv/tool_defaults.yml.j2` | Global defaults applied to every tool (cores, mem, env, scheduling) |
| `tpv-shared-database` (GitHub URL) | Community-maintained tool rules from the galaxyproject/tpv-shared-database |
| `{instance}/tpv/destinations.yml.j2` | Instance-specific destinations (test-only Pulsar nodes, etc.) |
| `tpv/tools.yml.j2` | Local tool overrides (supplement or override the shared DB entries) |
| `tpv/interactive_tools.yml.j2` | Galaxy Interactive Tool (GxIT) definitions |
| `tpv/users.yml.j2` | Per-user scheduling overrides |
| `tpv/roles.yml.j2` | Per-role scheduling (ESG metascheduler ranking) |

Later files override earlier definitions of the **same entity type**. Different entity types (tools vs destinations) do not interfere.

### Merge semantics

TPV merges properties from all matching entities (tool + role + user + destination) in priority order:

**Priority: Destination (5) > User (4) > Role (3) > Tool (2)**

| Property | Behaviour |
|----------|-----------|
| `params` | Dict merge — destination wins for the same key |
| `env` | List merge — same-name vars: destination wins |
| `context` | Dict merge — destination wins |
| `cores/mem/gpus` | Destination wins if set; `max_accepted_*` caps the value |
| `rules` | All run — tool rules and destination rules both execute |
| `scheduling` | Union — all require/reject/prefer/accept from all sources apply |
| `rank` | Destination wins (falls back to tool if destination has none) |

**Key implication:** `singularity_enabled` and `docker_enabled` are set at the **tool layer** (not destinations), because a destination setting would override and break tool-level container selection. The default tool sets `singularity_enabled: true`; the `_docker` tool abstract sets `docker_enabled: true, singularity_enabled: false`. Destinations only set volumes and environment — never these flags.

### Destination hierarchy

```
_default_environment          env/params shared by all runners
├── _condor                   runner: condor, scheduling tags
│   └── _condor_container     volumes + env for both singularity and docker
│       ├── condor_tpv        resource caps (16 cores, 260 GB)
│       ├── condor_training   capped resources for training jobs
│       └── pulsar_embedded_it  runner: pulsar_embedded (GxIT)
├── _pulsar                   remote transfer params, Pulsar-side volumes
│   └── pulsar_*              concrete remote Pulsar nodes
condor_conda                  inherits _condor (conda tools, no container)
condor_upload                 standalone upload destination
condor_gpu                    inherits _default_environment (GPU jobs)
```

### Container resolution pipeline

Understanding this pipeline is important for diagnosing container-related job failures.

#### What is a SIF file?

A SIF (Singularity Image Format) file is a **single flat file** containing a complete container filesystem. Unlike Docker's layered images (which require a running daemon), Singularity runs `singularity exec /path/to/image.sif command` directly. SIF files can live on NFS or CVMFS and are read by compute workers without any local extraction.

#### Resolution sequence (local condor jobs)

Container resolution happens **on the Galaxy head node** before the job is dispatched. The compute node never resolves containers — it receives the full SIF path embedded in the job script.

```
1. Galaxy head node runs the resolver chain (container_resolvers_conf.yml, in order):

   a. cached_explicit_singularity   → checks galaxy_mutable_data_dir/container_cache/singularity/explicit/
   b. cached_mulled_singularity     → checks /cvmfs/singularity.galaxyproject.org/all/      ← primary hit
   c. cached_mulled_singularity     → checks /cvmfs/main.galaxyproject.org/singularity/
   d. cached_mulled_singularity     → checks galaxy_mutable_data_dir/container_cache/singularity/mulled/
   e. mulled_singularity            → pulls from quay.io → stores in cache_directory → returns path

2. Resolved absolute SIF path is written into the condor job submission script.

3. Condor worker runs: singularity exec /cvmfs/.../toolname:version.sif <tool command>
   The worker just reads the SIF — it never resolves or pulls anything.
```

CVMFS (`/cvmfs/singularity.galaxyproject.org/all/`) contains pre-built SIF files for nearly all BioContainers and is the primary hit for the vast majority of tools. The local `container_cache` directory is only written to when a tool's container is not yet in CVMFS.

#### Two distinct caches — do not confuse them

| | Galaxy container resolver cache | Singularity runtime scratch |
|---|---|---|
| **Configured by** | `container_resolvers_conf.yml` (`cache_directory`) | `SINGULARITY_CACHEDIR` env var in TPV destinations |
| **Used by** | Galaxy head node process, to find/store SIF files before dispatching jobs | Singularity binary on the compute node during job execution |
| **Path (prod)** | `galaxy_mutable_data_dir/container_cache/singularity/` | `$_GALAXY_JOB_TMP_DIR` (per-job, auto-cleaned) |
| **Written by** | Galaxy process pulling new images via `mulled_singularity` resolver | Singularity for internal OCI/overlay scratch — rarely written to when SIF is pre-resolved |

**The Galaxy resolver cache must be on a shared NFS path** accessible at the same absolute path from both the Galaxy head node (which writes SIF files into it) and all condor workers (which read SIF files from the embedded path in the job script). For usegalaxy.be, `galaxy_mutable_data_dir = /srv/galaxy/shared/database`, which is the NFS-mounted shared directory.

**`SINGULARITY_CACHEDIR` in TPV destinations** is scratch space for the Singularity binary on the compute node during job execution — analogous to `TMPDIR`. It is set to `$_GALAXY_JOB_TMP_DIR` (per-job isolated, auto-cleaned) to avoid writing to the galaxy user's home directory (`~/.singularity/cache`, which is the default when the variable is unset).

For **remote Pulsar nodes**, `SINGULARITY_CACHEDIR` matters more: the Pulsar node may need to pull or cache images itself (depending on its `container_resolvers` config), so a persistent path (`/data/share/var/database/container_cache`) is used there instead.

#### Ansible variables involved

| Variable | Where set | Purpose |
|----------|-----------|---------|
| `galaxy_container_volumes.local` | `group_vars/galaxyservers/galaxy.yml` | List of bind-mount paths passed as `singularity_volumes` and `docker_volumes` to condor jobs |
| `galaxy_mutable_data_dir` | `group_vars/galaxyservers/galaxy.yml` | Root of all Galaxy mutable data; `container_cache/` lives here |
| `container_resolvers_conf.yml.j2` | `templates/galaxy/config/` | Resolver chain run by the Galaxy head node process |
| `SINGULARITY_CACHEDIR` in `_condor_container` env | `destinations_shared.yml.j2` | Per-job scratch for the Singularity binary on condor workers |
| `SINGULARITY_CACHEDIR` in `_pulsar` env | `destinations_shared.yml.j2` | Persistent cache for the Singularity binary on remote Pulsar nodes |

---

## iRODS Object Store

Galaxy stores datasets on VSC Tier-1 iRODS (`vsc-galaxy.irods.hpc.kuleuven.be`).
The configuration lives in:

- `templates/galaxy/config/usegalaxy.be/object_store_conf.xml.j2` (production)
- `templates/galaxy/config/test.usegalaxy.be/object_store_conf.xml.j2` (test)

Both use a `distributed` object store: local NFS backends (weight 0, legacy fallback)
plus one iRODS backend (weight 1, all new data goes here).

### `<connection>` options

| Attribute | Current value | Description |
|-----------|--------------|-------------|
| `host` | *(vault)* | iRODS server hostname. Resolved via `/etc/hosts` before DNS — see [DNS workaround](#dns-workaround) below. |
| `port` | *(vault)* | iRODS port, typically `1247`. |
| `timeout` | `120` | Socket-level timeout (seconds) applied to **every individual socket operation**: TCP connect, SSL handshake, each `recv()`/`send()` during data transfer, and the SSL `close_notify` exchange when tearing down a connection. This is intentionally not lowered — VSC Tier-1 uses hierarchical storage and files may be staged from a slower tier, creating gaps of tens of seconds in an otherwise healthy data transfer. Lowering this would risk aborting legitimate large-file or tape-staged transfers. |
| `refresh_time` | `120` | Age in seconds after which an idle connection is replaced. Must be shorter than the network firewall's idle TCP timeout — see [Connection pool internals](#connection-pool-internals). |
| `connection_pool_monitor_interval` | `15` | How often (seconds) Galaxy's background monitor thread runs. Reduced from 60 to 15 after the 2026-03 incident to shrink the race window — see [Connection pool internals](#connection-pool-internals). Set to `-1` to disable. |

### `<auth>` options

| Attribute | Description |
|-----------|-------------|
| `username` | iRODS service account username (vault). |
| `password` | iRODS service account password (vault). |

### `<resource>` options

| Attribute | Description |
|-----------|-------------|
| `name` | iRODS storage resource name. `default` uses iRODS's configured default. |

### `<zone>` options

| Attribute | Description |
|-----------|-------------|
| `name` | iRODS zone (vault, e.g. `vsc_galaxy`). |

### `<ssl>` options

All values are provided by vault and must match the iRODS server's configuration exactly.

| Attribute | Description |
|-----------|-------------|
| `client_server_negotiation` | SSL negotiation mode, typically `request_server_negotiation`. |
| `client_server_policy` | Enforcement policy: `CS_NEG_REQUIRE` (require SSL) or `CS_NEG_DONT_CARE`. |
| `encryption_algorithm` | Symmetric cipher for parallel transfer encryption, typically `AES-256-CBC`. |
| `encryption_key_size` | Key size in bytes (e.g. `32` for 256-bit). |
| `encryption_num_hash_rounds` | PBKDF2 rounds for key derivation (e.g. `16`). |
| `encryption_salt_size` | Salt size in bytes (e.g. `8`). |
| `ssl_verify_server` | `cert` = verify server certificate against CA; `none` = skip (not recommended). |
| `ssl_ca_certificate_file` | Path to CA certificate file. Leave empty to use the system trust store. |

### `<logical>` options

| Attribute | Description |
|-----------|-------------|
| `path` | Root iRODS collection path for Galaxy data. Defaults to `/<zone>/home/<username>` if omitted. |

### `<cache>` options

Galaxy caches iRODS data objects locally before serving them to jobs or users.

| Attribute | Description |
|-----------|-------------|
| `path` | Local filesystem path for the cache directory. |
| `size` | Maximum cache size in GB. LRU eviction when the limit is approached. |
| `cache_updated_data` | `True` = write updated datasets back to iRODS after jobs. `False` = treat iRODS as read-only. |

### `<extra_dir>` options

Additional local directories for Galaxy's temporary data; never stored in iRODS.

| `type` | Description |
|--------|-------------|
| `job_work` | Per-job working directory, local to the compute node. |
| `temp` | General temporary files. |

### Connection pool internals

Each Galaxy worker process holds **one persistent `iRODSSession`** with a connection
pool. Connections are reused across requests. Two mechanisms age out old connections:

**Safe path — Galaxy's background monitor**
`IRODSObjectStore._connection_pool_monitor()` runs every `connection_pool_monitor_interval`
seconds. For each idle connection older than `refresh_time` it calls
`pool.release_connection(conn, destroy=True)`, which removes the connection from
the idle set with **no socket operation** — no SSL teardown, no risk of blocking.
Socket cleanup is deferred to Python's GC. This is the normal path.

**Risky path — `pool.get_connection()` fallback**
If a request arrives after a connection exceeds `refresh_time` but before the
monitor has had a chance to remove it (the race window), `get_connection()` calls
`conn.disconnect()` **while holding the pool's `RLock`**. `disconnect()` sends a
`RODS_DISCONNECT` message and then calls `socket.unwrap()` (SSL `close_notify`).
If the connection is stale — the TCP session was silently dropped by a network
firewall — the server never replies and `socket.unwrap()` blocks for `timeout`
seconds. While it blocks, **every other thread in the process trying to do any
iRODS operation is also blocked**, because they cannot acquire the same `RLock`.

The race window is at most `connection_pool_monitor_interval` seconds wide. Setting
it to `15` (from `60`) means the window is 15 out of every 120 seconds, reducing
by 4× the chance that a request hits the risky path.

`refresh_time` must be shorter than the network firewall's idle TCP timeout. At
`refresh_time`, the monitor (or the fallback path) will act on the connection. If
the connection is still alive at that age, everything is fast. If the firewall has
already dropped it, the risky path hangs for `timeout` seconds. The exact firewall
timeout for the Galaxy→iRODS path has not been measured; `120s` is conservatively
short and confirmed safe.

**Symptoms of a stale connection incident**
- `socket.timeout: The read operation timed out` from `irods/connection.py disconnect()`
- `irods_pt _exists_remotely: (120089 ms)` — exactly `timeout` seconds, confirming a hang in `disconnect()`
- Cascading freezes: one stale connection serialises all iRODS activity in a worker

**Recovery**
Restart the Galaxy workers — this flushes the pool and creates fresh connections.

### DNS workaround

> **Resolved 2026-03-12.** No active workaround is in place.

During the 2026-03 iRODS incident, `vsc-galaxy.irods.hpc.kuleuven.be` had a dead
DNS round-robin node (`134.58.8.53`) — TCP connections to it timed out after ~2
minutes, causing half of all new iRODS connections to hang. A static `/etc/hosts`
entry pinned the hostname to the working node (`134.58.8.36`), managed by the
`pdg.update_hosts` role in `playbooks/infrastructure/04-galaxy.yml` and stored in
`inventories/group_vars/galaxyservers/vault_hosts.yml`.

KU Leuven fixed the firewall issue on 2026-03-12; both nodes are now reachable and
the `/etc/hosts` pin has been removed (`host_mappings: []` in `vault_hosts.yml`).
If the issue recurs, re-add the entry to `vault_hosts.yml` and re-run `04-galaxy.yml`.

---

## Docker bind-mount failures on NFS directories

### Symptom

A Docker-based job (e.g. AlphaFold) fails immediately with:

```
docker: Error response from daemon: error while creating mount source path
'/srv/galaxy/shared/database/reference_data/dm_data':
mkdir /srv/galaxy/shared/database/reference_data/dm_data: permission denied.
```

### Root cause

The NFS export uses `root_squash` (the default). When the Docker daemon sets up a bind mount it runs as `root` on the worker node. NFS maps root → `nfsnobody` (uid 65534), which is neither the directory owner (`galaxy_master`) nor in the `galaxy_master` group. If the directory has `0750` permissions, `nfsnobody` falls into the "other" class and has no access at all — not even the execute bit needed to traverse the path.

| Permissions | Other bits | nfsnobody can access? |
|-------------|-----------|----------------------|
| `0750` (`rwxr-x---`) | `---` | No — Docker fails |
| `0755` (`rwxr-xr-x`) | `r-x` | Yes — Docker can traverse and bind-mount |

### Fix

Set the affected directory (and any intermediate directories under the NFS mount that also have `0750`) to `0755`. Only the directories Docker uses as mount-source paths need changing — the files inside are accessed inside the container as uid 1001 (`galaxy_master`), which already has full owner access.

```bash
# Check permissions of the relevant path components
stat -c '%a %U:%G %n' \
  /srv/galaxy/shared/database/reference_data \
  /srv/galaxy/shared/database/reference_data/dm_data

# Fix any that show 750
chmod 755 /srv/galaxy/shared/database/reference_data
chmod 755 /srv/galaxy/shared/database/reference_data/dm_data
```

No recursive `chmod` is needed — only the directories listed as `-v` sources in the failing `docker run` command require the fix.

### Why this surface only for Docker and not Singularity jobs

Singularity jobs run directly on the compute worker as the `galaxy` user (uid 1001), not as root. Singularity itself does not require root to set up bind mounts, so `root_squash` never applies. Docker jobs run the daemon as root, which triggers the squash.
