# Ansible role to deploy TPV Broker

A role that installs the TPV Broker, a FastAPI application for advanced metascheduling.

## Requirements

No specific requirements, the role is self-contained.

## Role variables

Role variables are documented in the forms of comments on [defaults/main.yml](defaults/main.yml)

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Install and configure tpv api
  hosts: all
  vars:
    # defaults file for tpv_broker
    tpv_broker_dir: "/opt/tpv_broker"
    tpv_broker_repo: "https://github.com/usegalaxy-eu/tpv-broker.git"
    tpv_broker_commit_id: "main"
    tpv_broker_force_checkout: true # discards local changes if any
    tpv_broker_venv_dir: "/opt/tpv_broker/venv"
    tpv_broker_virtualenv_command: "python -m venv"
    tpv_broker_systemd_service_name: "tpv_broker"
    tpv_broker_systemd_service_user: "nginx"
    tpv_broker_ssl_certificate: ""
    tpv_broker_ssl_certificate_key: ""
    tpv_broker_nginx_conf: true
    tpv_broker_proxy_config:
    location: "/tpv-api/"
    proxy_pass_host: "127.0.0.1"
    proxy_pass_port: 8000
    proxy_pass_protocol: "http"

    influx_address: "{{ inventory_hostname }}"
    influx_port: 8086
    influx_db: galaxy
    influx_username: "influx_user"
    influx_password: "influx_pass"
  roles:
      # Fastapi that collects stats about Pulsar nodes
      - role: usegalaxy_eu.tpv_broker
        src: https://github.com/usegalaxy-eu/ansible-tpv-broker.git
```

## License

See [LICENSE.md](LICENSE.md)

