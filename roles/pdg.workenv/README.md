# pdg.workenv

Deploys a consistent admin working environment (vim, tmux, aliases) for the
`galaxy_master` user across all managed hosts. Also deploys the tmux session
init script and vault password helper on the login node (`vgcn-controller`).

This role targets the **admin users** in `workenv_users` (`galaxy_master` by
default, personal accounts on the login node). The Galaxy application
user's shell environment is managed separately by `usegalaxy-eu.bashrc`.

## What it deploys

### All hosts

| File | Purpose |
|---|---|
| `~/.vimrc` | Personal vimrc for `galaxy_master` (can be customised without touching system default) |
| `/etc/vimrc` | System-wide vim config — applies to every user (root, galaxy, condor, etc.) |
| `/etc/profile.d/workenv-aliases.sh` | Shell aliases for every login user on the host |

### Login node only (`vgcn-controller`, `workenv_deploy_session_script: true`)

| File | Purpose |
|---|---|
| `~/galaxy-session.sh` | Pure-tmux session init — replaces `galaxy-byobu.sh` |
| `~/.vault-pass.sh` | Ansible vault password script — reads `$ANSIBLE_VAULT_PASSWORD` from SSH env |
| `/etc/logrotate.d/tmux-logs` | Daily log rotation for `~/tmux-logs/`, 7-day retention |
| `~/bin/wt-clean` | Removes git worktrees whose PR is merged (`wt-clean` dry run, `wt-clean --apply`) |

## Variables

```yaml
# defaults/main.yml
workenv_users:
  - uname: galaxy_master
    uhome: /home/galaxy_master

workenv_vim_install: true            # ensure vim package is present
workenv_tmux_install: false          # tmux — enabled for loginnode via group_vars
workenv_deploy_session_script: false # session script + vault helper — loginnode only
workenv_venv: ""                     # venv auto-activated in .zshrc, relative to each user's home
```

## Usage

```bash
# All hosts
ansible-playbook playbooks/infrastructure/workenv.yml

# Login node only
ansible-playbook playbooks/infrastructure/workenv.yml --limit loginnode

# Exclude a host or group
ansible-playbook playbooks/infrastructure/workenv.yml --limit 'all:!proxyservers'
```

No `--vault-password-file` flag needed — `ansible.cfg` points to `~/.vault-pass.sh`
which reads `$ANSIBLE_VAULT_PASSWORD` from the environment (see setup below).

## Vault password setup (per client machine)

`$ANSIBLE_VAULT_PASSWORD` is forwarded over SSH from your local machine so it
never touches disk on the controller. Do this once on each machine you SSH from:

**1. Set the environment variable on your local machine**

Temporarily (current session only):
```bash
export ANSIBLE_VAULT_PASSWORD="your-vault-password"
```

Permanently (add to `~/.zshenv` — loaded for all shells including non-interactive):
```bash
echo 'export ANSIBLE_VAULT_PASSWORD="your-vault-password"' >> ~/.zshenv
```

Or source it from your password manager (recommended — see below).

**2. Add `SendEnv` to your local `~/.ssh/config`**

```
Host vgcn-controller.usegalaxy.be
    SendEnv ANSIBLE_VAULT_PASSWORD
```

**3. Reconnect your SSH session**

The variable is injected at login time. Existing tmux windows won't have it —
open a new window (`Ctrl+b c`) or re-attach after reconnecting.

### Using a password manager (recommended)

Rather than storing the password in `~/.zshenv`, retrieve it on demand from
your password manager CLI before SSHing. Example with Keeper Commander:

```bash
# ~/.zshrc — add a login function
function galaxy() {
    export ANSIBLE_VAULT_PASSWORD=$(keeper get --format=password <record-uid>)
    ssh vgcn-controller.usegalaxy.be
}
```

Run `galaxy` instead of `ssh vgcn-controller...`. The password is fetched fresh
from Keeper, forwarded over SSH, and never written to disk anywhere.

## galaxy-session.sh

Replaces `galaxy-byobu.sh` with a pure tmux equivalent — no byobu layer,
no F-key dependency. Start or restart your session:

```bash
~/galaxy-session.sh            # kill any existing session, start fresh, attach
~/galaxy-session.sh --attach   # attach to existing session if present, else start fresh
```

Windows created: `ansible`, `test`, `prod`, `condor`, `pulsar-vib`, `monitoring`.
Shell output is logged to `~/tmux-logs/` (except the monitoring/htop window).

## Vim quick-reference

| Key | Action |
|---|---|
| `<Space>w` | Save |
| `<Space>q` | Quit |
| `<Space><Space>` | Clear search highlight |
| `<Space>e` | File explorer (netrw) |
| `<Space>b` | List open buffers |
| `<Space>[` / `<Space>]` | Previous / next buffer |
| `Ctrl+h/j/k/l` | Navigate splits |
| `Alt+j/k` | Move line(s) up / down |
| `>` / `<` (visual) | Indent and keep selection |

## tmux quick-reference

Prefix is `Ctrl+b`.

| Key | Action |
|---|---|
| `Prefix \|` | Split vertically |
| `Prefix -` | Split horizontally |
| `Prefix h/j/k/l` | Navigate panes |
| `Prefix H/J/K/L` | Resize panes |
| `Prefix r` | Reload `~/.tmux.conf` |
| `Prefix c` | New window (opens in current path) |
| `Prefix [` | Enter copy mode (`/` search, `v` select, `y` yank) |
