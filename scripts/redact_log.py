#!/usr/bin/env python3
"""Redact known-sensitive values out of pasted playbook/ansible log output.

Reads the lookup stub files to learn which Vault paths/keys are in play,
fetches their current values from Vault, and keeps only the ones that are
themselves IP-shaped (skips usernames/passwords/other secrets, which are
short generic strings too likely to collide with unrelated log text, e.g.
a value like "admin" corrupting a path such as ".../usegalaxy-be-admin").
Each kept value is replaced everywhere in the input with a <label>
placeholder built from its key name. Values are never printed. Any other
private/public IPv4 address found that isn't a known secret is also
redacted, as <ip-N>.

Requires: vault CLI on PATH, VAULT_ADDR/VAULT_TOKEN set (same as vault_verify.py).

Example:
  ansible-playbook playbooks/infrastructure/02-database.yml --limit dbservers --diff -v 2>&1 \
    | python3 scripts/redact_log.py --stub-root inventories --mount vsc/prod \
    > cleansed.log
"""

import argparse
import re
import sys
from pathlib import Path

from vault_seed import find_stub_files, parse_stub, target_path
from vault_verify import fetch_vault

IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b")


def build_replacements(stub_root: Path, mount: str):
    """value -> <label>, sourced only from values fetched from Vault (never printed)."""
    replacements = {}
    fetched = {}
    for stub in find_stub_files(stub_root):
        mapping = parse_stub(stub)
        for vpath, keys in mapping.items():
            tgt = target_path(vpath, mount)
            if tgt not in fetched:
                stored, err = fetch_vault(tgt)
                fetched[tgt] = stored or {}
                if err:
                    print(f"warning: could not read {tgt} ({err})", file=sys.stderr)
            for key in keys:
                val = fetched[tgt].get(key)
                if isinstance(val, str) and IPV4_RE.fullmatch(val):
                    replacements[val] = f"<{key.replace('_', '-')}>"
    return replacements


def redact(text: str, replacements: dict) -> str:
    for val, label in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(val, label)

    seen = {}

    def sub_ip(m):
        ip = m.group(0)
        if ip not in seen:
            seen[ip] = f"<ip-{len(seen) + 1}>"
        return seen[ip]

    return IPV4_RE.sub(sub_ip, text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stub-root", required=True, type=Path,
                    help="inventories/ dir containing the lookup stubs")
    ap.add_argument("--mount", required=True, help="Vault KV v2 mount, e.g. vsc/prod")
    ap.add_argument("infile", nargs="?", type=Path, default=None,
                    help="log file to redact; omit to read stdin")
    args = ap.parse_args()

    replacements = build_replacements(args.stub_root, args.mount)
    text = args.infile.read_text() if args.infile else sys.stdin.read()
    sys.stdout.write(redact(text, replacements))


if __name__ == "__main__":
    main()
