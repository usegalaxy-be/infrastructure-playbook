#!/usr/bin/env python3
"""
fix_tus_jobs.py — Recover stuck __DATA_FETCH__ jobs and scan the tus upload store.

Two independent modes (can be combined):

  --fix-stuck
      Query the DB for DATA_FETCH jobs that are stuck in new/queued/waiting with
      no handler or a wrong handler (e.g. celery). For each, check whether the
      tus file still exists on disk.
        - File exists  → restart via gxadmin mutate restart-jobs --commit
        - File missing → mark the job 'error' (direct SQL, no gxadmin equivalent)

  --scan-tus
      Walk the tus upload store. For each binary file, find the corresponding
      DATA_FETCH job via the job_parameter table. Report the job state and flag:
        - Stuck job (new/queued/waiting, wrong handler) → restart via gxadmin
        - Errored job                                   → optionally retry (--retry-errors)
        - Orphaned file (no job found)                  → print rm command for manual review

Credentials are handled by ~/.pgpass — no password needed in the DSN.

Usage examples:
  # Dry run both modes against prod (no changes):
  python fix_tus_jobs.py --fix-stuck --scan-tus

  # Apply fixes against prod:
  python fix_tus_jobs.py --fix-stuck --scan-tus --no-dry-run

  # Run against test:
  python fix_tus_jobs.py \\
      --dsn "host=db.usegalaxy.be dbname=galaxy-test" \\
      --tus-store /srv/galaxy_test/shared/database/data_stage/tus \\
      --fix-stuck --scan-tus
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import psycopg2
import psycopg2.extras

# Handlers that are considered alive and valid. Update if you add/remove handlers.
VALID_HANDLERS = {"handler_0", "handler_1", "handler_2"}
TOOL_ID = "__DATA_FETCH__"


def get_conn(dsn):
    return psycopg2.connect(dsn)


def _extract_tus_path(files_param_json):
    """Return the first tus file path from a 'files' job_parameter value, or None."""
    if not files_param_json:
        return None
    try:
        files = json.loads(files_param_json)
        if files and isinstance(files, list):
            return files[0].get("file_data")
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return None


def _gxadmin_restart(job_ids, dry_run):
    """Restart jobs via gxadmin mutate restart-jobs."""
    if not job_ids:
        return
    ids_str = ",".join(str(j) for j in job_ids)
    cmd = ["gxadmin", "mutate", "restart-jobs", ids_str]
    if not dry_run:
        cmd.append("--commit")
    print(f"  $ {' '.join(cmd)}")
    if not dry_run:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: gxadmin exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        else:
            print(f"  {result.stdout.strip()}")


def fix_stuck_jobs(conn, tus_store, dry_run=True):
    """
    Find DATA_FETCH jobs stuck with no handler or a non-live handler.
    Restart via gxadmin if the tus file exists; error them out if it doesn't.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT j.id, j.state, j.handler, j.create_time,
               jp.value AS files_param
        FROM job j
        LEFT JOIN job_parameter jp
               ON jp.job_id = j.id AND jp.name = 'files'
        WHERE j.tool_id = %s
          AND j.state IN ('new', 'queued', 'waiting')
          AND (j.handler IS NULL
               OR j.handler NOT IN %s)
        ORDER BY j.create_time
        """,
        (TOOL_ID, tuple(VALID_HANDLERS)),
    )
    jobs = cur.fetchall()

    if not jobs:
        print("No stuck DATA_FETCH jobs found.")
        return

    print(f"Found {len(jobs)} stuck job(s):\n")
    col = "{:>8}  {:<8}  {:<45}  {:<20}  {:<8}  {}"
    print(col.format("ID", "State", "Handler", "Created", "TUS", "Path"))
    print("-" * 130)

    to_restart = []
    to_error = []

    for job in jobs:
        tus_path = _extract_tus_path(job["files_param"])
        if tus_path:
            file_ok = os.path.isfile(tus_path)
        else:
            file_ok = False

        status = "OK" if file_ok else ("MISSING" if tus_path else "NO_PARAM")
        handler_display = job["handler"] or "NULL"
        created = job["create_time"].strftime("%Y-%m-%d %H:%M")
        print(col.format(job["id"], job["state"], handler_display, created, status, tus_path or ""))

        if file_ok:
            to_restart.append(job["id"])
        else:
            to_error.append(job["id"])

    print()
    print(f"  → Restart (tus file present): {to_restart}")
    print(f"  → Error out (tus file absent): {to_error}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        _gxadmin_restart(to_restart, dry_run=True)
        return

    _gxadmin_restart(to_restart, dry_run=False)

    if to_error:
        cur.execute(
            "UPDATE job SET state = 'error' WHERE id = ANY(%s)",
            (to_error,),
        )
        conn.commit()
        print(f"Errored out {cur.rowcount} job(s) with missing tus files.")


def scan_tus_store(conn, tus_store, retry_errors=False, dry_run=True):
    """
    Walk the tus upload store and correlate each file with a DB job.
    Flags orphaned files, stuck jobs, and optionally retries errored jobs.
    """
    if not os.path.isdir(tus_store):
        print(f"ERROR: tus store not found: {tus_store}", file=sys.stderr)
        sys.exit(1)

    # Collect all tus binary files (skip .info metadata sidecars)
    tus_files = {}
    for fname in os.listdir(tus_store):
        if fname.endswith(".info"):
            continue
        fpath = os.path.join(tus_store, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            tus_files[fpath] = {
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime),
            }

    if not tus_files:
        print(f"No tus binary files found in {tus_store}.")
        return

    print(f"Found {len(tus_files)} tus binary file(s) in {tus_store}.\n")

    # Fetch all DATA_FETCH jobs that are still relevant (not ok/deleted) and join
    # their 'files' parameter. We load all into memory and match by path in Python
    # to avoid a slow LIKE ANY query.
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT j.id, j.state, j.handler, j.create_time,
               jp.value AS files_param
        FROM job j
        JOIN job_parameter jp
          ON jp.job_id = j.id AND jp.name = 'files'
        WHERE j.tool_id = %s
          AND j.state NOT IN ('ok', 'deleted')
        ORDER BY j.id
        """,
        (TOOL_ID,),
    )

    path_to_job = {}
    for job in cur.fetchall():
        tus_path = _extract_tus_path(job["files_param"])
        if tus_path:
            path_to_job[tus_path] = job

    # Report
    col = "{:<45}  {:>14}  {:<20}  {:>8}  {:<12}  {}"
    print(col.format("TUS File (ID)", "Size (bytes)", "Modified", "Job ID", "State", "Handler"))
    print("-" * 140)

    to_restart = []
    orphaned = []

    for fpath, finfo in sorted(tus_files.items(), key=lambda x: x[1]["mtime"]):
        fname = os.path.basename(fpath)
        job = path_to_job.get(fpath)
        size_str = f"{finfo['size']:,}"
        mtime_str = finfo["mtime"].strftime("%Y-%m-%d %H:%M")

        if job is None:
            print(col.format(fname, size_str, mtime_str, "ORPHAN", "no_job", ""))
            orphaned.append(fpath)
            continue

        handler_display = job["handler"] or "NULL"
        print(col.format(fname, size_str, mtime_str, job["id"], job["state"], handler_display))

        stuck = job["state"] in ("new", "queued", "waiting") and (
            job["handler"] is None or job["handler"] not in VALID_HANDLERS
        )
        if stuck or (job["state"] == "error" and retry_errors):
            to_restart.append(job["id"])

    print()
    print(f"  → Jobs to restart : {to_restart}")
    print(f"  → Orphaned tus files : {len(orphaned)}")

    _gxadmin_restart(to_restart, dry_run=dry_run)

    if dry_run:
        print("\n[DRY RUN] No changes made.")

    if orphaned:
        print("\nOrphaned files (no active DB job) — review and remove manually if stale:")
        for fpath in orphaned:
            info = tus_files[fpath]
            info_file = fpath + ".info"
            info_suffix = f"  # also: {os.path.basename(info_file)}" if os.path.isfile(info_file) else ""
            print(f"  rm {fpath} {info_file}{info_suffix}  "
                  f"# {info['size']:,} bytes, modified {info['mtime'].strftime('%Y-%m-%d %H:%M')}")


def main():
    parser = argparse.ArgumentParser(
        description="Recover stuck __DATA_FETCH__ jobs / scan the tus upload store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dsn",
        default="host=db.usegalaxy.be dbname=galaxy",
        help="PostgreSQL DSN without credentials — ~/.pgpass supplies auth "
             "(default: 'host=db.usegalaxy.be dbname=galaxy')",
    )
    parser.add_argument(
        "--tus-store",
        default="/srv/galaxy/shared/database/data_stage/tus",
        help="Path to galaxy_tus_upload_store "
             "(default: /srv/galaxy/shared/database/data_stage/tus)",
    )
    parser.add_argument(
        "--fix-stuck",
        action="store_true",
        help="Find stuck DATA_FETCH jobs and restart/error them based on tus file presence",
    )
    parser.add_argument(
        "--scan-tus",
        action="store_true",
        help="Scan the tus store and correlate files with DB jobs",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="(--scan-tus only) Also restart jobs in 'error' state whose tus file still exists",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Apply changes (default: dry run, no changes)",
    )

    args = parser.parse_args()

    if not args.fix_stuck and not args.scan_tus:
        parser.error("Specify at least one of --fix-stuck or --scan-tus.")

    dry_run = not args.no_dry_run
    if dry_run:
        print("[DRY RUN] Pass --no-dry-run to apply changes.\n")

    conn = get_conn(args.dsn)

    if args.fix_stuck:
        print("=" * 50)
        print("Fix Stuck DATA_FETCH Jobs")
        print("=" * 50)
        fix_stuck_jobs(conn, args.tus_store, dry_run=dry_run)
        print()

    if args.scan_tus:
        print("=" * 50)
        print("Scan TUS Upload Store")
        print("=" * 50)
        scan_tus_store(conn, args.tus_store, retry_errors=args.retry_errors, dry_run=dry_run)

    conn.close()


if __name__ == "__main__":
    main()
