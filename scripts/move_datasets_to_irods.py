#!/usr/bin/env python
"""Move datasets from a disk object store to an iRODS object store.

Based on Galaxy's scripts/objectstore/copy_files_to_irods.py, but uses Galaxy's
own object store config for paths and the iRODS connection.

copy:  upload each dataset to iRODS, compare checksums, then point the dataset
       at the iRODS store. The disk copy stays.
clean: for datasets moved at least --min-age-hours ago, compare checksums
       again, then remove the disk copy.
revert: point datasets that still have their disk copy back at the disk store.
check:  read moved datasets that still have their disk copy through Galaxy's
        object store, and compare them with the disk copy.

Datasets used by an unfinished job are skipped in all modes.

Run as the Galaxy user with Galaxy's virtualenv, from <galaxy_server_dir>/scripts:
  python move_datasets_to_irods.py -c galaxy.yml --mode copy \
      --source-store internal_nfs_shares --target-store tier1_data \
      --start-id 1 --end-id 100000 --limit 1000 [--dry-run]
"""

import argparse
import base64
import filecmp
import hashlib
import os
import shutil
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "lib")))

import irods.keywords as kw
from sqlalchemy import (
    bindparam,
    create_engine,
    text,
)

import galaxy.config
from galaxy.exceptions import ObjectNotFound
from galaxy.objectstore import build_object_store_from_config
from galaxy.util.script import (
    app_properties_from_args,
    populate_config_args,
)

ACTIVE_JOB_STATES = ["new", "upload", "waiting", "queued", "running", "resubmitted"]

NOT_USED_BY_ACTIVE_JOB = """
    AND NOT EXISTS (
        SELECT 1 FROM history_dataset_association hda
        JOIN job_to_input_dataset jt ON jt.dataset_id = hda.id
        JOIN job j ON j.id = jt.job_id
        WHERE hda.dataset_id = d.id AND j.state IN :states)
    AND NOT EXISTS (
        SELECT 1 FROM library_dataset_dataset_association l
        JOIN job_to_input_library_dataset jt ON jt.ldda_id = l.id
        JOIN job j ON j.id = jt.job_id
        WHERE l.dataset_id = d.id AND j.state IN :states)
"""

COPY_SELECT = (
    """
    SELECT d.id, d.uuid FROM dataset d
    WHERE d.object_store_id = :source AND d.state = 'ok' AND NOT d.deleted AND NOT d.purged
    AND d.id BETWEEN :start_id AND :end_id
    """
    + NOT_USED_BY_ACTIVE_JOB
    + " ORDER BY d.id LIMIT :limit"
)

CLEAN_SELECT = (
    """
    SELECT d.id, d.uuid FROM dataset d
    WHERE d.object_store_id = :target AND NOT d.purged
    AND d.id BETWEEN :start_id AND :end_id
    AND d.update_time < (now() at time zone 'utc') - make_interval(hours => :min_age_hours)
    """
    + NOT_USED_BY_ACTIVE_JOB
    + " ORDER BY d.id"
)

SWITCH_STORE = """
    UPDATE dataset SET object_store_id = :target, update_time = (now() at time zone 'utc')
    WHERE id = :id AND object_store_id = :source
"""

REVERT_STORE = """
    UPDATE dataset SET object_store_id = :source, update_time = (now() at time zone 'utc')
    WHERE id = :id AND object_store_id = :target
"""


def local_checksums(path):
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return base64.b64encode(sha256.digest()).decode(), md5.hexdigest()


def irods_matches(session, local_path, remote_path):
    """True if the iRODS object has the same size and checksum as the local file."""
    obj = session.data_objects.get(remote_path)
    if obj.size != os.path.getsize(local_path):
        return False
    remote = obj.chksum()
    sha256_b64, md5_hex = local_checksums(local_path)
    if remote.startswith("sha2:"):
        return remote[len("sha2:") :] == sha256_b64
    return remote == md5_hex


def file_pairs(source, target, ds):
    """List (local path, iRODS path) for the dataset file and its extra files."""
    main_local = source._get_filename(ds)
    main_remote = f"{target.logical_path}/{target._construct_path(ds)}"
    pairs = [(main_local, main_remote)]
    dirs = []

    source_extra = f"dataset_{source._get_object_id(ds)}_files"
    target_extra = f"dataset_{target._get_object_id(ds)}_files"
    try:
        extra_local = source._get_filename(ds, extra_dir=source_extra, dir_only=True)
    except ObjectNotFound:
        extra_local = None
    if extra_local and os.path.isdir(extra_local):
        extra_remote = f"{target.logical_path}/{target._construct_path(ds, extra_dir=target_extra, dir_only=True)}"
        extra_remote = extra_remote.rstrip("/")
        dirs.append((extra_local, extra_remote))
        for root, _dirs, files in os.walk(extra_local):
            for name in files:
                local = os.path.join(root, name)
                rel = os.path.relpath(local, extra_local)
                pairs.append((local, f"{extra_remote}/{rel}"))
    return pairs, dirs


def copy_dataset(session, target, pairs):
    options = {kw.FORCE_FLAG_KW: "", kw.DEST_RESC_NAME_KW: target.resource, kw.REG_CHKSUM_KW: ""}
    for local, remote in pairs:
        session.collections.create(os.path.dirname(remote), recurse=True)
        session.data_objects.put(local, remote, **options)
        if not irods_matches(session, local, remote):
            raise RuntimeError(f"checksum or size differs after upload: {remote}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["copy", "clean", "revert", "check"], required=True)
    parser.add_argument("--source-store", required=True, help="disk object store id, e.g. internal_nfs_shares")
    parser.add_argument("--target-store", required=True, help="iRODS object store id, e.g. tier1_data")
    parser.add_argument("--start-id", type=int, required=True)
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=1000, help="maximum number of datasets handled in this run")
    parser.add_argument("--min-age-hours", type=int, default=24, help="clean: only datasets moved this long ago")
    parser.add_argument("--max-errors", type=int, default=20, help="stop after this many failed datasets")
    parser.add_argument("--dry-run", action="store_true", help="list what would happen, change nothing")
    populate_config_args(parser)
    args = parser.parse_args()

    config = galaxy.config.Configuration(**app_properties_from_args(args))
    config.disable_process_management = True
    object_store = build_object_store_from_config(config)
    source = object_store.backends[args.source_store]
    target = object_store.backends[args.target_store]
    session = target.session

    engine = create_engine(config.database_connection)
    params = {
        "source": args.source_store,
        "target": args.target_store,
        "start_id": args.start_id,
        "end_id": args.end_id,
        "limit": args.limit,
        "min_age_hours": args.min_age_hours,
        "states": ACTIVE_JOB_STATES,
    }
    select = COPY_SELECT if args.mode == "copy" else CLEAN_SELECT
    if args.mode in ("revert", "check"):
        params["min_age_hours"] = 0
    with engine.connect() as conn:
        rows = conn.execute(text(select).bindparams(bindparam("states", expanding=True)), params).fetchall()

    done = skipped = failed = 0
    total_bytes = 0
    for dataset_id, dataset_uuid in rows:
        if done >= args.limit:
            break
        ds = SimpleNamespace(id=dataset_id, uuid=uuid.UUID(str(dataset_uuid)))
        try:
            pairs, dirs = file_pairs(source, target, ds)
        except ObjectNotFound:
            # In clean, revert and check mode most datasets in the target store were never on the source store.
            if args.mode == "copy":
                print(f"skip {dataset_id}: no file on {args.source_store}")
                skipped += 1
            continue
        size = sum(os.path.getsize(local) for local, _remote in pairs)

        if args.dry_run:
            print(f"would {args.mode} {dataset_id}: {len(pairs)} files, {size} bytes")
            done += 1
            total_bytes += size
            continue

        try:
            if args.mode == "copy":
                copy_dataset(session, target, pairs)
                with engine.begin() as conn:
                    updated = conn.execute(text(SWITCH_STORE), {**params, "id": dataset_id}).rowcount
                if updated != 1:
                    raise RuntimeError("dataset row not switched, store changed during copy")
                print(f"copied {dataset_id}: {len(pairs)} files, {size} bytes")
            elif args.mode == "check":
                ds.object_store_id = args.target_store
                if not filecmp.cmp(object_store.get_filename(ds), pairs[0][0], shallow=False):
                    raise RuntimeError("Galaxy reads different content than the disk copy")
                print(f"readable {dataset_id}: {size} bytes")
            elif args.mode == "revert":
                with engine.begin() as conn:
                    conn.execute(text(REVERT_STORE), {**params, "id": dataset_id})
                print(f"reverted {dataset_id}: {len(pairs)} files, {size} bytes")
            else:
                for local, remote in pairs:
                    if not irods_matches(session, local, remote):
                        raise RuntimeError(f"iRODS copy differs from disk: {remote}")
                for local_dir, _remote_dir in dirs:
                    shutil.rmtree(local_dir)
                os.remove(pairs[0][0])
                print(f"cleaned {dataset_id}: {len(pairs)} files, {size} bytes")
            done += 1
            total_bytes += size
        except Exception as e:
            print(f"error {dataset_id}: {e}")
            failed += 1
            if failed >= args.max_errors:
                print(f"stopping after {failed} errors")
                break

    print(f"summary mode={args.mode} done={done} skipped={skipped} failed={failed} bytes={total_bytes}")
    object_store.shutdown()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
