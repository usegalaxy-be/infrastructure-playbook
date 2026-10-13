# pdg.cvmfs_repo_config

Writes per-repository CVMFS client settings to `/etc/cvmfs/config.d/<repository>.local`, which override the domain settings from `galaxyproject.cvmfs` for that repository only. Run it after `galaxyproject.cvmfs`.

`galaxyproject.cvmfs` has `client_options` per repository, but writes them to `/etc/cvmfs/repositories.d/`, which only CVMFS servers read.

## Variables

```yaml
cvmfs_repo_config:
  main.galaxyproject.org:
    - CVMFS_SERVER_URL="http://cvmfs1-tacc0.galaxyproject.org/cvmfs/main.galaxyproject.org;..."
    - CVMFS_HOST_RESET_AFTER=300
```

Write the repository name into each URL. `@fqrn@` is expanded when the file is read at mount time, but not by `cvmfs_talk host set`, so copying a URL with `@fqrn@` into that command breaks every host.

## Applying to a running mount

The file is read on the next mount or reload. To apply the server order now without a remount:

```bash
sudo cvmfs_talk -i main.galaxyproject.org host set "<url1>;<url2>"
```
