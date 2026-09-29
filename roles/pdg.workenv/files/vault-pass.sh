#!/bin/bash
# Ansible vault password provider — managed by Ansible (pdg.workenv)
# Reads the vault password from an environment variable forwarded over SSH.
# On your Mac: set ANSIBLE_VAULT_PASSWORD in ~/.zshenv and add
#   SendEnv ANSIBLE_VAULT_PASSWORD  to ~/.ssh/config for this host.
if [[ -z "${ANSIBLE_VAULT_PASSWORD:-}" ]]; then
    echo "ERROR: ANSIBLE_VAULT_PASSWORD environment variable is not set." >&2
    echo "Set it on your Mac in ~/.zshenv and add SendEnv ANSIBLE_VAULT_PASSWORD to ~/.ssh/config" >&2
    exit 1
fi
echo "$ANSIBLE_VAULT_PASSWORD"
