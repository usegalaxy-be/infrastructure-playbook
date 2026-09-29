# pdg.update_hosts

Manages `/etc/hosts` custom entries on all managed hosts. Intended as a thin,
idempotent wrapper around `ansible.builtin.lineinfile` with three guarantees:

1. **cloud-init disabled** — sets `manage_etc_hosts: false` in
   `/etc/cloud/cloud.cfg` so cloud-init does not regenerate `/etc/hosts` on
   every boot and wipe custom entries.
2. **Standard localhost block ensured** — adds the standard IPv4/IPv6 localhost
   lines (including the host-specific `127.0.0.1 <fqdn> <hostname>` entries
   derived from Ansible facts) if they are missing. This repairs hosts where the
   legacy `pdg.condor_cm` cron wiped `/etc/hosts` entirely.
3. **Custom entries managed** — adds entries from `host_mappings` and removes
   entries from `host_mappings_absent`.

## Variables

All variables default to empty lists. Define per-group overrides in the
corresponding `group_vars/*/vault_hosts.yml` (encrypted).

### `host_mappings`

List of entries to ensure are present in `/etc/hosts`.

```yaml
host_mappings:
  - ip: "x.x.x.x"
    hostname: "usegalaxy.be"
  - ip: "x.x.x.x"
    hostname: "test.usegalaxy.be"
```

Each entry produces a line `<ip> <hostname>` appended at EOF if not already
present. `hostname` may contain multiple space-separated aliases
(e.g. `"usegalaxy.be www.usegalaxy.be"`).

### `host_mappings_absent`

List of entries to remove from `/etc/hosts`. Same format as `host_mappings`.
Use this for one-time cleanup of stale entries.

```yaml
host_mappings_absent:
  - ip: "x.x.x.x"
    hostname: "vsc-galaxy.irods.hpc.kuleuven.be"
```

## Usage

The role is included in the full infrastructure playbooks that already target
the relevant host groups:
the vault password
- `playbooks/infrastructure/00-proxy.yml` — proxy servers
- `playbooks/infrastructure/04-galaxy.yml` — galaxy servers

A dedicated lightweight playbook targets all hosts and is the preferred way to
apply `/etc/hosts` changes without a full redeployment:

```bash
# All hosts
ansible-playbook playbooks/daily/daily-update-hosts.yml

# Single group
ansible-playbook playbooks/daily/daily-update-hosts.yml --limit proxyservers

# Single host
ansible-playbook playbooks/daily/daily-update-hosts.yml --limit usegalaxy.be
```

## Per-group configuration

| Group | vault_hosts.yml location | Notes |
|-------|--------------------------|-------|
| `galaxyservers` | `group_vars/galaxyservers/vault_hosts.yml` | Currently empty. `host_mappings_absent` contains a one-time cleanup entry for the 2026-03 iRODS DNS pin — remove after confirmed. |
| `proxyservers` | `group_vars/proxyservers/vault_hosts.yml` | Internal IP mappings for usegalaxy.be vhosts. |
| All others | *(none — role defaults apply)* | localhost block is still guaranteed. |

## Notes

- The role is fully idempotent; re-running it is always safe.
- `ignore_errors: true` is set on the cloud-init task so the role does not fail
  on hosts without cloud-init installed (e.g. bare-metal or non-RHEL systems).
- The localhost block task uses `ansible_fqdn` and `ansible_hostname` facts;
  `gather_facts` must be enabled in the calling playbook (Ansible default).
