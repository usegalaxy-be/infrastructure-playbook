#!/usr/bin/env python3
"""Check whether Vault-stored secrets still match the current encrypted source files.

Decrypts each source file in memory (never printed, never written to disk),
fetches the corresponding Vault secret via `vault kv get`, and reports which
KEYS differ per path. Never prints values, only key names and match/mismatch.

Requires: vault CLI on PATH, VAULT_ADDR/VAULT_TOKEN set.

Example:
  python3 scripts/vault_verify.py \
    --stub-root  path/to/branch/inventories \
    --src-root   path/to/main-checkout/inventories \
    --vault-password-file path/to/.vault-password-prod.txt \
    --vault-password-file path/to/.vault-password-test.txt \
    --mount vsc/prod
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from vault_seed import decrypt_yaml, find_stub_files, parse_stub, target_path


def fetch_vault(tgt: str):
    """Return {key: value} currently stored at tgt, or None if not found."""
    out = subprocess.run(
        ["vault", "kv", "get", "-format=json", tgt],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None, out.stderr.strip()
    payload = json.loads(out.stdout)
    return payload["data"]["data"], None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stub-root", required=True, type=Path)
    ap.add_argument("--src-root", required=True, type=Path)
    ap.add_argument("--vault-password-file", required=True, type=Path, action="append")
    ap.add_argument("--mount", required=True)
    ap.add_argument("--only", default=None,
                    help="only check vault paths containing this substring")
    args = ap.parse_args()

    # current[target] = {key: value} decrypted from the live source files
    current, provenance = {}, {}
    problems = []

    for stub in find_stub_files(args.stub_root):
        mapping = parse_stub(stub)
        if not mapping:
            continue
        rel = stub.relative_to(args.stub_root)
        src = args.src_root / rel
        if not src.exists():
            problems.append(f"missing source file: {src}")
            continue
        try:
            data = decrypt_yaml(src, args.vault_password_file)
        except RuntimeError as e:
            problems.append(str(e))
            continue
        for vpath, keys in mapping.items():
            if args.only and args.only not in vpath:
                continue
            tgt = target_path(vpath, args.mount)
            bucket = current.setdefault(tgt, {})
            prov = provenance.setdefault(tgt, {})
            for key in keys:
                if key not in data:
                    problems.append(f"{rel}: key '{key}' not found in {src}")
                    continue
                if key in bucket and bucket[key] != data[key]:
                    problems.append(
                        f"conflict at {tgt}/{key}: {prov[key]} vs {rel} give different values")
                    continue
                bucket[key] = data[key]
                prov[key] = str(rel)

    any_stale = False
    for tgt in sorted(current):
        stored, err = fetch_vault(tgt)
        if err:
            print(f"ERROR {tgt}: could not read from Vault ({err})")
            any_stale = True
            continue
        live_keys = current[tgt]
        missing_in_vault = sorted(k for k in live_keys if k not in stored)
        extra_in_vault = sorted(k for k in stored if k not in live_keys)
        changed = sorted(
            k for k in live_keys
            if k in stored and live_keys[k] != stored[k]
        )
        if not missing_in_vault and not extra_in_vault and not changed:
            print(f"OK    {tgt}")
            continue
        any_stale = True
        print(f"STALE {tgt}")
        if changed:
            print(f"        changed values for: {', '.join(changed)}")
        if missing_in_vault:
            print(f"        missing from Vault: {', '.join(missing_in_vault)}")
        if extra_in_vault:
            print(f"        extra in Vault (not in current source): {', '.join(extra_in_vault)}")

    if problems:
        print("\nProblems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)

    if any_stale:
        print("\nRe-seed stale paths with: python3 scripts/vault_seed.py ... --only <path> --execute")
        sys.exit(1)
    print(f"\n{len(current)} paths checked, all match Vault.")


if __name__ == "__main__":
    main()
