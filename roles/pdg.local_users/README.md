# pdg.local_users

Manages local user accounts: SSH keys, optional sudo, and expiry dates. Only
accounts listed in `local_users` are touched, so existing accounts are safe.

- `ssh_keys` is exclusive: keys not in the list are removed from the user's
  `authorized_keys`.
- `expires` locks the account (`chage -E`) from 00:00 UTC on that date. This
  also blocks SSH key logins. Remove the field to unlock.
- `sudo: true` writes `/etc/sudoers.d/local_users_<name>` (checked with
  `visudo`). `sudo_expires` adds a `NOTAFTER` date, so the rule stops working
  on its own, without another playbook run.
- `state: absent` removes the account and its sudo rule. The home directory
  is kept unless `local_users_remove_home: true`.

## Variables

See `defaults/main.yml` for every entry field.

```yaml
local_users:
  - name: alice
    comment: Alice Admin
    uid: 2001
    sudo: true
    ssh_keys:
      - "ssh-ed25519 AAAA... alice@laptop"

  # Temporary guest: sudo for one week, account locked after a month.
  - name: bob
    comment: Bob Guest
    expires: "2026-11-01"
    sudo: true
    sudo_expires: "2026-10-15"
    ssh_keys:
      - "ssh-ed25519 AAAA... bob@laptop"

local_users_sudo_nopasswd: true   # accounts are key-only
local_users_remove_home: false
```
