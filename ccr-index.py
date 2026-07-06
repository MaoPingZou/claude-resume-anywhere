#!/usr/bin/env python3
"""ccr-index: 扫描 ~/.claude/projects 下所有会话，供 fzf 列表 / 预览使用。

用法：
  ccr-index.py                列出全部会话（NUL 分隔记录，供 fzf --read0）
  ccr-index.py --preview <id> 打印某个会话的预览
"""
import json
import os
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
HOME = str(Path.home())

# ── ANSI 颜色 ─────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def ask(prompt_text: str):
    """从控制终端读一行输入。

    这些子命令通常由 fzf 的 execute() 调起，此时终端处于 raw 模式，
    Python 的 input() 拿不到行编辑（退格会错乱）。先把 /dev/tty 恢复成
    canonical 模式（stty sane），再直接从 tty 读整行，交给终端驱动处理退格。
    """
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        # 无控制终端，退回普通 input
        return input(prompt_text)
    try:
        os.system("stty sane < /dev/tty > /dev/tty 2>/dev/null")
        tty.write(prompt_text)
        tty.flush()
        line = tty.readline()
        if line == "":  # EOF (Ctrl-D)
            raise EOFError
        return line.rstrip("\n")
    finally:
        tty.close()


def read_key() -> str:
    """从 /dev/tty 读单个按键（无需回车）。用于 y/n 即时确认。"""
    import termios

    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        ch = sys.stdin.read(1)
        return ch or "\x04"  # 无 tty 时把 EOF 当作取消
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ICANON | termios.ECHO)  # lflag: 关闭行缓冲与回显
    new[6][termios.VMIN] = 1
    new[6][termios.VTIME] = 0
    try:
        termios.tcsetattr(fd, termios.TCSANOW, new)
        ch = os.read(fd, 1)
        return ch.decode("utf-8", "replace") if ch else "\x04"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def rel_time(ts: float) -> str:
    d = max(0, int(time.time() - ts))
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    if d < 86400 * 30:
        return f"{d // 86400}d ago"
    return f"{d // (86400 * 30)}mo ago"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def pretty_path(p: str) -> str:
    return "~" + p[len(HOME):] if p.startswith(HOME) else p


def extract_text(content) -> str:
    """从 message.content 提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "\n".join(parts)
    return ""


def scan_session(path: Path):
    """解析单个 jsonl，返回会话元信息 dict 或 None。"""
    cwd = None
    branch = None
    custom_title = None
    ai_title = None
    last_prompt = None
    first_user = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = o.get("type")
                if cwd is None and o.get("cwd"):
                    cwd = o["cwd"]
                if branch is None and o.get("gitBranch"):
                    branch = o["gitBranch"]
                if t == "custom-title" and o.get("customTitle"):
                    custom_title = o["customTitle"]  # 用户 rename，多次取最后一次
                elif t == "ai-title" and o.get("aiTitle"):
                    ai_title = o["aiTitle"]
                elif t == "last-prompt" and o.get("lastPrompt"):
                    last_prompt = o["lastPrompt"]
                elif t == "user" and first_user is None:
                    txt = extract_text(o.get("message", {}).get("content"))
                    if txt.strip():
                        first_user = txt.strip()
    except OSError:
        return None

    title = custom_title or ai_title or last_prompt or first_user or "(无标题)"
    title = " ".join(title.split())  # 折叠换行/多空格
    st = path.stat()
    return {
        "id": path.stem,
        "cwd": cwd or "",
        "branch": branch or "",
        "title": title,
        "mtime": st.st_mtime,
        "size": st.st_size,
    }


def all_sessions():
    sessions = []
    if not PROJECTS_DIR.is_dir():
        return sessions
    for jf in PROJECTS_DIR.glob("*/*.jsonl"):
        info = scan_session(jf)
        if info:
            sessions.append(info)
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def list_command():
    out = []
    for s in all_sessions():
        title = truncate(s["title"], 78)
        meta_bits = [rel_time(s["mtime"])]
        if s["branch"]:
            meta_bits.append(s["branch"])
        meta_bits.append(human_size(s["size"]))
        meta = " · ".join(meta_bits)
        path = pretty_path(s["cwd"]) if s["cwd"] else "(未知路径)"
        # 两行展示：标题行 + 元信息行（含完整路径）
        display = (
            f"{CYAN}❯ {BOLD}{title}{RESET}\n"
            f"  {DIM}{meta}{RESET}  {GREEN}{path}{RESET}"
        )
        # 记录：display \t cwd \t sessionId，NUL 结尾供 fzf --read0
        out.append(f"{display}\t{s['cwd']}\t{s['id']}")
    sys.stdout.write("\0".join(out))


def find_session_file(session_id: str):
    matches = list(PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


def preview_command(session_id: str):
    jf = find_session_file(session_id)
    if not jf:
        print("会话文件未找到")
        return
    info = scan_session(jf)
    print(f"{BOLD}{info['title']}{RESET}")
    print(f"{GREEN}{info['cwd'] or '(未知)'}{RESET}")
    meta = [rel_time(info["mtime"]), human_size(info["size"])]
    if info["branch"]:
        meta.insert(1, f"⎇ {info['branch']}")
    print(f"{DIM}{'  ·  '.join(meta)}{RESET}")
    print(f"{DIM}{'─' * 46}{RESET}\n")

    # 最近若干轮对话
    turns = []
    try:
        with jf.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = o.get("type")
                if t in ("user", "assistant"):
                    txt = extract_text(o.get("message", {}).get("content")).strip()
                    if txt:
                        turns.append((t, txt))
    except OSError:
        pass

    for role, txt in turns[-8:]:
        tag = f"{YELLOW}▸ 你{RESET}" if role == "user" else f"{CYAN}▸ Claude{RESET}"
        print(tag)
        print(truncate(" ".join(txt.split()), 300))
        print()


def delete_command(session_id: str):
    jf = find_session_file(session_id)
    if not jf:
        print("会话文件未找到")
        return
    info = scan_session(jf)
    print(f"{YELLOW}即将删除会话：{RESET}{BOLD}{info['title']}{RESET}")
    print(f"{DIM}{pretty_path(info['cwd'])} · {human_size(info['size'])}{RESET}")

    sys.stdout.write(f"{YELLOW}确认删除? [y/N] {RESET}")
    sys.stdout.flush()
    while True:
        key = read_key()
        if key in ("y", "Y"):
            print("y")
            try:
                jf.unlink()
                print(f"{GREEN}已删除{RESET}")
            except OSError as e:
                print(f"删除失败: {e}")
            return
        if key in ("n", "N", "\x1b", "\x03", "\x04", "\r", "\n"):  # n/Esc/Ctrl-C/Ctrl-D/回车
            print("n")
            print("已取消")
            return
        # 其它键：提示后继续等 y/n
        sys.stdout.write(f"\n{DIM}请按 y 确认 / n 取消：{RESET}")
        sys.stdout.flush()


def rename_command(session_id: str):
    jf = find_session_file(session_id)
    if not jf:
        print("会话文件未找到")
        return
    info = scan_session(jf)
    print(f"{DIM}当前标题：{RESET}{BOLD}{info['title']}{RESET}")
    try:
        new = ask(f"{CYAN}新标题: {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return
    if not new:
        print("已取消（空标题）")
        return
    # 追加一条 custom-title 记录，扫描时取最后一条即生效
    rec = {"type": "custom-title", "customTitle": new, "sessionId": session_id}
    try:
        with jf.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{GREEN}已重命名为：{RESET}{new}")
    except OSError as e:
        print(f"重命名失败: {e}")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--preview":
        if len(args) < 2:
            print("用法: ccr-index.py --preview <sessionId>")
            return
        preview_command(args[1])
    elif args and args[0] == "--delete":
        if len(args) < 2:
            print("用法: ccr-index.py --delete <sessionId>")
            return
        delete_command(args[1])
    elif args and args[0] == "--rename":
        if len(args) < 2:
            print("用法: ccr-index.py --rename <sessionId>")
            return
        rename_command(args[1])
    else:
        list_command()


if __name__ == "__main__":
    main()
