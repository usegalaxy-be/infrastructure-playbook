"""This script is a producer that publishes condor status details to the queue"""

import argparse
import os
import re
import sys
import time

from kombu import Connection, Exchange, Producer, Queue

import yaml


def get_amqp_url(pulsar_app_file: str) -> None:
    """
    Parse the Pulsar app.yml file and extract the AMQP URL.
    """
    # Check the existence of the job_conf.yml file
    if not os.path.exists(pulsar_app_file):
        print(f"File {pulsar_app_file} does not exist.")
        return None

    with open(pulsar_app_file, "r") as file:
        app_conf = yaml.safe_load(file)
        amqp_url = app_conf['message_queue_url']

    return amqp_url


def get_vhost_name(amqp_url: str) -> str:
    """
    Parse the AMQP URL to extract the vhost name.
    """
    vhost = amqp_url.split("/")[-1].split("?")[0]
    return vhost


def connect_to_queue(amqp_url: str) -> Connection:
    """
    Connect to the AMQP queue using the provided URL.
    """
    # With try and except block, connect to the AMQP queue using the provided URL and manage the error if the connection fails
    try:
        connection = Connection(amqp_url)
        connection.ensure_connection(max_retries=3)
        return connection
    except Exception as e:
        print(f"Error connecting to the AMQP queue: {e}")
        return None


def get_condor_cluster_utilisation() -> list:
    """
    Get condor metrics from scheduler python bindings
    """

    from htcondor_cluster_util import collect_metrics

    condor_metrics = collect_metrics()

    return condor_metrics


def produce_message(amqp_url: str, metrics: list) -> None:
    """
    Produce and publish messages to the queue.
    """
    connection = connect_to_queue(amqp_url)

    if connection:
        vhost = get_vhost_name(amqp_url)
        routing_key = f"{vhost}-condor"
        channel = connection.channel()
        exchange = Exchange(f"{vhost}-condor-exchange", type="direct")
        producer = Producer(exchange=exchange, channel=channel, routing_key=routing_key)
        queue = Queue(name=f"{vhost}-condor-stats0", exchange=exchange, routing_key=routing_key)
        queue.maybe_bind(connection)
        queue.declare()

        # Add destination to metrics
        processed_metrics = []
        for metr in metrics:
            processed_metrics.append(f"{metr[0]},destination_id=\"{vhost}\",{metr[1]} {metr[2]}")

        producer.publish(
            {"metrics": processed_metrics},
            exchange=exchange,
            routing_key=routing_key,
            declare=[queue],
            serializer="json"
        )
        connection.release()


def main(pulsar_app_file: str, cluster_type: str) -> None:

    amqp_url = get_amqp_url(pulsar_app_file)

    if not amqp_url:
        print("No Pulsar url found in the pulsar configuration file.")
        sys.exit(1)

    metrics = []
    if cluster_type == "htcondor":
        # Get the condor status
        metrics = get_condor_cluster_utilisation()
    else:
        raise RuntimeError(f"Unsupported cluster type {cluster_type}")

    # Create and publish message
    produce_message(amqp_url, metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce messages to AMQP queues.")
    parser.add_argument("pulsar_app_file", type=str, help="Path to the Pulsar app configuration file (YAML).")
    parser.add_argument("cluster_type", type=str, default="htcondor", choices=["htcondor"], help="Type of HPC cluster to gather metrics from (only htcondor at the moment, Slurm could be implemented).")
    args = parser.parse_args()

    main(args.pulsar_app_file, args.cluster_type)
