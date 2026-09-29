BACKUPS_DIR="$1"
cd $BACKUPS_DIR
latest=$(ls -1 | sort | grep -P '\d{6}-\d{5,6}.pgsql\.gz$' | tail -1)
scp -P 6666 $latest igegu@midas.psb.ugent.be:/group/elixir/backups/galaxy/latest_backup.pgsql.gz
#echo $latest
