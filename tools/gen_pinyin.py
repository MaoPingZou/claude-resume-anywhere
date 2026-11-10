#!/usr/bin/env python3
"""生成 ccr_pinyin_data.py：CJK 统一汉字（U+4E00–U+9FFF）的拼音首字母表。

仅在开发期运行，依赖 pypinyin；生成产物随仓库提交，ccr 运行时只用标准库。

  uv run --with pypinyin tools/gen_pinyin.py
  # 或：pip install pypinyin && python3 tools/gen_pinyin.py
"""
import unicodedata
from collections import Counter
from pathlib import Path

import pypinyin
from pypinyin import Style, pinyin
from pypinyin.phrases_dict import phrases_dict

BASE, END = 0x4E00, 0x9FFF
OUT = Path(__file__).resolve().parent.parent / "ccr_pinyin_data.py"
LINE_WIDTH = 64
# 非默认读音至少出现在这么多个词组中才收录，过滤掉生僻读音（如 是→t、重→t）
MIN_PHRASES = 3


def norm(letter: str) -> str:
    """去声调并小写，非 a-z 返回空串。"""
    c = unicodedata.normalize("NFKD", letter)[:1].lower()
    return c if "a" <= c <= "z" else ""


def phrase_usage() -> Counter:
    """统计 (汉字, 首字母) 在 pypinyin 词组库中出现的次数，用于判断读音是否常用。"""
    cnt = Counter()
    for phrase, readings in phrases_dict.items():
        if len(phrase) != len(readings):
            continue
        for ch, r in zip(phrase, readings):
            cnt[(ch, norm(r[0]))] += 1
    return cnt


def initials_of(ch: str, usage: Counter) -> str:
    """该字常用读音的首字母（去重，按词组用量降序）；无拼音返回空串。

    默认读音始终保留；其它读音需在词组库中出现至少 MIN_PHRASES 次。
    """
    readings = pinyin(ch, style=Style.FIRST_LETTER, heteronym=True, strict=False)[0]
    found = []
    for r in readings:
        c = norm(r)
        if c and c not in found:
            found.append(c)
    keep = found[:1] + [c for c in found[1:] if usage[(ch, c)] >= MIN_PHRASES]
    # 稳定排序：用量高的读音在前，用量相同保持 pypinyin 默认顺序
    keep.sort(key=lambda c: -usage[(ch, c)])
    return "".join(keep)


def main():
    usage = phrase_usage()
    initials = []
    poly = {}
    for cp in range(BASE, END + 1):
        ch = chr(cp)
        ini = initials_of(ch, usage)
        initials.append(ini[:1] or "_")
        if len(ini) > 1:
            poly[ch] = ini
    table = "".join(initials)

    lines = [
        f"# 由 tools/gen_pinyin.py 生成（pypinyin {pypinyin.__version__}），请勿手改。",
        "# INITIALS[ord(ch) - BASE]：汉字最常用读音的首字母，'_' 表示无拼音。",
        "# POLY：首字母不同的常用多音字，值为全部首字母（按词组用量降序）。",
        f"BASE = {BASE:#06x}",
        "INITIALS = (",
    ]
    for i in range(0, len(table), LINE_WIDTH):
        lines.append(f'    "{table[i:i + LINE_WIDTH]}"')
    lines.append(")")
    lines.append("POLY = {")
    for ch, ini in poly.items():
        lines.append(f'    "{ch}": "{ini}",')
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(table)} chars, {len(poly)} polyphones")


if __name__ == "__main__":
    main()
