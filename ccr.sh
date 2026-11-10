# ccr —— 跨目录恢复 Claude Code 会话
# 在 ~/.zshrc 中： source /path/to/ccr/ccr.sh

# 自动定位本脚本所在目录（zsh: ${0:A:h}）
if [ -n "$ZSH_VERSION" ]; then
  CCR_DIR="${0:A:h}"
else
  CCR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
export CCR_DIR

_ccr_help() {
  cat <<'EOF'
ccr — 跨目录恢复 Claude Code 会话

用法：
  ccr              打开会话列表
  ccr -h, --help   显示本帮助

类 Vim 双模式：
  Normal（默认）
    j / k            下移 / 上移
    g / G            跳到首条 / 末条
    Ctrl-D / Ctrl-U  下翻 / 上翻半页
    / 或 i           进入 Insert 模式搜索
    Enter            恢复选中会话
    r / d            重命名 / 删除（删除需 y 确认）
    Space            切换预览
    q / Esc          退出
  Insert
    输入文字         模糊搜索：标题 / 分支 / 路径 / 中文首字母
    Ctrl-J / Ctrl-K  下移 / 上移
    Ctrl-U           清空输入
    Esc              返回 Normal（保留过滤结果，可继续用 j/k 挑选）
    Enter            恢复选中会话
  两种模式通用
    Ctrl-R / Ctrl-X  重命名 / 删除
    Ctrl-/           切换预览窗口位置（右侧 / 下方 / 隐藏）
    Ctrl-C           退出

中文首字母搜索：
  标题「这是一个测试名称」可用 zs、cs、mc 等任意连续词组的首字母命中；
  多音字的常用读音均可匹配（如「重构」可搜 cg 或 zg）。
  前缀 ' 表示精确匹配（如 'cs），避免模糊匹配带来的干扰结果。

环境变量：
  CCR_START_MODE   启动时所处模式：normal（默认）| insert
                   例：export CCR_START_MODE=insert  # 打开即可输入搜索
EOF
}

ccr() {
  case "$1" in
    -h|--help) _ccr_help; return 0 ;;
    "") ;;
    *) echo "ccr: 未知参数 '$1'（ccr --help 查看用法）" >&2; return 2 ;;
  esac

  # --no-input / show-input / hide-input / $FZF_INPUT_STATE 需要 fzf ≥ 0.59
  local fzf_ver fzf_major fzf_minor
  fzf_ver=$(fzf --version 2>/dev/null) || { echo "ccr: 未找到 fzf" >&2; return 1; }
  fzf_ver=${fzf_ver%% *}
  fzf_major=${fzf_ver%%.*}
  fzf_minor=${fzf_ver#*.}; fzf_minor=${fzf_minor%%.*}
  if [ "$fzf_major" -eq 0 ] 2>/dev/null && [ "$fzf_minor" -lt 59 ] 2>/dev/null; then
    echo "ccr: 需要 fzf ≥ 0.59，当前为 $fzf_ver" >&2
    return 1
  fi

  local index_py="$CCR_DIR/ccr-index.py"
  local pick cwd id rest

  # Normal 模式专属单键：进入 Insert 时 unbind（恢复为普通输入），回到 Normal 时 rebind
  local nkeys='j,k,g,G,/,i,q,r,d,space'
  # header 分两行，避免预览窗口打开时被截断
  local hdr_n=$'\e[1;32mNORMAL\e[0m'
  local hdr_n_keys=$'  j/k 移动 · g/G 首尾 · / 搜索 · Enter 恢复\n        r 重命名 · d 删除 · Space 预览 · q 退出'
  local hdr_i=$'\e[1;33mINSERT\e[0m  Esc 返回 · Enter 恢复\n        Ctrl-J/K 移动 · Ctrl-U 清空'
  local to_insert="show-input+unbind($nkeys)+change-header($hdr_i)"
  # 回到 Normal：输入框隐藏，若有过滤词则在 header 中显示，避免“看不见的过滤”
  local to_normal="printf '%s' \"hide-input+rebind($nkeys)+change-header:$hdr_n\"; \
[ -n \"\$FZF_QUERY\" ] && printf ' \033[33m/%s\033[0m' \"\$FZF_QUERY\"; \
printf '%s' '$hdr_n_keys'"

  local -a mode_opts
  case "${CCR_START_MODE:-normal}" in
    insert|i) mode_opts=(--header="$hdr_i" --bind="start:unbind($nkeys)") ;;
    normal|n) mode_opts=(--no-input --header="$hdr_n$hdr_n_keys") ;;
    *)
      echo "ccr: CCR_START_MODE 取值应为 normal 或 insert，已按 normal 启动" >&2
      mode_opts=(--no-input --header="$hdr_n$hdr_n_keys")
      ;;
  esac

  pick=$(python3 "$index_py" | fzf \
    --read0 --ansi --gap \
    --layout=reverse \
    --delimiter='\t' --with-nth=1 \
    --no-hscroll --ellipsis='' \
    --prompt='Resume ▸ ' \
    "${mode_opts[@]}" \
    --preview="python3 '$index_py' --preview {3}" \
    --preview-window='right,50%,wrap,border-left' \
    --bind='j:down,k:up,g:first,G:last,q:abort,space:toggle-preview' \
    --bind="/:$to_insert" \
    --bind="i:$to_insert" \
    --bind="esc:transform:if [ \"\$FZF_INPUT_STATE\" = enabled ]; then $to_normal; else echo abort; fi" \
    --bind='ctrl-d:transform:[ "$FZF_INPUT_STATE" = enabled ] && echo delete-char/eof || echo half-page-down' \
    --bind='ctrl-u:transform:[ "$FZF_INPUT_STATE" = enabled ] && echo unix-line-discard || echo half-page-up' \
    --bind='ctrl-/:change-preview-window(down,60%|hidden|right,50%)' \
    --bind="r:execute(python3 '$index_py' --rename {3})+reload(python3 '$index_py')" \
    --bind="d:execute(python3 '$index_py' --delete {3})+reload(python3 '$index_py')" \
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
