#!/usr/bin/env bash
# perf_check.sh — Galaxy performance bottleneck diagnostics
#
# Usage:
#   ./scripts/perf_check.sh [tool_id_pattern]
#
# Defaults to 'protein_calculator' if no argument given.
# Runs NFS benchmarks, conda activation timing, and DB job timing queries.
# Must be run on the Galaxy headnode. DB auth is handled via ~/.pgpass.
#
# Sections:
#   1. NFS mount options
#   2. NFS stat() latency (NFS vs local)
#   3. NFS write throughput (tmp mount)
#   4. Conda env activation timing
#   5. Python import timing (top slow imports)
#   6. DB: job queue_s / running_s / tool_runtime_s breakdown
#   7. Summary

set -uo pipefail

TOOL_PATTERN="${1:-protein_calculator}"

# ---------------------------------------------------------------------------
# Auto-detect environment (test vs prod) based on hostname
# ---------------------------------------------------------------------------
HOSTNAME="$(hostname -f)"
if [[ "$HOSTNAME" == *test* ]]; then
    NFS_BASE="/srv/galaxy_test/shared"
    CONDA_BASE="$NFS_BASE/dependencies/miniconda3"
    VENV_PATH="$NFS_BASE/venv"
    TMP_PATH="$NFS_BASE/tmp"
    GALAXY_DB_NAME="galaxy_test_db"
    ENV_LABEL="test"
else
    NFS_BASE="/srv/galaxy/shared"
    CONDA_BASE="$NFS_BASE/etc/dependencies/miniconda3"
    VENV_PATH="$NFS_BASE/etc/venv"
    TMP_PATH="$NFS_BASE/tmp"
    GALAXY_DB_NAME="galaxy_prod_db"
    ENV_LABEL="prod"
fi

# Override these if your setup differs
# CONDA_BASE=/srv/galaxy/shared/etc/dependencies/miniconda3
# VENV_PATH=/srv/galaxy/shared/etc/venv
# TMP_PATH=/srv/galaxy/shared/tmp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
section() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $1"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }
ok()      { echo "  [OK]  $*"; }
warn()    { echo "  [!!]  $*"; }
info()    { echo "        $*"; }
skip()    { echo "  [--]  $* (skipped — path not found)"; }

# rate VAL GOOD_THRESH BAD_THRESH DIRECTION
# DIRECTION: "lower" (lower=better, e.g. latency) or "higher" (higher=better, e.g. throughput)
rate() {
    local val="$1" good="$2" bad="$3" dir="${4:-lower}"
    [[ "$val" == "N/A" ]] && { echo "N/A"; return; }
    if [[ "$dir" == "lower" ]]; then
        (( $(echo "$val < $good" | bc -l) )) && echo "GOOD" && return
        (( $(echo "$val < $bad"  | bc -l) )) && echo "AVG"  && return
        echo "BAD"
    else
        (( $(echo "$val > $good" | bc -l) )) && echo "GOOD" && return
        (( $(echo "$val > $bad"  | bc -l) )) && echo "AVG"  && return
        echo "BAD"
    fi
}

rating_symbol() {
    case "$1" in
        GOOD) echo "[OK] " ;;
        AVG)  echo "[~~] " ;;
        BAD)  echo "[!!] " ;;
        *)    echo "[--] " ;;
    esac
}

# Summary accumulators (N/A = not measured)
SUM_STAT_P50="N/A";       SUM_STAT_UNIT="ms"
SUM_WRITE_MBPS="N/A";     SUM_WRITE_UNIT="MB/s"
SUM_CONDA_S="N/A";        SUM_CONDA_UNIT="s"
SUM_IMPORT_S="N/A";       SUM_IMPORT_UNIT="s"
SUM_QUEUE_AVG="N/A";      SUM_QUEUE_UNIT="s"
SUM_OVERHEAD_AVG="N/A";   SUM_OVERHEAD_UNIT="s"
CONDA_ENV_PATH=""

# ---------------------------------------------------------------------------
# Section 1: NFS mount options
# ---------------------------------------------------------------------------
section "1. NFS mount options ($ENV_LABEL)"
info "Looking for actimeo, noac on client side:"
nfsstat -m 2>/dev/null | awk '
    /^[^ ]/ { mount=$0 }
    /Flags:/ {
        flags=$0
        has_noac   = (flags ~ /noac/)
        has_actimeo= (flags ~ /actimeo/)
        printf "  %-45s", mount
        if (has_noac)         printf " [!!] noac set — attribute caching DISABLED"
        else if (has_actimeo) printf " [OK] actimeo configured"
        else                  printf " [OK] default actimeo (NFSv3: 3-60s)"
        printf "\n"
    }
' || warn "nfsstat not available"

# ---------------------------------------------------------------------------
# Section 2: stat() latency — NFS vs local
# ---------------------------------------------------------------------------
section "2. NFS stat() latency"

STAT_TARGET=""
for candidate in \
    "$VENV_PATH/lib/python3.9/site-packages/galaxy/__init__.py" \
    "$VENV_PATH/lib/python3.11/site-packages/galaxy/__init__.py" \
    "$VENV_PATH/lib/python3.12/site-packages/galaxy/__init__.py"; do
    [[ -f "$candidate" ]] && { STAT_TARGET="$candidate"; break; }
done
[[ -z "$STAT_TARGET" ]] && STAT_TARGET="$(find "$VENV_PATH" -name "*.py" -type f 2>/dev/null | head -1)"

if [[ -n "$STAT_TARGET" ]]; then
    info "Target: $STAT_TARGET"
    _STAT_TMP=$(mktemp)
    python3 -c "
import os, time, statistics
path = '$STAT_TARGET'
times = []
for _ in range(2000):
    os.stat(path)
    t0 = time.perf_counter()
    os.stat(path)
    times.append((time.perf_counter() - t0) * 1000)
s = sorted(times)
p50 = statistics.median(times)
p95 = s[int(len(s)*0.95)]
p99 = s[int(len(s)*0.99)]
print(f'  NFS   stat(): p50={p50:.3f}ms  p95={p95:.3f}ms  p99={p99:.3f}ms')
label = 'OK  (attribute cache working)' if p50 < 0.5 else 'WARNING  (cache miss or noac?)' if p50 < 2 else 'CRITICAL (no caching / high latency)'
print(f'  -> {label}')
open('$_STAT_TMP', 'w').write(f'{p50:.3f}')
"
    SUM_STAT_P50=$(cat "$_STAT_TMP" 2>/dev/null || echo "N/A")
    rm -f "$_STAT_TMP"
else
    skip "venv stat() test (no .py file found under $VENV_PATH)"
fi

info "Local baseline:"
python3 -c "
import os, time, statistics
import os.path as _p
path = _p.__file__
times = []
for _ in range(2000):
    os.stat(path)
    t0 = time.perf_counter()
    os.stat(path)
    times.append((time.perf_counter() - t0) * 1000)
s = sorted(times)
print(f'  local stat(): p50={statistics.median(times):.3f}ms  p95={s[int(len(s)*0.95)]:.3f}ms  p99={s[int(len(s)*0.99)]:.3f}ms')
"

# ---------------------------------------------------------------------------
# Section 3: NFS write throughput (tmp mount)
# ---------------------------------------------------------------------------
section "3. NFS write throughput"
SUM_WRITE_MBPS="N/A"
# Prefer the tmp mount (dedicated job scratch); fall back to database mount
WRITE_TARGET=""
for candidate in "$TMP_PATH" "$NFS_BASE/database" "$NFS_BASE"; do
    [[ -d "$candidate" && -w "$candidate" ]] && { WRITE_TARGET="$candidate"; break; }
done
if [[ -n "$WRITE_TARGET" ]]; then
    PERF_FILE="$WRITE_TARGET/perf_check_$$"
    info "Writing 256 MB to $WRITE_TARGET with fdatasync ..."
    result=$(dd if=/dev/zero of="$PERF_FILE" bs=1M count=256 conv=fdatasync 2>&1 | tail -1)
    rm -f "$PERF_FILE"
    echo "  $result"
    SUM_WRITE_MBPS=$(echo "$result" | grep -oP '[\d.]+ MB/s' | grep -oP '[\d.]+' || echo "N/A")
    case "$(rate "${SUM_WRITE_MBPS}" 80 30 higher)" in
        GOOD) ok "Throughput looks good" ;;
        AVG)  info "Moderate throughput — sync export confirmed, acceptable for small outputs" ;;
        BAD)  warn "Below 30 MB/s — NFS sync export impacting job working dir writes" ;;
    esac
else
    skip "write throughput (no writable NFS path found under $NFS_BASE)"
fi

# ---------------------------------------------------------------------------
# Section 4: Conda activation timing
# ---------------------------------------------------------------------------
section "4. Conda activation timing"

if [[ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
    skip "conda activation ($CONDA_BASE/etc/profile.d/conda.sh not found)"
else
    if [[ -d "$CONDA_BASE/envs" ]]; then
        CONDA_ENV_PATH=$(ls -dt "$CONDA_BASE/envs"/*/ 2>/dev/null | head -1 || true)
        info "Using most recently modified conda env (override CONDA_ENV_PATH to specify):"
        info "$CONDA_ENV_PATH"
    fi

    if [[ -n "$CONDA_ENV_PATH" && -d "$CONDA_ENV_PATH" ]]; then
        info "File count in env:"
        find "$CONDA_ENV_PATH" -type f 2>/dev/null | wc -l | awk '{print "  " $1 " files"}'

        info "Directory walk time (simulates activation probing):"
        { time find "$CONDA_ENV_PATH" -type f > /dev/null 2>&1; } 2>&1 | grep real | awk '{print "  " $0}' || true

        info "Full activation + python startup:"
        TIME_OUTPUT=$({ time bash -c "
            source '$CONDA_BASE/etc/profile.d/conda.sh'
            conda activate '$CONDA_ENV_PATH'
            python -c 'import sys'
        " > /dev/null 2>&1; } 2>&1 | grep real || echo "real 0m0.000s")
        echo "  $TIME_OUTPUT"
        # Parse "real 0m5.492s" → seconds
        SUM_CONDA_S=$(echo "$TIME_OUTPUT" | awk '/real/{gsub(/[ms]/," ",$2); split($2,a," "); printf "%.1f", a[1]*60+a[2]}' || echo "N/A")
        case "$(rate "${SUM_CONDA_S}" 5 15 lower)" in
            GOOD) ok "Conda activation fast" ;;
            AVG)  info "Conda activation moderate — expected on NFS with many small files" ;;
            BAD)  warn "Slow conda activation (>${SUM_CONDA_S}s) — large env on NFS, consider async export or local cache" ;;
        esac
    else
        skip "conda env timing (no envs found under $CONDA_BASE/envs)"
    fi
fi

# ---------------------------------------------------------------------------
# Section 5: Python import timing (top slow imports)
# ---------------------------------------------------------------------------
section "5. Python import timing (top slowest modules)"

if [[ -n "${CONDA_ENV_PATH:-}" && -d "$CONDA_ENV_PATH" ]]; then
    info "Running python -X importtime inside the conda env ..."
    IMPORT_OUTPUT=$(bash -c "
        source '$CONDA_BASE/etc/profile.d/conda.sh'
        conda activate '$CONDA_ENV_PATH' 2>/dev/null
        python -X importtime -c '
import sys
for mod in [\"pandas\",\"plotly\",\"Bio.SeqIO\",\"jinja2\",\"numpy\",\"requests\"]:
    try:
        __import__(mod)
    except ImportError:
        pass
' 2>&1
    " | awk -F'|' '
    NF==3 {
        gsub(/ /,"",$2)
        if ($2+0 > 50000) printf "%8.3fs  %s\n", $2/1e6, $3
    }' | sort -rn | head -15 || true)
    echo "$IMPORT_OUTPUT"
    SUM_IMPORT_S=$(echo "$IMPORT_OUTPUT" | head -1 | awk '{print $1}' | tr -d 's' || echo "N/A")
    [[ -z "$SUM_IMPORT_S" ]] && SUM_IMPORT_S="N/A"
else
    info "No conda env found; showing Python stdlib startup cost only:"
    IMPORT_OUTPUT=$(python3 -X importtime -c 'import os, sys, re' 2>&1 | \
        awk -F'|' 'NF==3{gsub(/ /,"",$2); if($2+0>50000) printf "%8.3fs  %s\n",$2/1e6,$3}' | \
        sort -rn | head -10 || true)
    echo "$IMPORT_OUTPUT"
    SUM_IMPORT_S=$(echo "$IMPORT_OUTPUT" | head -1 | awk '{print $1}' | tr -d 's' || echo "N/A")
    [[ -z "$SUM_IMPORT_S" ]] && SUM_IMPORT_S="N/A"
fi

# ---------------------------------------------------------------------------
# Section 6: DB job timing breakdown
# ---------------------------------------------------------------------------
section "6. DB job timing — '$TOOL_PATTERN' (last 10 completed jobs)"

DB_OK=false
if psql --no-align --tuples-only -c "SELECT 1" > /dev/null 2>&1; then
    DB_OK=true
    psql --no-align --tuples-only -c "
SELECT
    j.id,
    to_char(j.create_time, 'MM-DD HH24:MI:SS')                       AS submitted,
    round(EXTRACT(EPOCH FROM (
        MIN(CASE WHEN jst.state='running' THEN jst.create_time END) - j.create_time
    ))::numeric, 1)                                                    AS queue_s,
    round(EXTRACT(EPOCH FROM (
        MIN(CASE WHEN jst.state='ok' THEN jst.create_time END) -
        MIN(CASE WHEN jst.state='running' THEN jst.create_time END)
    ))::numeric, 1)                                                    AS running_s,
    round((
        MAX(CASE WHEN n.metric_name='end_epoch'   THEN n.metric_value END) -
        MAX(CASE WHEN n.metric_name='start_epoch' THEN n.metric_value END)
    )::numeric, 1)                                                     AS tool_runtime_s
FROM job j
JOIN job_state_history jst ON jst.job_id = j.id
LEFT JOIN job_metric_numeric n
       ON n.job_id = j.id AND n.plugin = 'core'
WHERE j.tool_id LIKE '%${TOOL_PATTERN}%'
GROUP BY j.id
HAVING MAX(CASE WHEN jst.state='ok' THEN jst.create_time END) IS NOT NULL
ORDER BY j.id DESC
LIMIT 10;
" | awk -F'|' '
BEGIN {
    printf "  %-8s  %-16s  %8s  %10s  %14s  %16s\n",
        "job_id","submitted","queue_s","running_s","tool_runtime_s","overhead_s"
    printf "  %s\n", "--------  ----------------  --------  ----------  --------------  ----------------"
}
NF==5 {
    overhead = ($4 != "" && $5 != "") ? $4 - $5 : "N/A"
    fmt = (overhead != "N/A" && overhead+0 > 10) ? "  %-8s  %-16s  %8s  %10s  %14s  %16s  <<\n" \
                                                  : "  %-8s  %-16s  %8s  %10s  %14s  %16s\n"
    printf fmt, $1, $2, $3, $4, $5, (overhead == "N/A" ? "N/A" : sprintf("%.1f", overhead))
}'

    echo
    info "Columns:"
    info "  queue_s        = job created → running  (Galaxy handler + Condor/local_runner dispatch)"
    info "  running_s      = job running → ok        (conda activate + tool + output collection)"
    info "  tool_runtime_s = start_epoch → end_epoch (actual shell wall time, from core metrics)"
    info "  overhead_s     = running_s - tool_runtime_s  (Galaxy pre/post-job processing)"
    info "  <<             = overhead_s > 10s (flagged for investigation)"

    # Fetch averages for summary (single-row result, excludes queue outliers > 300s)
    read SUM_QUEUE_AVG SUM_OVERHEAD_AVG < <(psql --no-align --tuples-only -c "
SELECT
    round(avg(queue_s)::numeric, 1),
    round(avg(overhead_s)::numeric, 1)
FROM (
    SELECT
        EXTRACT(EPOCH FROM (
            MIN(CASE WHEN jst.state='running' THEN jst.create_time END) - j.create_time
        )) AS queue_s,
        EXTRACT(EPOCH FROM (
            MIN(CASE WHEN jst.state='ok' THEN jst.create_time END) -
            MIN(CASE WHEN jst.state='running' THEN jst.create_time END)
        )) - (
            MAX(CASE WHEN n.metric_name='end_epoch'   THEN n.metric_value END) -
            MAX(CASE WHEN n.metric_name='start_epoch' THEN n.metric_value END)
        ) AS overhead_s
    FROM job j
    JOIN job_state_history jst ON jst.job_id = j.id
    LEFT JOIN job_metric_numeric n ON n.job_id = j.id AND n.plugin = 'core'
    WHERE j.tool_id LIKE '%${TOOL_PATTERN}%'
    GROUP BY j.id
    HAVING MAX(CASE WHEN jst.state='ok' THEN jst.create_time END) IS NOT NULL
    ORDER BY j.id DESC
    LIMIT 10
) sub
WHERE queue_s < 300;
" 2>/dev/null | tr '|' ' ' || echo "N/A N/A")
else
    warn "psql failed — check ~/.pgpass and PGHOST/PGUSER env vars"
fi

# ---------------------------------------------------------------------------
# Section 7: Summary
# ---------------------------------------------------------------------------
section "7. Summary ($ENV_LABEL — tool: $TOOL_PATTERN)"

printf "  %-30s  %10s  %6s  %s\n" "Metric" "Value" "Unit" "Rating"
printf "  %s\n" "------------------------------  ----------  ------  ------"

# NFS stat latency
R=$(rate "$SUM_STAT_P50" 0.1 1.0 lower)
printf "  %-30s  %10s  %6s  %s %s\n" "NFS stat() p50 latency" "$SUM_STAT_P50" "$SUM_STAT_UNIT" "$(rating_symbol "$R")" "$R"

# NFS write throughput
R=$(rate "$SUM_WRITE_MBPS" 80 30 higher)
printf "  %-30s  %10s  %6s  %s %s\n" "NFS write throughput (tmp)" "$SUM_WRITE_MBPS" "$SUM_WRITE_UNIT" "$(rating_symbol "$R")" "$R"

# Conda activation
R=$(rate "$SUM_CONDA_S" 5 15 lower)
printf "  %-30s  %10s  %6s  %s %s\n" "Conda activation time" "$SUM_CONDA_S" "$SUM_CONDA_UNIT" "$(rating_symbol "$R")" "$R"

# Top Python import
R=$(rate "$SUM_IMPORT_S" 1.0 5.0 lower)
printf "  %-30s  %10s  %6s  %s %s\n" "Slowest Python import" "$SUM_IMPORT_S" "$SUM_IMPORT_UNIT" "$(rating_symbol "$R")" "$R"

# Job queue time (avg)
R=$(rate "$SUM_QUEUE_AVG" 5 15 lower)
printf "  %-30s  %10s  %6s  %s %s\n" "Job queue time (avg)" "$SUM_QUEUE_AVG" "$SUM_QUEUE_UNIT" "$(rating_symbol "$R")" "$R"

# Galaxy pre/post overhead (avg)
R=$(rate "$SUM_OVERHEAD_AVG" 5 15 lower)
printf "  %-30s  %10s  %6s  %s %s\n" "Galaxy pre/post overhead (avg)" "$SUM_OVERHEAD_AVG" "$SUM_OVERHEAD_UNIT" "$(rating_symbol "$R")" "$R"

echo
info "Thresholds:  GOOD / AVG / BAD"
info "  stat() latency      <0.1ms / <1ms  / >=1ms"
info "  write throughput    >80    / >30   / <=30 MB/s"
info "  conda activation    <5s    / <15s  / >=15s"
info "  slowest import      <1s    / <5s   / >=5s"
info "  job queue time      <5s    / <15s  / >=15s"
info "  Galaxy overhead     <5s    / <15s  / >=15s"
echo
echo "Done."
