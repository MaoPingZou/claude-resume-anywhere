# ccr — 跨目录恢复 Claude Code 会话

![shell](https://img.shields.io/badge/shell-zsh%20%2F%20bash-89e051)
![python](https://img.shields.io/badge/python-3-3776ab)
![requires fzf](https://img.shields.io/badge/requires-fzf-1e90ff)
![last commit](https://img.shields.io/github/last-commit/MaoPingZou/claude-resume-anywhere)
![license](https://img.shields.io/github/license/MaoPingZou/claude-resume-anywhere)

Claude Code 自带的 `claude --resume` 只列出**当前工作目录**对应的会话。`ccr` 在**任意目录**下用 fzf 浏览并搜索 `~/.claude/projects/` 中的**全部**会话，选中后自动 `cd` 回该会话的原始目录并执行 `claude --resume <sessionId>`。

```
┌─ Resume ▸ auth                                       ┌─ Preview ────────────┐
│                                                      │ 重构鉴权中间件         │
│ ❯ 重构鉴权中间件                                       │ ~/work/api            │
│   10h ago · feature/auth · 128.4KB  ~/work/api       │ 10h ago · ⎇ … · 128K  │
│                                                      │ ──────────────        │
│ ❯ 配置 CI 工作流                                       │ ▸ User  …             │
│   3d ago · main · 74.2KB  ~/work/web                 │ ▸ Claude  …           │
└───────────────────────────────────────────────────  └───────────────────────┘
 Enter 恢复 · Space 预览 · Ctrl-R 重命名 · Ctrl-X 删除 · Esc 取消
```

## 特性

- 聚合展示所有工作目录下的会话，不受当前目录限制
- 模糊搜索标题、Git 分支与项目路径
- 侧栏预览会话的完整路径与最近对话
- 就地重命名会话，与 Claude Code 的 `/resume` 双向兼容
- 就地删除会话，单键确认防误触
- 纯标准库实现，无第三方 Python 依赖

## 依赖

- `python3`（仅标准库）
- [`fzf`](https://github.com/junegunn/fzf) ≥ 0.53
- `claude` CLI

## 安装

克隆仓库并接入 `~/.zshrc`：

```sh
git clone https://github.com/MaoPingZou/claude-resume-anywhere.git ~/.claude-resume-anywhere && \
  echo 'source ~/.claude-resume-anywhere/ccr.sh' >> ~/.zshrc && source ~/.zshrc
```

安装后在任意目录执行 `ccr` 即可。更新：

```sh
git -C ~/.claude-resume-anywhere pull
```

若放置于其他目录，将 `source` 行改为对应路径即可；`ccr.sh` 通过 `${0:A:h}` 自动定位自身目录，位置可任意迁移。

## 用法

```sh
ccr
```

### 快捷键

| 键 | 动作 |
|----|------|
| 输入文字 | 模糊搜索（标题 / 分支 / 路径） |
| `Enter` | `cd` 到会话目录并恢复 |
| `Space` | 切换预览面板 |
| `Ctrl-/` | 切换预览窗口位置（右侧 / 下方 / 隐藏） |
| `Ctrl-R` | 重命名选中会话 |
| `Ctrl-X` | 删除选中会话（`y` / `n` 单键确认） |
| `↑` / `↓`、`Ctrl-P` / `Ctrl-N` | 上下移动 |
| `Ctrl-K` | 删除到行尾 |
| `Esc` | 取消 |

## 列表格式

每条会话占两行：

```
❯ 会话标题
  10h ago · 分支 · 128.4KB   ~/项目/路径
```

- **标题优先级**：用户重命名（`custom-title`）→ AI 标题（`ai-title`）→ 最近一次输入（`last-prompt`）→ 首条用户消息
- **路径**：列表显示 `~` 缩写路径，预览面板显示完整绝对路径
- **排序**：按文件修改时间倒序

## 工作原理

### 数据来源

Claude Code 将会话按工作目录分桶存储于 `~/.claude/projects/<编码目录>/<sessionId>.jsonl`，每个 `.jsonl` 为逐行 JSON。`ccr-index.py` 扫描全部分桶并提取：

| 字段 | 来源 |
|------|------|
| `sessionId` | 文件名 |
| `cwd` | 行内 `cwd` 字段（编码目录名将 `/` 与 `.` 均转为 `-`，不可逆，故从内容读取） |
| 标题 | `custom-title` / `ai-title` / `last-prompt` / 首条 `user` 消息 |
| 分支 | 行内 `gitBranch` 字段 |
| 时间 / 大小 | 文件 `mtime` / `size` |

### fzf 数据流

每条记录输出为 `显示文本\t真实cwd\tsessionId`，以 `\0` 分隔并配合 `--read0`：

- fzf 仅显示与搜索第一段（`--with-nth=1`），后两段隐藏，仅用于跳转
- 显示文本内含换行，配合 `--read0` 与 `--gap` 实现两行样式
- 选中后由 `ccr()` 通过 shell 参数展开取出 `cwd` 与 `sessionId`

### 重命名与删除

- **重命名**：向会话 `.jsonl` 追加一条 `{"type":"custom-title","customTitle":...}`，扫描时取最后一条生效，与 Claude Code 内置机制一致
- **删除**：移除对应 `.jsonl` 文件，删除前需单键确认
- 二者均通过 fzf 的 `execute(...)+reload(...)` 执行并即时刷新列表

### 终端输入

重命名与删除由 fzf 的 `execute()` 调起，此时终端处于 raw 模式：

- 重命名读取整行：先 `stty sane` 恢复 canonical 模式，再从 `/dev/tty` 读取，保证退格正常
- 删除读取单键：通过 `termios` 进入 cbreak 模式（关闭行缓冲与回显），按键即响应

## 命令行

各子命令通常由 fzf 调用，亦可独立运行：

```sh
python3 ccr-index.py                 # 列出全部会话（NUL 分隔，供 fzf --read0）
python3 ccr-index.py --preview <id>  # 打印指定会话的预览
python3 ccr-index.py --rename <id>   # 重命名指定会话
python3 ccr-index.py --delete <id>   # 删除指定会话
```

## 说明

- 当会话原始目录已不存在时，仍可恢复，但会保留在当前目录并给出提示
- 每次启动执行一次全量扫描

## 许可证

[MIT](./LICENSE) © MaoPingZou
