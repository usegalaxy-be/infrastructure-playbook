#!/usr/bin/env bash
# Resubmit Galaxy jobs that errored within a time window, optionally filtered by tool_id.
#
# Uses gxadmin for DB connectivity and restart-jobs mutation.
#
# Usage:
#   resubmit_failed_jobs.sh <hours> [tool_id_pattern] [--commit]
#
# Arguments:
#   hours            How far back to look (e.g. 6)
#   tool_id_pattern  Optional SQL LIKE pattern for tool_id (e.g. '__SET_METADATA__',
#                    'toolshed.g2.bx.psu.edu/repos/nml/spades/spades/%')
#   --commit         Actually restart the jobs; omit for a dry run that just prints IDs
#
# Examples:
#   # Dry run: show all errored jobs from the last 6 hours
#   ./resubmit_failed_jobs.sh 6
#
#   # Dry run: show failed __SET_METADATA__ jobs from the last 12 hours
#   ./resubmit_failed_jobs.sh 12 '__SET_METADATA__'
#
#   # Restart all errored spades jobs from the last 24 hours
#   ./resubmit_failed_jobs.sh 24 'toolshed.g2.bx.psu.edu/repos/nml/spades/spades/%' --commit

set -euo pipefail

HOURS="${1:?Usage: $0 <hours> [tool_id_pattern] [--commit]}"
TOOL_PATTERN="${2:-}"
COMMIT=""

# Shift past positional args to find --commit anywhere in remaining args
shift
shift 2>/dev/null || true
for arg in "$@"; do
  [[ "$arg" == "--commit" ]] && COMMIT="--commit"
done

# Build the WHERE clause
WHERE="state = 'error' AND create_time > now() - interval '${HOURS} hours'"
if [[ -n "$TOOL_PATTERN" ]]; then
  WHERE="${WHERE} AND tool_id LIKE '${TOOL_PATTERN}'"
fi

# Fetch matching job IDs via psql (gxadmin's connection settings apply)
JOB_IDS=$(psql -qAt -c "SELECT id FROM job WHERE ${WHERE} ORDER BY id;")

if [[ -z "$JOB_IDS" ]]; then
  echo "No matching errored jobs found in the last ${HOURS} hours."
  exit 0
fi

COUNT=$(echo "$JOB_IDS" | wc -l)
echo "Found ${COUNT} job(s):"
echo "$JOB_IDS" | tr '\n' ' '
echo

if [[ -z "$COMMIT" ]]; then
  echo "(Dry run — pass --commit to restart)"
else
  echo "$JOB_IDS" | gxadmin mutate restart-jobs --commit -
fi
