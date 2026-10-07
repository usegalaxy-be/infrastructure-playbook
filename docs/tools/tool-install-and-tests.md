# Tool installation and testing

How tools reach usegalaxy.be, what tests them afterwards, and the two traps that
make both look like they are working when they are not.

Tool lists live in a separate repo,
[usegalaxy-be-tools](https://github.com/usegalaxy-be/usegalaxy-be-tools), and its
GitHub workflows install them. This repo only deploys the tool tests to the Galaxy
servers.

Files:

| File | Purpose |
|------|---------|
| `playbooks/daily/daily-galaxy-tools.yml` | Applies the role, the only entry point |
| `inventories/group_vars/galaxyservers/galaxy-tools.yml` | `tools_user`, test mode, parallelism |
| `roles/pdg.galaxy-tools/templates/systemd/` | The tool-test unit templates |
| `roles/pdg.galaxy-tools/templates/scripts/tool-tests.sh.j2` | Test entry point, picks the mode |
| `roles/pdg.galaxy-tools/files/compute_new_synced_tools.py` | `synced_diff` mode, diffs synced tools |

Deploy:

```bash
ansible-playbook playbooks/daily/daily-galaxy-tools.yml \
  --limit prodgalaxyservers \
  -e '{"test_tools": false}' \
  --diff
```

`galaxyservers` contains both prod and test, so always `--limit` unless you mean
both.

## Passing test_tools on the command line

The playbook sets `test_tools: yes` as a role var. To override it you must use
the JSON form of `--extra-vars`:

```bash
-e '{"test_tools": false}'   # bool false, test tasks skip
-e test_tools=false          # string "false", which is TRUTHY, tests RUN
```

`-e key=value` always produces a string, and `when: test_tools` on a non-empty
string passes. The `key=value` form silently does the opposite of what it reads
like. This applies to any boolean you override this way, not just `test_tools`.

## What runs when

| What | When | Does |
|------|------|------|
| `install_latest_tool_version.yml` workflow in usegalaxy-be-tools | Merge to `master` touching a `.lock` file, or after the Monday automerge | `shed-tools install` from the `.lock` files |
| `galaxy-tool-tests-full.timer` | yearly, 15 Jan | Re-tests everything |

The playbook runs the role with `galaxy_tools_install_state: absent`, which
removes the old host-side install timers (`galaxy-tool-shed-install@*.timer`),
their units and the install scripts.

`test.usegalaxy.be` installs nothing. Tools reach it by rsync from prod, which is
why it tests with `synced_diff`.

**Testing newly installed tools is not scheduled.** The only armed test timer is
the yearly full sweep. `galaxy-tool-tests.service` is a one-shot that the
playbook starts when `test_tools` is true, so new tools are tested only when
somebody applies the playbook. Nothing chains tests to the CI install.

## Test modes

Set with `galaxy_tools_test_mode`. The role default is `ephemeris`, but
`group_vars/galaxyservers/galaxy-tools.yml` sets `since_date` for every Galaxy
server, so that is the effective default.

| Mode | Tests | Used by |
|------|-------|---------|
| `since_date` | Tools installed since a checkpoint date | prod |
| `synced_diff` | Tools new in the synced `shed_tool_conf.xml` since the last snapshot | test |
| `tools_file` | Whatever is listed in a file | on demand |
| `ephemeris` | Generates the list with `get-tool-list`, the broadest option | role default only |

### The since_date checkpoint moves before the tests run

`test_tools_since_date` is `""`, so `tool_tests.py` falls back to its own
checkpoint file, `{{ tool_install_dir }}/.last_test_since_date`, and selects
tools with:

```sql
SELECT name FROM tool_shed_repository WHERE create_time >= <checkpoint>
```

That is the install database, so the scope is tools first installed since the
checkpoint, not the whole catalogue. A run started on 2026-09-24 against a
checkpoint of 2026-09-19 picked up 69 tools.

The catch is the order. `tool_tests.py` reads the old checkpoint and then writes
today's date back *immediately*, before testing anything:

```python
since_date = read_since_date_checkpoint() or "1970-01-01"
db_tools = get_tools_since_date(db_path, since_date) or []
write_since_date_checkpoint(run_start)
```

So if a run is interrupted, the checkpoint already claims everything up to today
was tested, and the tools it never reached are skipped for good. If you stop a
run early, roll the checkpoint back to the previous value first:

```bash
sudo systemctl stop galaxy-tool-tests.service
echo 2026-09-19 | sudo tee /srv/galaxy/local/galaxy-tools/.last_test_since_date
```

Stop the service, do not kill the process tree. The process group on a Galaxy
host can include live Galaxy processes.

## Troubleshooting

### Tool tests fail immediately on test

`galaxy-tool-tests.service` on `test.usegalaxy.be` exits 1 within a second:

```
PermissionError: [Errno 13] Permission denied:
'/srv/galaxy_test/shared/shared_data/test/mutable-config/shed_tool_conf.xml'
```

`tools_user: root` is set in `group_vars/galaxyservers/galaxy-tools.yml`, but
`synced_diff` has to read a file on an NFS export with root_squash, in a
directory that is `drwxr-x---` owned by `galaxy_master`. Root is squashed to
nobody and denied.

Switching `tools_user` to `galaxy_master` alone does not fix it:
`/srv/galaxy_test/local/galaxy-tools` is `root:root 0755` and the run writes its
output there. A working fix needs both the user override and a chown of the
tools directory. Open, deferred until the tool-test dashboard exists.

## Data managers have no panel section

Data manager tools never enter the tool panel. They are registered in
`shed_data_manager_conf.xml` and appear under Admin > Data Managers, and none of
them appear in `shed_tool_conf.xml` at all. A `tool_panel_section_label` on a
data manager entry is inert, so leaving it unset is correct.
