#!/bin/bash
set -euo pipefail

# tmux session initialisation for galaxy-admin
# Replaces galaxy-byobu.sh — pure tmux, no byobu layer.
# Prefix key: Ctrl+a  (see ~/.tmux.conf)
#
# Usage:
#   ~/galaxy-session.sh          # start fresh and attach
#   ~/galaxy-session.sh --attach # attach to existing session if present
#
# Logs:
#   ~/tmux-logs/*.log  — rotated daily, kept 7 days (see /etc/logrotate.d/tmux-logs)
#   Note: the monitoring window runs htop interactively and is not logged
#   (escape codes make the output unreadable as text).

SESSION="galaxy-admin"
SCROLLBACK_LINES=50000
LOG_DIR="$HOME/tmux-logs"

mkdir -p "$LOG_DIR"

# --attach: reuse an existing session rather than killing it
if [[ "${1:-}" == "--attach" ]]; then
    tmux attach-session -t "$SESSION" 2>/dev/null && exit 0
    echo "No session named '$SESSION' found, starting fresh..."
fi

# Kill any existing session (prevents duplicate sessions and memory buildup)
tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"

# ----------------------------------------------------------------
# Session creation
# ----------------------------------------------------------------

# Start a new detached session with the "ansible" window
tmux new-session -d -s "$SESSION" -n ansible

# Apply scrollback to all future windows in this session
tmux set-option -t "$SESSION" history-limit "$SCROLLBACK_LINES"

# ansible window — deployment repo (main pane) + two extra shells in repo root
tmux send-keys -t "$SESSION:ansible" \
    "cd ~/usegalaxy-be-admin/ansible-galaxy-deployment/ansible-deployment" C-m
tmux pipe-pane -t "$SESSION:ansible" -o "cat >> $LOG_DIR/ansible.log"

tmux split-window -t "$SESSION:ansible" -h -c "$HOME/usegalaxy-be-admin/ansible-galaxy-deployment"
tmux split-window -t "$SESSION:ansible" -v -c "$HOME/usegalaxy-be-admin/ansible-galaxy-deployment"
tmux select-pane -t "$SESSION:ansible.1"

# test window — persistent SSH to test galaxy
tmux new-window -t "$SESSION" -n test
tmux send-keys -t "$SESSION:test" "while true; do ssh UseGalaxyTest; sleep 5; done" C-m
tmux pipe-pane -t "$SESSION:test" -o "cat >> $LOG_DIR/test.log"

# prod window — persistent SSH to prod galaxy
tmux new-window -t "$SESSION" -n prod
tmux send-keys -t "$SESSION:prod" "while true; do ssh UseGalaxyDup; sleep 5; done" C-m
tmux pipe-pane -t "$SESSION:prod" -o "cat >> $LOG_DIR/prod.log"

# condor window
tmux new-window -t "$SESSION" -n condor
tmux send-keys -t "$SESSION:condor" \
    "while true; do ssh vgcn-condor-worker-1-2x-0-usegalaxy-be; sleep 5; done" C-m
tmux pipe-pane -t "$SESSION:condor" -o "cat >> $LOG_DIR/condor.log"

# pulsar-vib window
tmux new-window -t "$SESSION" -n pulsar-vib
tmux send-keys -t "$SESSION:pulsar-vib" \
    "while true; do ssh vgcn-pulsar-central-manager-vib; sleep 5; done" C-m
tmux pipe-pane -t "$SESSION:pulsar-vib" -o "cat >> $LOG_DIR/pulsar-vib.log"

# monitoring window — interactive htop on prod (not logged, output is not plain text)
tmux new-window -t "$SESSION" -n monitoring
tmux send-keys -t "$SESSION:monitoring" \
    "while true; do ssh -t UseGalaxyDup 'htop'; sleep 5; done" C-m

# Land on the ansible window
tmux select-window -t "$SESSION:ansible"

# Attach
tmux attach-session -t "$SESSION"
