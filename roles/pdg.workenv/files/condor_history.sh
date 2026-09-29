#!/bin/bash
# Display HTCondor history with custom formatting
# Usage: condor_history.sh [-n N] [-u user] [-d description] [-w] [cluster_id]
#   -n N           Show last N jobs (default: 50)
#   -u user        Filter by owner
#   -d desc        Filter by JobDescription substring (e.g. __DATA_FETCH__)
#   -w             Wide mode: show full Cmd path instead of extracted Galaxy job ID
#   cluster_id     Show summary row for a specific cluster (or use -long for full dump)

LIMIT=50
USER_FILTER=""
DESC_FILTER=""
CLUSTER_ID=""
WIDE=0

while [[ $# -gt 0 ]]; do
    case $1 in
        -n)    LIMIT=$2; shift 2 ;;
        -u)    USER_FILTER=$2; shift 2 ;;
        -d)    DESC_FILTER=$2; shift 2 ;;
        -w)    WIDE=1; shift ;;
        [0-9]*) CLUSTER_ID=$1; shift ;;
        -h|--help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)  echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Build condor_history args
HIST_ARGS=("-backwards" "-match" "$LIMIT")
[[ -n "$USER_FILTER" ]] && HIST_ARGS+=("-submitter" "$USER_FILTER")
[[ -n "$CLUSTER_ID" ]] && HIST_ARGS=("$CLUSTER_ID")  # match overrides limit for single job

{
    echo "Cluster Status Exit Vacates CPUs Mem(G) WallTime GalaxyJob Description Worker Completed"

    condor_history "${HIST_ARGS[@]}" \
        -af ClusterId JobStatus ExitCode ExitBySignal ExitSignal NumVacates \
            RequestCpus RequestMemory RemoteWallClockTime \
            JobDescription Cmd LastRemoteHost CompletionDate \
    | awk -v desc_filter="$DESC_FILTER" -v wide="$WIDE" '
    BEGIN {
        status_map[0]="U"; status_map[1]="I"; status_map[2]="R"
        status_map[3]="X"; status_map[4]="C"; status_map[5]="H"
        status_map[6]="E"
    }
    {
        cluster   = $1
        status    = status_map[$2+0]; if (status == "") status = $2
        exitcode  = $3
        by_signal = $4   # true/false
        exitsig   = $5
        vacates   = $6
        cpus      = $7
        mem_mb    = $8
        wall_sec  = $9
        desc      = $10
        cmd       = $11
        worker    = $12
        comp_ts   = $13

        # Filter by description substring if requested
        if (desc_filter != "" && index(desc, desc_filter) == 0) next

        # Build exit column: code or Sig:N
        if (by_signal == "true")
            exit_str = "Sig:" exitsig
        else
            exit_str = exitcode

        # Memory: MB -> G with one decimal
        mem_g = sprintf("%.1f", mem_mb / 1024)

        # Wall time: seconds -> hh:mm:ss
        h = int(wall_sec / 3600)
        m = int((wall_sec % 3600) / 60)
        s = int(wall_sec % 60)
        wall_str = sprintf("%d:%02d:%02d", h, m, s)
        if (wall_sec == 0 || wall_sec == "undefined") wall_str = "-"

        # Galaxy job ID from path: .../jobs/000/671/671465/galaxy_671465.sh -> 671465
        if (wide) {
            gal_job = cmd
        } else {
            n = split(cmd, parts, "/")
            gal_job = parts[n-1]   # directory name one level up from script
            if (gal_job ~ /^[0-9]+$/) {
                # good
            } else {
                # fallback: try to match job id from filename
                match(cmd, /galaxy_([0-9]+)\.sh/, arr)
                gal_job = (arr[1] != "") ? arr[1] : "-"
            }
        }

        # Worker: strip slot prefix and fqdn suffix for brevity
        # slot1_6@vgcn-condor-worker-1-2x-0.usegalaxy.be -> worker-1-2x-0
        worker_short = worker
        sub(/^[^@]+@/, "", worker_short)           # remove slot@
        sub(/\.usegalaxy\.be$/, "", worker_short)  # remove domain
        sub(/^vgcn-condor-/, "", worker_short)     # remove common prefix
        if (worker == "undefined" || worker == "") worker_short = "-"

        # Completion timestamp
        if (comp_ts == "0" || comp_ts == "undefined") {
            comp_str = "-"
        } else {
            cmd2 = "date -d @" comp_ts " +\"%m/%d %H:%M\" 2>/dev/null"
            cmd2 | getline comp_str
            close(cmd2)
        }

        print cluster " " status " " exit_str " " vacates " " cpus " " mem_g " " wall_str " " gal_job " " desc " " worker_short " " comp_str
    }'
} | column -t | \
awk 'NR==1 {
    print $0
    sep = ""
    for (i = 1; i <= length($0); i++) sep = sep "-"
    print sep
    next
}
{
    # Color by status (column 2)
    if ($2 == "C") print "\033[32m" $0 "\033[0m"       # green  = completed
    else if ($2 == "X") print "\033[31m" $0 "\033[0m"  # red    = removed
    else if ($2 == "H") print "\033[33m" $0 "\033[0m"  # yellow = held
    else if ($2 == "R") print "\033[36m" $0 "\033[0m"  # cyan   = running
    else print $0
}'
