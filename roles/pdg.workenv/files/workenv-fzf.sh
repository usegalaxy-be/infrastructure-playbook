[ -n "$ZSH_VERSION" ] || return  # zsh-only (zle/bindkey, fzf --zsh, zoxide init zsh); no-op under other shells

command -v fd > /dev/null && command -v fzf > /dev/null || return

export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_CTRL_T_OPTS="--preview 'bat --color=always {}'"
export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'

# Load fzf key bindings — skip if already done (e.g. ~/.fzf.zsh ran first)
[[ -n "${__fzf_key_bindings_options:-}" ]] || eval "$(fzf --zsh)"

# zoxide: jump to frecently-visited directories by fuzzy name (z, zi)
command -v zoxide > /dev/null && eval "$(zoxide init zsh)"

# fcd — fzf over both ancestor dirs (up) and subdirs (down) in one picker
function fcd() {
    local dir p
    if [[ $# -gt 0 ]]; then
        # Root given: search from that directory (no ancestors)
        dir=$(fd --type d --exclude .git --exclude .worktrees --max-depth 4 . "$1" \
            | sed "s|^$HOME|~|" \
            | fzf --height=60% --reverse)
        dir="${dir/#\~/$HOME}"
    else
        # No root: ancestors above + subdirs below current directory
        p=$(pwd)
        dir=$(
            {
                while [[ -n $p && $p != / ]]; do
                    p=${p%/*}
                    echo "${p:-/}"
                done | sed "s|^$HOME|~|"
                fd --type d --exclude .git --exclude .worktrees --max-depth 3 .
            } | fzf --height=60% --reverse
        )
        dir="${dir/#\~/$HOME}"  # expand ~ back to full path for cd
    fi
    [[ -n $dir ]] && cd "$dir"
}
function _fcd_widget()  { fcd;   zle reset-prompt }
function _fcdh_widget() { fcd ~; zle reset-prompt }
zle -N _fcd_widget
zle -N _fcdh_widget
bindkey '\ef' _fcd_widget   # Alt+F — add iTerm2 key mapping: Esc+ f
bindkey '\eh' _fcdh_widget  # Alt+H — add iTerm2 key mapping: Esc+ h
