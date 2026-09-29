#!/usr/bin/env python

import argparse
import os
import sys

sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "lib")))

import galaxy.config
from galaxy.model import Dataset
from galaxy.model.mapping import init_models_from_config
from galaxy.objectstore import build_object_store_from_config
from galaxy.util.script import (
    app_properties_from_args,
    populate_config_args,
)

parser = argparse.ArgumentParser()
populate_config_args(parser)
args = parser.parse_args()


def init():
    app_properties = app_properties_from_args(args)
    config = galaxy.config.Configuration(**app_properties)

    object_store = build_object_store_from_config(config)
    model = init_models_from_config(config, object_store=object_store)
    return model, object_store


if __name__ == "__main__":
    print("Loading Galaxy model...")
    model, object_store = init()
    sa_session = model.context.current
    session = sa_session()

    set = 0
    dataset_count = session.query(model.Dataset).count()
    print(f"Processing {dataset_count} datasets...")
    percent = 0
    print(f"Completed {percent}%", end=" ")
    sys.stdout.flush()

    for i, dataset in enumerate(
        session.query(model.Dataset)
        .filter(model.Dataset.object_store_id.is_(None))
        .enable_eagerloads(False)
        .yield_per(1000)
    ):
        if dataset.state == "ok":
            if object_store.exists(dataset):
                print(i, dataset.id, dataset.extra_files_path)
                set += 1

    session.commit()
    print("\rCompleted 100%")
    print(f"#{set} datasets processed")
    object_store.shutdown()
