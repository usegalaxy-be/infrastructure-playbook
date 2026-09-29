import json

try:
    import htcondor
except ImportError:
    import htcondor2 as htcondor


def collect_metrics():

    collector = htcondor.Collector()

    # get CPUs and Mem from unclaimed slots and group them in a dictionary
    unclaimed_slots_summary = {}
    metrics = []
    for slot in collector.query(htcondor.AdTypes.Startd, projection=['State', 'Cpus', 'Memory']):

        cpu_mem_combo = json.dumps({key: slot[key] for key in ['Cpus', 'Memory']})

        if slot['State'] == 'Unclaimed':
            if cpu_mem_combo not in unclaimed_slots_summary:
                unclaimed_slots_summary[cpu_mem_combo] = 1
            else:
                unclaimed_slots_summary[cpu_mem_combo] += 1

    influx_msmt = "htcondor_cluster_usage"

    for unclaimed_slot_type in unclaimed_slots_summary:
        classad = json.loads(unclaimed_slot_type)

        uniq_tag = f"{slot['Cpus']}c_{slot['Memory']}m"

        influx_tagset = f"unclaimed_tag={uniq_tag}"
        influx_fieldset = f"count={unclaimed_slots_summary[unclaimed_slot_type]},unclaimed_cpus={classad['Cpus']},unclaimed_memory={classad['Memory']}"

        metrics.append((influx_msmt, influx_tagset, influx_fieldset))

    return metrics
