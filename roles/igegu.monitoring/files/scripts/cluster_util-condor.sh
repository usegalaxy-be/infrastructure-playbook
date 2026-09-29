#!/bin/bash
mem_total=$(condor_status  -autoformat TotalMemory | paste -s -d'+' | bc)
mem_remain=$(condor_status -autoformat Memory      | paste -s -d'+' | bc)
cpu_total=$(condor_status  -autoformat DetectedCpus | paste -s -d'+' | bc)
cpu_remain=$(condor_status -autoformat Cpus         | paste -s -d'+' | bc)
mem_perc=$(echo "($mem_total - $mem_remain) / $mem_total" | bc -l)
cpu_perc=$(echo "($cpu_total - $cpu_remain) / $cpu_total" | bc -l)
echo "cluster.alloc,cluster=condor cores=0$cpu_perc,memory=0$mem_perc"
