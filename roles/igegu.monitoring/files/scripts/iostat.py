#!/usr/bin/env python
import datetime
import subprocess
import yaml

from influxdb import InfluxDBClient
time = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

secrets = yaml.load(open('secret.yml', 'r'))


def parse_iostat(flags):
    results = subprocess.check_output(['iostat'] + flags, env={'LC_ALL': 'C'})
    headers = None
    for line in results.split('\n'):
        if headers and len(line.strip()) > 0:
            parts = line.strip().split()
            k1 = parts[0]
            for (k2, v) in zip(headers, parts[1:]):
                yield {
                    'measurement': 'iostat',
                    'time': time,
                    'fields': {
                        'value': float(v)
                    },
                    'tags': {
                        'device': k1,
                        'metric': k2.replace('%', 'percent_'),
                    }
                }

        if line.startswith('Filesystem') or line.startswith('Device'):
            headers = line.strip().split()[1:]
            headers = [x.replace('/', '_') for x in headers]


if __name__ == '__main__':
    client = InfluxDBClient(**secrets['influxdb'])
    # client.create_database(secrets['influxdb']['database'])
    client.write_points(parse_iostat(['-x']))
    #client.write_points(parse_iostat(['-n']))
    client.write_points(parse_iostat(['-N']))
