#!/usr/bin/env python3
"""Diffs guids in shed_tool_conf.xml against the previous run's snapshot,
writing newly-appeared ones out in tool_tests.py's tools_file format."""
import argparse
import xml.etree.ElementTree as ET


def read_guids(shed_tool_conf_path):
    tree = ET.parse(shed_tool_conf_path)
    return {tool.get("guid") for tool in tree.getroot().iter("tool") if tool.get("guid")}


def read_snapshot(snapshot_path):
    try:
        with open(snapshot_path) as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def write_lines(path, guids):
    with open(path, "w") as f:
        for guid in sorted(guids):
            f.write(guid + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shed-tool-conf", required=True, help="Path to the synced shed_tool_conf.xml")
    parser.add_argument("--snapshot", required=True, help="Path to the guid snapshot from the previous run")
    parser.add_argument("--output", required=True, help="Where to write newly-appeared guids (tools_file format)")
    args = parser.parse_args()

    current = read_guids(args.shed_tool_conf)
    previous = read_snapshot(args.snapshot)
    new = current - previous

    print(f"{len(current)} tools in shed_tool_conf, {len(previous)} in previous snapshot, {len(new)} new")

    write_lines(args.output, new)
    write_lines(args.snapshot, current)


if __name__ == "__main__":
    main()
