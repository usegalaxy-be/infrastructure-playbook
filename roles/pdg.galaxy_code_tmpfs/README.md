# pdg.galaxy_code_tmpfs

Keeps a **node-local RAM (tmpfs) copy** of the Galaxy codebase (`server/lib` +
venv) on the condor workers, so the in-job metadata step (`metadata/set.py`,
which runs on the worker host after the tool container exits) imports the Galaxy
framework from RAM instead of cold from NFS.

Measured (issue #504): the metadata import is ~26s cold from NFS vs **~13s** from
RAM. The remaining ~13s is CPU (importing release_26.0 Galaxy + scanning ~315
packages' entry points) and is not fixable by storage.

## Why tmpfs and not local disk

The workers' local disk is Cinder-backed (network storage), so cold small-file
reads are slow there too — a disk copy doesn't help. tmpfs is RAM, so there is no
cold path. Cost: ~1.3 GB RAM per worker (workers have 60-360 GB).

## What it sets up

On each worker:
- a tmpfs mount at `galaxy_code_tmpfs_mount` (default `/opt/galaxy`),
- `/usr/local/sbin/galaxy-code-tmpfs-populate` — rsyncs `server/lib` + venv from
  NFS into the tmpfs, **rewrites the venv's hardcoded NFS paths** to the tmpfs
  path (the copied `activate`/console scripts point at the old location),
  precompiles `.pyc`, and sanity-checks that galaxy imports from the copy,
- `galaxy-code-tmpfs-populate.service` — runs the populate on boot (tmpfs is
  volatile), after the mount + NFS are up.

The paired config change (in `templates/galaxy/config/tpv/destinations.yml.j2`)
sets `GALAXY_LIB` / `GALAXY_VIRTUAL_ENV` on `condor_tpv` to the tmpfs path.

## Version lockstep (mandatory)

The tmpfs copy MUST match the running Galaxy exactly (the metadata code shares
models/datatypes with the handler + DB). **Re-run this role after every Galaxy
deploy** — wire it into the Galaxy deploy playbook so the workers repopulate
whenever the NFS code changes. Drift = broken metadata.

## VERIFY on first deploy

The wiring assumes a destination `env:` `GALAXY_LIB` overrides the job script's
baked value. Confirm on the first real job that the job actually imports from the
tmpfs — e.g. capture a job's `galaxy_*.sh`/env and check `GALAXY_LIB` resolves to
`/opt/galaxy/lib`, and that `runtime_seconds` drops toward ~13s. If the override
does **not** win, fall back to a consistent-path symlink: point Galaxy's
`galaxy_server_dir`/`galaxy_venv_dir` at `/opt/galaxy`, symlink it to the NFS
galaxy on the head, tmpfs on the workers — then no env override is needed.

## Usage

```bash
# test workers
ansible-playbook playbooks/one-off/galaxy-code-tmpfs.yml -i inventories/hosts --limit prodcomputeservers

# prod: override sources
ansible-playbook playbooks/one-off/galaxy-code-tmpfs.yml -i inventories/hosts --limit prodcomputeservers \
  -e galaxy_code_tmpfs_src_lib=/srv/galaxy/shared/server/lib \
  -e galaxy_code_tmpfs_src_venv=/srv/galaxy/shared/database/tool-dependencies/venv-py3.11
```

## Notes / not covered

- Populate reads ~1.3 GB of small files from NFS on each boot/deploy (~1-2 min);
  that's a one-time cost per boot, not per job.
- Only the code (`lib` + venv) is in tmpfs; config/mutable-data stay on NFS.
- The `--ignore-errors` on rsync tolerates a few NFS files unreadable under
  root_squash (test filters etc.); they're not needed by the metadata import.
