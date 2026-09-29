local_handlers-log() { ## : Print a merge of all handlers logs
	handle_help "$@" <<-EOF
		Merge the log outputs of the 4 handlers. Command is:
                journalctl -u galaxy-handler@0 -u galaxy-handler@1 -u galaxy-hander@2 -u galaxy-hander@3
                Options can be added the end, e.g:
                    -n X to print the last X lines
                    -f real time printing of tail
	EOF
        journalctl -u galaxy-handler@0 -u galaxy-handler@1 -u galaxy-hander@2 -u galaxy-hander@3 $@
}



