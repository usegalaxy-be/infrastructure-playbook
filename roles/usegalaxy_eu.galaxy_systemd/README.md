# ansible-galaxy-systemd

Sets up Galaxy server processes responsible for:

- servicing web requests for the UI/API
- setting up, starting, monitoring and submitting jobs to a cluster (if configured)

## Requirements

- systemd
- watchdog, pyYAML (when watchdog is enabled)

## Major Changes

### Version 2.1.0
Introduces Celery service files with `watchdog` integration. The `watchmedo auto-restart` command watches specified directories (`galaxy/server, galaxy/config and galaxy/mutable-config`).  
File patterns default to `*py,*.yml,*.yaml,*.xml`  
Enable by setting `galaxy_systemd_watchdog: true`
### :warning: Version 2.0.0
The Celery workers are now split into two unit-files:
 - external queue, usually used with threads, but could be probably also used with the pools `gevent` or `evenlet` (not tested). Since `autoscale` is not supported for thread pools,  `concurrency` is used as before
 - internal queue, supports `prefork`, so it can `autoscale`
 - deafult concurrency was reduced, keep that in mind
 - max tasks per child were reduced to avoid jammed worker processes and tasks that are started but get never finished (for so far unknown reason)

Be aware that there are now new variable names for these two different nit files and also for the beat file, to keep everything separated.

The restart behavior also changed, to make sure that no old celery workers are running, so the celery workers are getting restarted on each deployment.


:warning: **You need to reassign jobs to the newly named handlers/workflow schedulers, for example with:**

```sh
mutate reassign-job-to-handler <job_id> <handler_id> [--commit]
```

and with for loop for example like this (be careful with mutate, no warranties):

```bash
for job in $(gxadmin query queue-details | awk '/handler_key_0/ {print $3}'); do gxadmin mutate reassign-job-to-handler $job handler_sn06_0 --commit; done

```

- Workflow Schedulers now have a scalable prefix, too. `galaxy_systemd_workflow_scheduler_prefix` By default the first part of `ansible_hostname`
- Handlers have a `galaxy_systemd_handler_prefix` var now, which should be used to give them a unique key together with their process number. For example by using the hostname as prefix, like in the [deafults][defaults]. This makes an **update of the job_conf necessary**.
- Gunicorn is now scalable: just define a number in `galaxy_systemd_gunicorns` and like the handlers, that many of them will spawn.
- The Socket name should now be without the '.sock' prefix, as the sockets are automatically created for each Gunicorn process.
- Be aware that you may have to rename the sockets in your NGINX config.

## Role Variables

I don't feel like syncing the readme with my default file every time a variable gets added. Just [go there][defaults].

[defaults]: defaults/main.yml

## Dependencies

- [galaxyproject.galaxy](https://github.com/galaxyproject/ansible-galaxy)

Many variables from that role are set. It is assumed you will use that in your playbook as well.

## Example Playbook

### Basic

Install Galaxy on your local system with all the default options:

```yaml
- hosts: localhost
  vars:
    galaxy_server_dir: /srv/galaxy
  connection: local
  roles:
    - galaxyproject.galaxy
    - usegalaxy-eu.galaxy-systemd
```

## License

GPLv3

## Author Information

This role was written and contributed to by the following people:

- [Ott Oopkaup](https://github.com/ooobik)
- [Helena Rasche](https://github.com/hexylena)
- [Mira Kuntz](https://github.com/mira-miracoli)
