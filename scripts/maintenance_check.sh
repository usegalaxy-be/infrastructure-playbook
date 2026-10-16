#!/usr/bin/env bash
# Maintenance mode check, through the proxy. Run from the loginnode (internal network).
#
#   scripts/maintenance_check.sh [site] [proxy_ip]
#   scripts/maintenance_check.sh usegalaxy.be 10.113.3.5
#
# Shows what users get, and whether Galaxy answers through the proxy with the
# maintenance bypass, then what to do: switch maintenance on, keep it on, or
# switch it off once the job healthcheck passes. Exit 0 when nothing is wrong
# for users or Galaxy answers behind the maintenance page, 1 otherwise.
set -u
site=${1:-usegalaxy.be}
proxy=${2:-10.113.3.5}
resolve=(--resolve "$site:443:$proxy")
bypass=(-H "X-Maintenance-Bypass: 1")

code() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

page=$(code https://usegalaxy-be.github.io/maintenance)
users=$(code "${resolve[@]}" "https://$site/")
front=$(code "${resolve[@]}" "${bypass[@]}" "https://$site/")
version=$(curl -s --max-time 20 "${resolve[@]}" "${bypass[@]}" "https://$site/api/version")
api=$(code "${resolve[@]}" "${bypass[@]}" "https://$site/api/version")

case $users in
    503) users_text="maintenance page" ;;
    200) users_text="Galaxy" ;;
    000) users_text="no answer from the proxy" ;;
    *)   users_text="error" ;;
esac

echo "Site $site through proxy $proxy"
echo "  maintenance page published:  $page"
echo "  users get:                   $users ($users_text)"
echo "  Galaxy front page (bypass):  $front"
echo "  Galaxy API (bypass):         $api $version"

galaxy_ok=false
[[ $front == 200 && $api == 200 ]] && galaxy_ok=true

if [[ $users == 503 ]]; then
    if $galaxy_ok; then
        echo "Maintenance mode is on and Galaxy answers behind it. Run the job healthcheck, then switch maintenance off:"
        echo "  ansible-playbook playbooks/daily/daily-galaxy-healthcheck.yml --limit $site"
        exit 0
    fi
    echo "Maintenance mode is on and Galaxy does not answer yet: keep it on."
    exit 1
fi
if [[ $users == 200 ]]; then
    echo "Maintenance mode is off and users get Galaxy."
    [[ $page != 200 ]] && echo "The maintenance page is not published ($page): fix it before the next window."
    exit 0
fi
if [[ $users == 000 ]]; then
    echo "No answer from proxy $proxy: maintenance mode cannot help, the proxy serves the page. Check the proxy and its port forwarding."
elif [[ $page == 200 ]]; then
    echo "Users get errors: switch maintenance mode on for $site."
else
    echo "Users get errors, and the maintenance page is not published ($page): publish it, then switch maintenance mode on."
fi
exit 1
