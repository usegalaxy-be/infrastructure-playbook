#!/bin/bash
# Ansible vault password for vault id "byoc" (managed by Ansible, pdg.workenv).
# Reads it from HashiCorp Vault with the token from vault_login.
set -o pipefail
secret_path="vsc/prod/data/usegalaxy-be/byoc"

if [[ -z "${VAULT_ADDR:-}" || -z "${VAULT_TOKEN:-}" ]]; then
    echo "byoc vault password not loaded: VAULT_ADDR or VAULT_TOKEN is not set, run vault_login first." >&2
    exit 1
fi

# Token goes in on stdin, so it does not show in the process list
printf 'X-Vault-Token: %s\n' "$VAULT_TOKEN" |
    curl -sSf ${VAULT_CACERT:+--cacert "$VAULT_CACERT"} -H @- "$VAULT_ADDR/v1/$secret_path" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["data"]["data"]["vault_password"])'
