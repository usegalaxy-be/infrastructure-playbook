#!/usr/bin/env python3
"""Copy conda environments to a new conda root and rewrite the old root path in them.

Runs on the NFS server, so the work is local. Paths inside the environments are the client
paths (--old-prefix, --new-prefix); the new one must not be longer than the old one, so paths
inside programs can be rewritten in place, as conda does when it installs a package.

Each environment is copied as hard links (cp -al), so unchanged files take no space or time.
Files that hold the old path are replaced by rewritten copies, never edited in place, so the
old environment is not changed. Every file is searched for the old path, because conda-meta
does not list all of them (entry-point scripts, files written by post-link scripts, and .pyc
caches Python rebuilt).

A file that contains the old path is handled like this:
  - text files (no NUL byte): plain replace, as conda does for text
  - files conda lists as binary in conda-meta, and ELF files: conda's binary replace
  - .pyc caches: removed, Python rebuilds them from the rewritten source
  - other binary files: left as they are, listed in the log
Absolute symlinks into the old root are pointed at the new root.

A finished environment gets a .copied marker; environments with a marker are skipped,
so the script can be run again after an interruption. The log, lock and list of failed
environments are in the directory that holds the new miniconda3.

Run with the new Miniforge's python, which provides the conda package:
  python conda_copy_envs.py --old-envs /data/share/prod/etc/dependencies/miniconda3/envs \
    --new-envs /data/share/shared_data/dependencies/miniconda3/envs \
    --old-prefix /srv/galaxy/shared/etc/dependencies/miniconda3 \
    --new-prefix /srv/galaxy_shared/dependencies/miniconda3 [--jobs N] [--limit N] [--only NAME ...]
"""
import argparse
import fcntl
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from conda.core.portability import replace_prefix
from conda.models.enums import FileMode

MARKER = ".copied"


def conda_binary_files(env):
    """Paths, relative to env, that conda installed in binary prefix mode."""
    binary = set()
    for meta in glob.glob(os.path.join(env, "conda-meta", "*.json")):
        try:
            with open(meta) as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        for path in record.get("paths_data", {}).get("paths", []):
            if path.get("file_mode") == "binary":
                binary.add(path["_path"])
    return binary


def files_with(env, text):
    """Files under env that contain text; symlinks are not followed."""
    out = subprocess.run(["grep", "-rlFZ", "--", text, env], capture_output=True, check=False)
    if out.returncode > 1:
        # An empty file without read permission cannot hold the path; anything else is an error
        for line in out.stderr.decode(errors="replace").splitlines():
            path = line[len("grep: "):].rsplit(": ", 1)[0] if line.startswith("grep: ") else ""
            if not (line.endswith(": Permission denied") and os.path.isfile(path)
                    and os.lstat(path).st_size == 0):
                raise RuntimeError(line)
    return [p.decode() for p in out.stdout.split(b"\0") if p]


def write_like(path, data, st):
    """Replace path with a new file holding data, keeping its mode, owner and times."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".conda-copy-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, st.st_mode & 0o7777)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def copy_env(name, old_envs, new_envs, old_prefix, new_prefix):
    """Copy one environment. Returns its log lines; raises on failure."""
    start = time.time()
    old_env = os.path.join(old_envs, name)
    new_env = os.path.join(new_envs, name)
    lines = [name]
    if os.path.lexists(new_env):
        shutil.rmtree(new_env)
    subprocess.run(["cp", "-al", old_env, new_env], check=True)

    old_bytes = old_prefix.encode()
    binary = conda_binary_files(new_env)
    rewritten = removed = 0
    others = []
    for path in files_with(new_env, old_prefix):
        rel = os.path.relpath(path, new_env)
        with open(path, "rb") as fh:
            data = fh.read()
        if rel in binary or data[:4] == b"\x7fELF":
            mode = FileMode.binary
        elif b"\0" not in data:
            mode = FileMode.text
        elif path.endswith(".pyc"):
            os.unlink(path)
            removed += 1
            continue
        else:
            lines.append(f"  left as is (binary): {rel}")
            others.append(rel)
            continue
        new = replace_prefix(mode, data, old_prefix, new_prefix, subdir="linux-64")
        if mode == FileMode.binary and len(new) != len(data):
            raise RuntimeError(f"binary rewrite changed the size of {rel}")
        if old_bytes in new:
            raise RuntimeError(f"old path still in {rel} after the rewrite")
        write_like(path, new, os.lstat(path))
        rewritten += 1

    links = 0
    for root, dirs, files in os.walk(new_env):
        for entry in dirs + files:
            path = os.path.join(root, entry)
            if not os.path.islink(path):
                continue
            target = os.readlink(path)
            if target.startswith(old_prefix):
                os.unlink(path)
                os.symlink(new_prefix + target[len(old_prefix):], path)
                links += 1

    open(os.path.join(new_env, MARKER), "w").close()
    lines.append(f"  copied in {time.time() - start:.0f}s: {rewritten} files and "
                 f"{links} links rewritten, {removed} .pyc removed, {len(others)} binaries left")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--old-envs", required=True)
    ap.add_argument("--new-envs", required=True)
    ap.add_argument("--old-prefix", required=True)
    ap.add_argument("--new-prefix", required=True)
    ap.add_argument("--jobs", type=int, default=1, help="environments copied at the same time")
    ap.add_argument("--limit", type=int, default=0, help="copy at most this many environments")
    ap.add_argument("--only", nargs="*", help="copy only these environments")
    args = ap.parse_args()

    old_prefix = args.old_prefix.rstrip("/")
    new_prefix = args.new_prefix.rstrip("/")
    if len(new_prefix) > len(old_prefix):
        sys.exit("--new-prefix must not be longer than --old-prefix")

    new_envs = args.new_envs.rstrip("/")
    os.makedirs(new_envs, exist_ok=True)
    root = os.path.dirname(os.path.dirname(new_envs))
    lock = open(os.path.join(root, "conda-copy.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another copy is running")
        sys.exit(3)

    todo, skipped = [], 0
    for name in sorted(os.listdir(args.old_envs)):
        old_env = os.path.join(args.old_envs, name)
        if args.only and name not in args.only:
            continue
        if not os.path.isdir(old_env) or os.path.islink(old_env):
            continue
        if os.path.exists(os.path.join(new_envs, name, MARKER)):
            skipped += 1
            continue
        todo.append(name)
    if args.limit:
        todo = todo[: args.limit]

    copied = failed = 0
    with open(os.path.join(root, "conda-copy.log"), "a") as log, \
            open(os.path.join(root, "conda-copy-failed.txt"), "w") as failed_list, \
            ProcessPoolExecutor(max_workers=args.jobs) as pool:
        jobs = {
            pool.submit(copy_env, name, args.old_envs, new_envs, old_prefix, new_prefix): name
            for name in todo
        }
        for job in as_completed(jobs):
            name = jobs[job]
            try:
                log.write("\n".join(job.result()) + "\n")
                copied += 1
            except Exception as exc:  # noqa: BLE001 - one bad environment must not stop the rest
                failed += 1
                failed_list.write(f"{name}\n")
                failed_list.flush()
                log.write(f"{name}\n  FAILED: {exc}\n")
                shutil.rmtree(os.path.join(new_envs, name), ignore_errors=True)
            log.flush()
    print(f"copied={copied} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
