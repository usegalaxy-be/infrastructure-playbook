# Ansible role: pulsar-metric-collection

A role that either installs a:
- producer script that sends htcondor stats to an amqp queue on the Pulsar side
- consumer script that collects the metrics from the amqp queue on the Galaxy side, aggregates them and sends them to an InfluxDB

Note: the consumer script needs read access to the galaxy `job_conf`

## Requirements

No specific requirements, the role is self-contained.

## Role variables

Role variables are documented in the forms of comments on [defaults/main.yml](defaults/main.yml)

## Dependencies

None.

## Example Playbooks

### Deployment of the consumer

```yaml
---
- name: Install and configure a pulsar metric consumer script
  hosts: all
  vars:
    pulsar_metric_role: consumer
    consumer_influx_address: ""
    consumer_influx_port: 8086
    consumer_influx_db: galaxy
    consumer_influx_username: "influx_user"
    consumer_influx_password: "influx_pass"
    consumer_influx_measurement: "htcondor_cluster_usage"
    pulsar_consumer_dir: "/opt/pulsar_metrics"
    consumer_venv_dir: "{{ pulsar_consumer_dir }}/venv"
    consumer_galaxy_job_conf: "{{ galaxy_config_dir }}/galaxy.yml"
    tpv_destinations_conf: "{{ tpv_mutable_dir }}/destinations.yml"

    consumer_energy_measurement: "pulsar_carbon_intensity"
    energy_auth_token: "secret_token"

    consumer_destinations:
      - pulsar_de02
      - pulsar_cz01 
      - pulsar_it01
    telegraf_agent_output:
      - type: influxdb
        config:
          - urls = ["{{ consumer_influx_address }}:{{ consumer_influx_port }}"]
          - username = "{{ consumer_influx_username }}"
          - password = "{{ consumer_influx_password }}"
          - database = "{{ consumer_influx_db }}"
          - timeout = "10s"
        tagpass:
          - destination = ["esg"]
    telegraf_plugins_extra:
      # telegraf plugin for sending pulsar metrics to influx
      pular_monitor:
        plugin: exec
        config:
          - commands = [
            "{{ consumer_venv_dir }}/bin/python {{ pulsar_consumer_dir }}/pulsar_metric_consumer.py {{ consumer_galaxy_job_conf }}",
            ]
          - timeout = "10s"
          - data_format = "influx"
          - interval = "1m"
        tags:
          - destination = "esg"

  roles:
      - role: ansible-pulsar-util
      - role: dj-wasabi.telegraf
```

### Deployment of the producer

Please pay special attention to the value of these two variables
in the [defaults/main.yml](defaults/main.yml) file
* `pulsar_root`
* `pulsar_data_path`

Their value should be consistent with the ones configured as part
of the deployment of pulsar via the
[https://github.com/usegalaxy-eu/pulsar-deployment](https://github.com/usegalaxy-eu/pulsar-deployment)
repository.

```yaml
---
- name: Install and configure a pulsar metric producer script
  hosts: all
  vars:
    pulsar_metric_role: producer
    pulsar_root: "/opt/pulsar"
    pulsar_data_path: "/data/share"

  roles:
      - role: ansible-pulsar-util
```

## License

See [LICENSE.md](LICENSE.md)
