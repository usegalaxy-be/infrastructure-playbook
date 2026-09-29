#!/usr/bin/env python3
"""Seed HashiCorp Vault from ansible-vault encrypted var files.

Reads the lookup placeholder files (stubs) to learn which key belongs at
which Vault path, decrypts the corresponding real files in memory via
`ansible-vault view`, and writes each path with `vault kv put`.

Secret values are never printed and never written to disk.

Requires: vault CLI on PATH, VAULT_ADDR set, and a valid token
(`vault login` / VAULT_TOKEN). Dry-run by default; use --execute to write.

Example:
  python3 scripts/vault_seed.py \
    --stub-root  path/to/branch/inventories \
    --src-root   path/to/main-checkout/inventories \
    --vault-password-file path/to/.vault-password-prod.txt \
    --vault-password-file path/to/.vault-password-test.txt \
    --mount vsc/prod
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# stub line patterns
RE_HELPER = re.compile(
    r"""^(_\w+):\s*["']\{\{\s*lookup\('community\.hashi_vault\.hashi_vault',\s*'([^']+)'\)\s*\}\}["']"""
)
RE_INLINE = re.compile(
    r"""^(\w+):\s*["']\{\{\s*lookup\('community\.hashi_vault\.hashi_vault',\s*'([^']+)'\)\.(\w+)\s*\}\}["']"""
)
RE_HELPER_REF = re.compile(
    r"""^(\w+):\s*["']\{\{\s*(_\w+)\.(\w+)\s*\}\}["']"""
)


def find_stub_files(stub_root: Path):
    """Same file set decrypt.sh targets: files in dirs named 'vault' + files named vault.yml."""
    files = set()
    for d in stub_root.rglob("vault"):
        if d.is_dir():
            files.update(p for p in d.rglob("*") if p.is_file())
    files.update(p for p in stub_root.rglob("vault.yml") if p.is_file())
    return sorted(files)


def parse_stub(path: Path):
    """Return {vault_path: {key: None}} declared in one stub file."""
    helpers = {}  # _name -> vault path
    mapping = {}  # vault path -> set of keys
    for line in path.read_text().splitlines():
        line = line.strip()
        m = RE_HELPER.match(line)
        if m:
            helpers[m.group(1)] = m.group(2)
            continue
        m = RE_INLINE.match(line)
        if m:
            mapping.setdefault(m.group(2), set()).add(m.group(3))
            continue
        m = RE_HELPER_REF.match(line)
        if m and m.group(2) in helpers:
            mapping.setdefault(helpers[m.group(2)], set()).add(m.group(3))
    return mapping


def decrypt_yaml(src_file: Path, password_files):
    """Decrypt with ansible-vault view (trying each password file), parse in memory."""
    last_err = ""
    for pw in password_files:
        out = subprocess.run(
            ["ansible-vault", "view", str(src_file),
             "--vault-password-file", str(pw)],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            data = yaml.safe_load(out.stdout)
            if not isinstance(data, dict):
                raise RuntimeError(f"{src_file}: decrypted content is not a YAML mapping")
            return data
        last_err = out.stderr.strip()
    raise RuntimeError(f"ansible-vault view failed for {src_file}: {last_err}")


def target_path(stub_path: str, mount: str):
    """'<any-mount>/data/usegalaxy-be/db' -> '<mount>/usegalaxy-be/db' (kv put re-inserts data/)."""
    mount = mount.rstrip("/")
    suffix = stub_path
    for prefix in (f"{mount}/data/", "secret/data/"):
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix):]
            break
    return f"{mount}/{suffix}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stub-root", required=True, type=Path,
                    help="inventories/ dir of the branch containing lookup stubs")
    ap.add_argument("--src-root", required=True, type=Path,
                    help="inventories/ dir of the checkout with encrypted vault files")
    ap.add_argument("--vault-password-file", required=True, type=Path,
                    action="append",
                    help="may be given multiple times (e.g. prod and test passwords)")
    ap.add_argument("--mount", required=True,
                    help="target KV v2 mount, e.g. vsc/prod")
    ap.add_argument("--only", default=None,
                    help="only handle vault paths containing this substring, e.g. oidc/test")
    ap.add_argument("--execute", action="store_true",
                    help="actually write to Vault (default: dry-run)")
    args = ap.parse_args()

    # secrets[target] = {key: value}; provenance[target][key] = source file
    secrets, provenance, problems = {}, {}, []

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
            bucket = secrets.setdefault(tgt, {})
            prov = provenance.setdefault(tgt, {})
            for key in sorted(keys):
                if key not in data:
                    problems.append(f"{rel}: key '{key}' not found in {src}")
                    continue
                if key in bucket and bucket[key] != data[key]:
                    problems.append(
                        f"conflict at {tgt}/{key}: {prov[key]} vs {rel} give different values")
                    continue
                bucket[key] = data[key]
                prov[key] = str(rel)

    for tgt in sorted(secrets):
        keys = sorted(secrets[tgt])
        print(f"{'PUT' if args.execute else 'DRY'} {tgt}  ({len(keys)} keys: {', '.join(keys)})")
        if args.execute:
            payload = json.dumps(secrets[tgt], default=str)
            r = subprocess.run(["vault", "kv", "put", tgt, "-"],
                               input=payload, text=True, capture_output=True)
            if r.returncode != 0:
                problems.append(f"vault kv put {tgt} failed: {r.stderr.strip()}")

    if problems:
        print("\nProblems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)
    print(f"\n{len(secrets)} paths {'written' if args.execute else 'planned'}, no problems.")


if __name__ == "__main__":
    main()
