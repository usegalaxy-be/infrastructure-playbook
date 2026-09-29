# ansible-galaxy-systemd

Sets up handlers and zerglings and a zergpool. We should probably make that configurable for people who want other setups?.

## Requirements

- systemd

## Role Variables

I don't feel like syncing the readme with my default file every time a variable gets added. Just [go there][defaults].

[defaults]: defaults/main.yml

## Dependencies

- [galaxyproject.galaxy](https://github.com/galaxyproject/ansible-galaxy)

Many variables from that role are set. It is assumed you will use that in your playbook as well.

## Example Playbook

### Basic ###

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
- [Helena Rasche](https://github.com/erasche)
