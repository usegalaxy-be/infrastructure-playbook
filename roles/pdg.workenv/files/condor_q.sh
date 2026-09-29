#!/bin/bash
# Display HTCondor queue with custom formatting
# Columns: Cluster, Owner, Status, CPUs, Memory, RemoteHost, JobDescription, Command, Submitted

# Collect all data first, then format with column -t for dynamic alignment
{
    # Print header
    echo "Cluster Owner Status CPUs Memory RemoteHost JobDescription Command Submitted"
    
    # Get job data and format it
    condor_q -nobatch -af ClusterId Owner JobStatus RequestCpus RequestMemory RemoteHost JobDescription Cmd QDate | \
    awk 'BEGIN {status_map[0]="U"; status_map[1]="I"; status_map[2]="R"; status_map[3]="X"; status_map[4]="C"; status_map[5]="H"; status_map[6]="E"; status_map[7]="S"}
    {
        # Convert Unix timestamp to human readable date
        cmd = "date -d @" $9 " +\"%m/%d %H:%M\" 2>/dev/null || date -r " $9 " +\"%m/%d %H:%M\" 2>/dev/null"
        cmd | getline date_str
        close(cmd)
        
        # Map status number to letter
        status = status_map[$3+0]
        if (status == "") status = $3
        
        # Build output line (no color codes yet - we add those after column alignment)
        print $1 " " $2 " " status " " $4 " " $5 " " $6 " " $7 " " $8 " " date_str
    }'
} | column -t | \
awk 'NR==1 {
    # Print header
    print $0
    # Print separator line based on header length
    separator = ""
    for (i = 1; i <= length($0); i++) {
        separator = separator "-"
    }
    print separator
    next
}
{
    # Color running jobs green (status is in column 3)
    if ($3 == "R") print "\033[32m" $0 "\033[0m"
    else print $0
}'
