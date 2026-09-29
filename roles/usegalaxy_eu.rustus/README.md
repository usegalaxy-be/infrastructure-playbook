# Ansible role: rustus

A role that installs a [rustus](https://github.com/s3rius/rustus) server.

## Requirements

No specific requirements, the role is self-contained.

## Role variables

Role variables are documented in the forms of comments on [defaults/main.yml](defaults/main.yml)

## Dependencies

None.

## Example Playbook

```yaml
- name: Install and configure rustus
  hosts: all
  vars:
    rustus_instances:
    # Runs rustus instances as systemd services
      - name: uploads
        # user that rustus will run as
        user: myuser
        # group that rustus will run as
        group: mygroup
        # rustus will refuse to work if it cannot write to its current working directory,
        # just provide a directory that rustus has write access to (for example the same
        # directory where files will be uploaded)
        working_directory: /data/uploads
        # arguments passed to rustus
        args:
          # see https://s3rius.github.io/rustus/configuration/
          - --host "0.0.0.0"
          - --port 1081
          - --data-dir /data/uploads
          - --hooks-http-urls "https://my-app.example.org/api/upload"
          - --hooks-http-proxy-headers "Cookie"
  roles:
    usegalaxy-eu.rustus
```

## License

See [LICENSE.md](LICENSE.md)

## Author Information

This role was created by contributors of the [Galaxy Project](https://galaxyproject.org/). Check the [contributors page](https://github.com/usegalaxy-eu/ansible-rustus/graphs/contributors) for detailed information.

## Acknowledgments

This role stems from [ansible-role-tusd](https://galaxy.ansible.com/galaxyproject/tusd).
