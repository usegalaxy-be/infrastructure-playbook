#!/bin/bash

# backup mutable config files that change with time and may not be easy to reconstruct fromt the db 


src_path=$1  #dir with config files to backup
backup_dir=$2


#files=( "shed_data_manager_conf.xml" "shed_tool_conf.xml" "shed_tool_data_table_conf.xml")
timestamp=$(date +%s)
for file in $src_path/* #"${files[@]}"
do
   #file_path=$galaxy_config_base/$file_name
   file_name=${file##*/}
   backup_path=$backup_dir/$file_name\_$timestamp.backup
   echo $file_path
   echo $backup_path
   cp $file $backup_path
done

