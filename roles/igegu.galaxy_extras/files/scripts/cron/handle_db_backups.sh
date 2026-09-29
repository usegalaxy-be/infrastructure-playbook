#! /bin/bash
# vim: sw=2 ts=2 et ai

NUM_OLDEST_BACKUPS_TO_KEEP=20
NUM_RECENT_BACKUPS_TO_KEEP=20
NUM_MONTHS_TO_KEEP_DAILY_BACKUPS=1
AUTOMATIC_REMOVAL_THRESHOLD=40

# Deletes old DB backup files from the folder specified as an argument.
#
# Keeps:
# * NUM_RECENT_BACKUPS_TO_KEEP most recent backups
# * one backup per day for the last NUM_MONTHS_TO_KEEP_DAILY_BACKUPS months
# * one backup per month
# * NUM_OLDEST_BACKUPS_TO_KEEP oldest backups (a safeguard against bugs in the date processing logic)
#
# Refuses to run if more than AUTOMATIC_REMOVAL_THRESHOLD files would be removed
# (use --force to override).
#
# Requires file names to be named using the following format:
#   projectname-servername-date-time-commitid.sql.gz
# E.g.:
#   pm-live-20120322-1401-2db40fa.sql.gz
#
# Create the backups by running a script like this from cron:
#   COMMIT=$(cd /path/to/source/folder; git rev-parse --short HEAD)
#   mysqldump -u DBUSER -pDBPASSWORD DBNAME | gzip - > /path/to/backups/MYPROJECT-MYSERVER-$(date "+%Y%m%d-%H%S")-$COMMIT.sql.gz
#
# Author:  Andrey Tarantsov <andreyvit@me.com>
# License: MIT
# Site:    https://gist.github.com/2179886


###############################################################################
# parse command-line options
TOOLNAME="$(basename "$0")"
dry_run=false
force=false
verbose=false
while test -n "$1" && $cont_optparse true; do
    case $1 in
        -n | --dry-run) # Don't make any changes, print what will be kept and what will be removed
            dry_run=true; verbose=true; shift;;
        -f | --force) # Proceed even if more than AUTOMATIC_REMOVAL_THRESHOLD backups are to be removed
            force=true; shift;;
        -v | --verbose) # Print detailed progress info
            verbose=true; shift;;
        --oldest) # Set the number of oldest backups to keep
            NUM_OLDEST_BACKUPS_TO_KEEP=$2; shift; shift;;
        --recent) # Set the number of recent backups to keep
            NUM_RECENT_BACKUPS_TO_KEEP=$2; shift; shift;;
        --daily-months) # Set the number of recent months to keep daily backups for
            NUM_MONTHS_TO_KEEP_DAILY_BACKUPS=$2; shift; shift;;
        --automatic-threshold) # Set the maximum number of files that can be removed without --force
            AUTOMATIC_REMOVAL_THRESHOLD=$2; shift; shift;;
        --help) # Display this help message
            echo "Usage: $TOOLNAME [options] /path/to/backups"
            echo "Available options:"
            perl -ne 'printf "  %-15s %s\n", $1, $2 if / {8}((?:-\S \| )?--\S*)\) # (.*)$/' $0
            exit;;
        --)
            cont_optparse=false; shift;;
        -*)
            echo "** Invalid option $1. Run $TOOLNAME --help for a list of available options." >&2; exit 1;;
        *)
            cont_optparse=false;;
    esac
done
###############################################################################

BACKUPS_DIR="$1"

if test -z "$BACKUPS_DIR"; then
  echo " ** Error: backups directory must be specified. Run $TOOLNAME --help for usage info."
  exit 10
fi

if ! test -d "$BACKUPS_DIR"; then
  echo " ** Error: directory '$BACKUPS_DIR' does not exist."
  exit 2
fi

cd "$BACKUPS_DIR"

backup_id() {
  awk '-F[-.]' '{ OFS="-"; print $3, $4, $5 }'
}

all_backups() {
  ls -1 | sort | grep -P '\d{6}-\d{5,6}.pgsql\.gz$'
}

monthly_backups_to_keep() {
  all_backups | awk -F- '{ period = substr($3, 1, 6); if(!(period in periods)) print; periods[period] = 1 }'
}

daily_backups_to_keep() {
  all_backups | awk -v MK=$NUM_MONTHS_TO_KEEP_DAILY_BACKUPS -F- '
    {
        month = substr($3, 1, 6);
        if (!(month in months_hash)) {
            months_hash[month] = 1;
            months[c++] = month
        }

        if(!($3 in days_hash)) {
            days_hash[$3] = 1;
            daily[month, dailycount[month]++] = $0
        }
    }
    END {
        for(m = c - MK; m < c; ++m) {
            month = months[m]
            count = dailycount[month]
            for(i = 0; i < count; ++i)
                print daily[month, i]
        }
    }
'
}

oldest_backups_to_keep() {
  all_backups | head -$NUM_OLDEST_BACKUPS_TO_KEEP
}

recent_backups_to_keep() {
  all_backups | tail -$NUM_RECENT_BACKUPS_TO_KEEP
}

backups_to_keep() {
  monthly_backups_to_keep
  daily_backups_to_keep
  oldest_backups_to_keep
  recent_backups_to_keep
}

backups_to_remove() {
  comm -23 --check-order <( all_backups ) <( backups_to_keep | sort )
}

total=$(all_backups | wc -l)
removed=$(backups_to_remove | wc -l)
remaining=$( expr $total - $removed )

if test $removed -gt $AUTOMATIC_REMOVAL_THRESHOLD; then
  verbose=true
fi

$verbose && echo "Found: $total backups, oldest $(all_backups | head -1 | backup_id), newest $(all_backups | tail -1 | backup_id)."

if $dry_run; then
  echo "Will keep $remaining:"
  backups_to_keep | sort | uniq | sed 's/^/  /'
fi

if test $removed -gt $AUTOMATIC_REMOVAL_THRESHOLD && ! $force; then
  echo "To be removed: $removed backups ($remaining will remain)."
  echo "The number of backups to be removed exceeds automatic removal threshold of $AUTOMATIC_REMOVAL_THRESHOLD."
  echo "The script will NOT run now. Please rerun with --force option to proceed."
  exit 1
fi

$verbose && echo "Removing $removed backups ($remaining will remain)..."
for fn in $(backups_to_remove); do
  $dry_run || rm $fn
  $dry_run && echo "  rm $fn"
  $verbose && ! $dry_run && echo -n "."
done
$verbose && echo " OK"

$verbose && echo "After: $(all_backups | wc -l) backups, oldest $(all_backups | head -1 | backup_id), newest $(all_backups | tail -1 | backup_id)."

