#!/usr/bin/env python3
"""Build an OpenFold3 query.json from a Galaxy-rendered chain specification.

The spec file has one tab-separated record per protein chain:

    molecule_type<TAB>copies<TAB>sequence<TAB>msa_path

``msa_path`` may be empty. Chain IDs are assigned sequentially (A, B, C, ...)
across all chains, expanding ``copies`` into that many chain IDs for a single
(homomeric) chain entry.
"""

import argparse
import json
import logging
import re
import string
import sys

__version__ = "0.4.0"  # Must match @TOOL_VERSION@ in macros.xml

# Allowed one-letter residue alphabets per molecule type.
RESIDUE_ALPHABETS = {
    "protein": set("ACDEFGHIKLMNPQRSTVWYXU"),
    "rna": set("ACGUXN"),
    "dna": set("ACGTXN"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)


def chain_id_generator():
    """Yield A..Z then AA, AB, ... for arbitrarily many chains."""
    for letter in string.ascii_uppercase:
        yield letter
    for first in string.ascii_uppercase:
        for second in string.ascii_uppercase:
            yield first + second


def build(spec_path, query_name, use_msa_server):
    ids = chain_id_generator()
    chains = []
    with open(spec_path) as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            fields = line.split("\t")
            if len(fields) < 3:
                raise ValueError(
                    "Malformed spec line %d: expected at least 3 tab-separated "
                    "fields, got %d" % (lineno, len(fields))
                )
            molecule_type = fields[0].strip().lower()
            copies = int(fields[1].strip())
            # Remove all whitespace/newlines a user may have pasted, then upper-case.
            sequence = re.sub(r"\s+", "", fields[2]).upper()
            msa_path = fields[3].strip() if len(fields) > 3 else ""

            if not sequence:
                raise ValueError("Empty sequence on spec line %d" % lineno)
            if copies < 1:
                raise ValueError("copies must be >= 1 on spec line %d" % lineno)
            if molecule_type not in RESIDUE_ALPHABETS:
                raise ValueError(
                    "Unsupported molecule_type '%s' on spec line %d"
                    % (molecule_type, lineno)
                )
            invalid = sorted(set(sequence) - RESIDUE_ALPHABETS[molecule_type])
            if invalid:
                raise ValueError(
                    "Invalid %s residue(s) %s on spec line %d. Allowed: %s"
                    % (
                        molecule_type,
                        "".join(invalid),
                        lineno,
                        "".join(sorted(RESIDUE_ALPHABETS[molecule_type])),
                    )
                )

            chain_ids = [next(ids) for _ in range(copies)]
            chain = {
                "molecule_type": molecule_type,
                "chain_ids": chain_ids,
                "sequence": sequence,
            }
            if msa_path:
                chain["use_msas"] = True
                chain["main_msa_file_paths"] = msa_path
                logging.info(
                    "Chain %s: using precomputed MSA %s", chain_ids, msa_path
                )
            chains.append(chain)

    if not chains:
        raise ValueError("No chains found in spec file")

    query = {"queries": {query_name: {"chains": chains}}}
    logging.info(
        "Built query '%s' with %d chain entry/entries (%d total chain IDs), "
        "MSA server=%s",
        query_name,
        len(chains),
        sum(len(c["chain_ids"]) for c in chains),
        use_msa_server,
    )
    return query


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="Tab-separated chain spec")
    parser.add_argument("--name", required=True, help="Query name (history key)")
    parser.add_argument(
        "--use-msa-server",
        default="true",
        help="Whether ColabFold MSA server is used (informational only)",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="Where to write query.json ('-' for stdout, the default)",
    )
    args = parser.parse_args()

    try:
        query = build(args.spec, args.name, args.use_msa_server)
    except ValueError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    if args.output == "-":
        json.dump(query, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        with open(args.output, "w") as fh:
            json.dump(query, fh, indent=2)
            fh.write("\n")
        logging.info("Wrote query to %s", args.output)


if __name__ == "__main__":
    main()
