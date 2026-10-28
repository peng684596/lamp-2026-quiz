# -*- coding: utf-8 -*-
"""题库 PDF 解析器 v1（2026 全国决赛版，700 题）。

输入：tools/_raw_all.txt（tools/extract.py 生成，含 ===== PAGE n ===== 标记）
输出：tools/_parsed_raw.json、tools/_parse_report.txt

结构：
  一、单选题 1..440   参考答案 → 1..440 单选答案
  二、多选题 1..100   参考答案 → 1..100 多选答案
  三、判断题 1..160   参考答案 → 1..160 判断答案（A=对 B=错）

策略：
  1. 先按题型大节切段，再分别处理「题干区」和「参考答案区」
  2. 题干区按期望题号顺序扫描（支持一行多题）
  3. 块内按 A./B./C./D. 切选项；题干跨行合并
  4. 答案只在参考答案区读取，题干预置（　　）占位
"""
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "_raw_all.txt"
OUT = HERE / "_parsed_raw.json"
REPORT = HERE / "_parse_report.txt"

HEADER = re.compile(r"^[一二三四五六七八九十]+、\s*(单选题|多选题|判断题)")
SKIP = re.compile(
    r"^(全国工业设计职业技能大赛理论试题库|-\d+-|"
    r"^2026 年全国行业职业技能竞赛|^——|^决赛理论试题库|^灯具设计师$|^组委会|^2026 年\s*9 月)"
)
OPT_START = re.compile(r"^\s*([A-D])\s*[.．、]\s*(.*)$")
OPT_INLINE = re.compile(r"(?:^|\s)([A-D])\s*[.．、]\s*")
ANS_LINE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*([A-D](?:\s*、?\s*[A-D])*)\s*$")
PAIR = re.compile(r"(?<!\d)(\d{1,3})\s*[.．、]\s*((?:[A-D]\s*、?\s*)+)")

COUNT = {"单选题": 440, "多选题": 100, "判断题": 160}
TYPE = {"单选题": "single", "多选题": "multi", "判断题": "judge"}

report = []


def log(*a):
    report.append(" ".join(str(x) for x in a))


CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
OPT_AHEAD = r"(?![A-D][.．、])"     # 选项标号前的空格必须保留，否则切不开选项


def clean(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\u3000", " ")
    s = re.sub(r"[ \t]+", " ", s).strip()
    # PDF 两端对齐产生的空格："3 D 打印" -> "3D 打印"
    s = re.sub(r"(?<=[0-9])\s+(?=[A-Za-z])", "", s)
    s = re.sub(r"(?<=[A-Za-z])\s+(?=[0-9])", "", s)
    # 中英/中数之间的空格
    s = re.sub(rf"(?<=[{CJK}])\s+(?=[0-9A-Za-z]){OPT_AHEAD}", "", s)
    s = re.sub(rf"(?<=[0-9A-Za-z])\s+(?=[{CJK}])", "", s)
    # 中文之间的空格
    s = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", s)
    return s.strip()


def load_pages():
    pages, page = [], 0
    for ln in RAW.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^===== PAGE (\d+) =====", ln.strip())
        if m:
            page = int(m.group(1))
            continue
        t = ln.strip()
        if not t or SKIP.match(t):
            continue
        pages.append((page, t))
    return pages


def split_sections(pages):
    """按题型大节切段 → {'单选题': (题干行, 答案行, 起始页)}"""
    order = ["单选题", "多选题", "判断题"]
    sections = {}
    cur = None
    rows = []
    for page, ln in pages:
        m = HEADER.match(ln)
        if m:
            if cur:
                sections[cur] = rows
            cur = m.group(1)
            rows = []
            continue
        if cur:
            rows.append((page, ln))
    if cur:
        sections[cur] = rows
    assert order == list(sections.keys()), list(sections.keys())

    out = {}
    for name in order:
        rows = sections[name]
        cut = None
        for i, (page, ln) in enumerate(rows):
            if ln.startswith("参考答案"):
                cut = i
                break
        stem_rows = rows[:cut] if cut is not None else rows
        ans_rows = rows[cut + 1:] if cut is not None else []
        out[name] = (stem_rows, ans_rows)
    return out


def parse_answers(ans_rows, expect_type):
    """从参考答案区抓 题号→答案。多选答案同一行可能有多题。"""
    ans = {}
    for page, ln in ans_rows:
        if expect_type == "multi":
            hits = PAIR.findall(ln)
            if not hits:
                log(f"  [答案区未识别] p{page}: {ln[:80]}")
            for no, letters in hits:
                ans[int(no)] = sorted(set(re.findall(r"[A-D]", letters)))
        else:
            m = ANS_LINE.match(ln)
            if m:
                ans[int(m.group(1))] = re.findall(r"[A-D]", m.group(2))
            else:
                hits = PAIR.findall(ln)
                if hits:
                    for no, letters in hits:
                        ans[int(no)] = re.findall(r"[A-D]", letters)
                else:
                    log(f"  [答案区未识别] p{page}: {ln[:80]}")
    return ans


def qstart_patterns(n):
    nb = r"(?<![0-9])" + str(n) + r"(?![0-9])"
    return [
        re.compile(nb + r"\s*[.．、]\s*"),
        re.compile(nb + r"(?=\s*[“\"‘'（(【])"),
    ]


def find_qstart(s, n):
    best = None
    for p in qstart_patterns(n):
        m = p.search(s)
        if m and (best is None or m.start() < best.start()):
            best = m
    return best


def split_blocks(rows, total):
    """顺序扫描期望题号，支持一行多题。"""
    blocks, cur, expected = [], None, 1
    for page, ln in rows:
        rest = ln
        guard = 0
        while True:
            guard += 1
            if guard > 60:
                break
            m = find_qstart(rest, expected) if expected <= total else None
            if m is None:
                if cur is not None and rest.strip():
                    cur[2].append(rest)
                break
            pre = rest[:m.start()]
            if cur is not None and pre.strip():
                cur[2].append(pre)
            if cur is not None:
                blocks.append(cur)
            cur = [expected, page, []]
            expected += 1
            rest = rest[m.end():]
            if not rest.strip():
                break
    if cur is not None:
        blocks.append(cur)
    return blocks


def split_options(lines):
    """把块内文本拆成 (题干行, 选项列表)。

    选项可能一行多个（"A.xxx B.yyy C.zzz D.www"），也可能折行。
    """
    text = "\n".join(lines)
    # 选项标号：行首 / 空白后 / 上一选项内联处
    marks = [(m.start(), m.group(1))
             for m in re.finditer(r"(?<![A-Za-z0-9])([A-D])[.．、]\s*", text)]
    seq, want = [], 0
    for pos, key in marks:
        if key == "ABCD"[want]:
            seq.append((pos, key))
            want += 1
            if want == 4:
                break
    if len(seq) >= 2 and seq[0][1] == "A":
        stem_text = text[: seq[0][0]]
        stem = [x.strip() for x in stem_text.split("\n") if x.strip()]
        opts = []
        for i, (pos, key) in enumerate(seq):
            end = seq[i + 1][0] if i + 1 < len(seq) else len(text)
            body = re.sub(r"^[A-D][.．、]\s*", "", text[pos:end])
            opts.append([key, body])
        return stem, opts
    return [x.strip() for x in lines if x.strip()], []


def join(parts):
    return clean("".join(clean(p) for p in parts if p))


def fix_text(s):
    s = re.sub(r"(?<![0-9A-Za-z])D\s*打印", "3D打印", s)
    s = re.sub(r"(?<![A-Za-z])FD\s*M\s*工艺", "FDM工艺", s)
    s = re.sub(r"\s+([，。；：？！、）])", r"\1", s)
    s = re.sub(r"([（])\s+", r"\1", s)
    return s.strip()


def parse_block(num, page, raw_lines, qtype, answer):
    rec = {"no": num, "page": page, "type": qtype, "stem": "", "options": [],
           "answer": list(answer or []), "issues": []}
    lines = [x for x in raw_lines if x.strip()]
    stem_lines, opts = split_options(lines)
    stem = join(stem_lines)
    options = []
    for key, body in opts:
        options.append({"key": key, "text": join(body.split("\n"))})

    if qtype == "judge":
        options = [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}]

    stem = fix_text(stem)
    options = [{"key": o["key"], "text": fix_text(o["text"])} for o in options]

    if not stem:
        rec["issues"].append("题干为空")
    if qtype in ("single", "multi"):
        if len(options) != 4:
            rec["issues"].append(f"选项数={len(options)}")
        if not answer:
            rec["issues"].append("缺答案")
        elif not set(answer) <= {o["key"] for o in options}:
            rec["issues"].append(f"答案{''.join(answer)}不在选项{''.join(o['key'] for o in options)}")
        if qtype == "multi" and len(answer or []) < 2:
            rec["issues"].append("多选答案不足2项")
        if qtype == "single" and len(answer or []) != 1:
            rec["issues"].append(f"单选答案长度={len(answer or [])}")
    else:
        if answer not in (["A"], ["B"]):
            rec["issues"].append(f"判断答案异常={answer}")

    rec.update({"stem": stem, "options": options})
    return rec


def main():
    pages = load_pages()
    sections = split_sections(pages)
    recs = []
    for name, (stem_rows, ans_rows) in sections.items():
        qtype = TYPE[name]
        total = COUNT[name]
        answers = parse_answers(ans_rows, qtype)
        log(f"{name}: 答案 {len(answers)}/{total}")
        missing_ans = [n for n in range(1, total + 1) if n not in answers]
        if missing_ans:
            log(f"  缺答案题号: {missing_ans}")

        blocks = split_blocks(stem_rows, total)
        log(f"  题块 {len(blocks)}/{total}")
        nums = [b[0] for b in blocks]
        if missing := [n for n in range(1, total + 1) if n not in set(nums)]:
            log(f"  缺题号: {missing}")
        if dup := [n for n, c in Counter(nums).items() if c > 1]:
            log(f"  重复题号: {dup}")

        for num, page, rl in blocks:
            rec = parse_block(num, page, rl, qtype, answers.get(num))
            rec["section"] = name
            recs.append(rec)

    bad = [r for r in recs if r["issues"]]
    log(f"\n有问题 {len(bad)} 题")
    for r in bad:
        log(f"  {r['section'][:2]} Q{r['no']:>3} p{r['page']:>3} type={r['type']} ans={r['answer']} "
            f"opts={len(r['options'])} :: {', '.join(r['issues'])}")
        log(f"      stem={r['stem'][:110]}")
        for o in r["options"]:
            log(f"        {o['key']}. {o['text'][:90]}")

    log("\n题型: " + str(Counter(r["type"] for r in recs)))
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(f"题块总数 {len(recs)}，有问题 {len(bad)}；详见 {REPORT}")
    print(f"写出 {OUT}")


if __name__ == "__main__":
    main()
