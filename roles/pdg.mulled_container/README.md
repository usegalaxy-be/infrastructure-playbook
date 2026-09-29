# pdg.mulled_container

Builds local mulled **singularity** containers for custom Galaxy tools whose
requirement set has no prebuilt BioContainer, and installs them into the
`cached_mulled_singularity` resolver cache. The tool then runs from a single
cached image file instead of importing a conda env over NFS on every job.

## How it works

Each spec just points at a deployed tool XML. The requirements are read from the
XML itself (macros expanded, `python` included), so there is no per-tool package
list to maintain. For each spec, on the build host:

1. Parse the tool XML and compute the resolver name stem with Galaxy's own
   `v2_image_name`, so it matches what the resolver looks up **by construction**.
2. Skip if a matching file already exists in the cache (unless
   `mulled_container_force`).
3. As **root** (rootful Docker writes root-owned files that mulled-build must
   clean up): `mulled-build-tool build <tool.xml>` builds the container image,
   then `apptainer build docker-daemon://…` converts it to a SIF named like the
   resolver id (with its `-<build>` suffix, matching the CVMFS convention). Both
   happen in one step so involucro's post-run image cleanup can't race it.
4. Copy the SIF into `mulled_container_cache_dir` (shared NFS).

The `dir_mtime` cacher picks up the new file on the next lookup, so no Galaxy
restart is needed.

## Requirements

- Docker and Apptainer on the build host (pre-installed on VGCN images).
- Internet access on the build host (pip for `galaxy-tool-util`, conda channels,
  the involucro binary).

## Key variables

See `defaults/main.yml`. Most important:

- `mulled_container_specs`: list of `{name, tool_xml}`. `tool_xml` is the path to
  the deployed tool XML; requirements are read from it, so nothing has to be kept
  in sync by hand. The tool must be deployed first so its XML is on the build host.
  (mulled-build-tool derives any tests from the tool XML; there is no separate
  test argument.)
- `mulled_container_cache_dir`: defaults to the running host's Galaxy cache
  (`{{ galaxy_mutable_data_dir }}/container_cache/singularity/mulled`). When
  building on a Condor worker for prod, set this to the prod path explicitly,
  since `galaxy_mutable_data_dir` is only defined for `galaxyservers`.
- `mulled_container_force`: rebuild even if already cached.

## Usage

Run the wrapper playbook (`playbooks/one-off/build-mulled-containers.yml`):

```bash
ansible-playbook playbooks/one-off/build-mulled-containers.yml --limit test.usegalaxy.be
```

## Verifying

After a build, run the tool and check a fresh job's `command_line` references the
`.sif` rather than a bare `python` from the conda env:

```bash
ssh usegalaxy.be 'gxadmin query q "select command_line from job \
  where tool_id ilike '"'"'%protein_calculator%'"'"' order by create_time desc limit 1"'
```

Also confirm the tool is not forced native by TPV: the `tool_requires_galaxy`
rule (`tool_defaults.yml.j2`) sets `singularity_enabled: false` for tools needing
Galaxy's Python env. protein_calculator currently resolves via conda, so it
should not be caught, but confirm the container wins.

## Not covered / future work

- No automated cleanup of the mulled cache is configured; images persist. Fine
  for a handful of pre-built images.
- This image is local-only. It cannot go to the global BioContainers Stratum 0.
  Hosting BE-only images would need our own CVMFS Stratum 1 (future work).
- Not verified end-to-end in this repo; the first real run on the test host is
  the validation. The SIF-name check in `build_one.yml` fails loudly if
  `mulled-build`'s output name ever diverges from `v2_image_name`.
