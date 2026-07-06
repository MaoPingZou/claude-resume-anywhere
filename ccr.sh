# ccr —— 跨目录恢复 Claude Code 会话
# 在 ~/.zshrc 中： source /path/to/ccr/ccr.sh

# 自动定位本脚本所在目录（zsh: ${0:A:h}）
if [ -n "$ZSH_VERSION" ]; then
  CCR_DIR="${0:A:h}"
else
  CCR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
export CCR_DIR

ccr() {
  local index_py="$CCR_DIR/ccr-index.py"
  local pick cwd id rest

  pick=$(python3 "$index_py" | fzf \
    --read0 --ansi --gap \
    --delimiter='\t' --with-nth=1 \
    --prompt='Resume ▸ ' \
    --header='Enter 恢复 · Space 预览 · Ctrl-R 重命名 · Ctrl-X 删除 · Esc 取消' \
    --preview="python3 '$index_py' --preview {3}" \
    --preview-window='right,50%,wrap,border-left' \
    --bind='space:toggle-preview' \
    --bind='ctrl-/:change-preview-window(down,60%|hidden|right,50%)' \
    --bind='ctrl-k:kill-line' \
    --bind="ctrl-r:execute(python3 '$index_py' --rename {3})+reload(python3 '$index_py')" \
    --bind="ctrl-x:execute(python3 '$index_py' --delete {3})+reload(python3 '$index_py')")

  [ -z "$pick" ] && return 0

  # 记录是多行(display 含换行) + \tcwd\tsessionId，
  # 用参数展开按“最后两个 tab 字段”取，避免 cut 的逐行问题。
  id="${pick##*$'\t'}"      # 最后一个 tab 之后 = sessionId
  rest="${pick%$'\t'*}"     # 去掉 sessionId
  cwd="${rest##*$'\t'}"     # 再取最后一个 tab 之后 = cwd

  if [ -z "$id" ] || [ "$id" = "$pick" ]; then
    echo "ccr: 未取到 sessionId" >&2
    return 1
  fi
  if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    cd "$cwd" || return 1
  elif [ -n "$cwd" ]; then
    echo "ccr: 目录不存在，留在当前目录: $cwd" >&2
  fi

  claude --resume "$id"
}
