# -*- coding: utf-8 -*-
"""构建脚本：把 tools/_parsed_raw.json 加工成站点数据 + 人工校对表。

步骤
  1) 结构清洗：选项里残留的重复标号、判断题 A/B -> T/F、空白占位统一
  2) 人工补丁（PATCHES）：只放算法修不好、且已对照原文确认的题
  3) 严格去重：规范化题干 + 选项内容集合 + 映射到选项内容的答案
  4) 章节归类：按 PDF 的题块区间定章节，再用关键词纠正块内混排的少数题
  5) 输出 data/questions.json（SPEC 契约）与 docs/题库校对表.xlsx

用法: python tools/build.py
"""
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "_parsed_raw.json"
OUT_JSON = ROOT / "data" / "questions.json"
OUT_XLSX = ROOT / "docs" / "题库校对表.xlsx"

TITLE = "2026 第五届全国工业设计职业技能大赛 灯具设计师理论题库"
VERSION = "2026-c5-r1"

# ---------------------------------------------------------------- 人工补丁
# 只放「算法无法可靠修好、且已确认过原文」的题。每处都写清依据，便于复核。
PATCHES = {
    328: {"stem": "1兆欧=（　　）欧", "note": "原PDF下划线占位丢失，已还原为题干空位"},
    368: {"stem": "安培是（　　）的单位。", "note": "原PDF下划线占位丢失，已还原为题干空位"},
}

# ---------------------------------------------------------------- 章节定义
CHAPTERS = [
    ("c1", "3D打印与增材制造"),
    ("c2", "PDM与数字化设计"),
    ("c3", "设计史与设计理论"),
    ("c4", "机械制图与机械设计"),
    ("c5", "灯具设计与照明技术"),
    ("c6", "材料工艺与质量安全"),
    ("c7", "AI辅助设计与CMF"),
    ("c8", "逆向设计与产品开发"),
    ("misc", "综合与其他"),
]

# PDF 本身就是成块排版的：区间即章节。区间由题块边界确定（见 docs/SPEC.md）。
RANGES = {
    "single": [
        (1, 45, "c1"), (46, 90, "c2"), (91, 136, "c3"), (137, 142, "c5"),
        (143, 158, "c3"), (159, 258, "c4"), (259, 272, "c8"), (273, 337, "c5"),
        (338, 390, "c6"), (391, 440, "c7"),
    ],
    "multi": [
        (1, 10, "c1"), (11, 20, "c2"), (21, 45, "c3"), (46, 50, "c8"),
        (51, 70, "c4"), (71, 100, "c5"),
    ],
    "judge": [
        (1, 15, "c1"), (16, 29, "c2"), (30, 67, "c3"), (68, 99, "c4"),
        (100, 114, "c8"), (115, 160, "c5"),
    ],
}

# 题块内部有少量混排的题：命中即改判（按题干 + 选项文本匹配）
OVERRIDES = [
    # 判断题尾段（115-160）里混进来的制图 / 工厂与电气题
    (r"制图基准|工艺基准|装配图的内容|图样主要是用正投影", "c4"),
    (r"火零线|作业指引卡|自检试拉|混拉|拉长不处理|按能量形式和来源|电气事故", "c6"),
    (r"市场调查|市场需求应变|构思是对既有问题|消费者的评价|设计管理", "c3"),
    # 单选题工艺段（338-390）里混进来的电气安全题
    (r"兆欧|安培|漏电保护|接地|绝缘|触电|灯杯输入电压|Ⅰ类灯具|Ⅱ类灯具", "c5"),
]


def chapter_of(section_key, no):
    for lo, hi, cid in RANGES[section_key]:
        if lo <= no <= hi:
            return cid
    return "misc"


def strip_dup_label(text, key):
    """多选里有 43 题选项文本重复带了标号（"A. 静态平衡"），去掉一层。"""
    return re.sub(rf"^[{key}][.．、]\s*", "", text).strip() if text else text


PUNCT = r"[\s\u3000.,。，、；;：:!！?？\"'“”‘’()（）\[\]【】<>《》…—\-_/\\|+]"


def norm(s):
    """去标点、去空格、统一大小写。保留罗马数字/希腊字母等非 ASCII 字符，
    否则「Ⅰ类 / Ⅱ类 / Ⅲ类」会被归一成同一个字串而误判为重复选项。"""
    return re.sub(PUNCT, "", s or "").upper()


def dedupe_key(r):
    stem = norm(r["stem"])
    if r["type"] == "judge":
        return (stem, "judge", tuple(r["answer"]))
    texts = {o["key"]: norm(o["text"]) for o in r["options"]}
    return (stem, r["type"], tuple(sorted(texts.values())),
            tuple(sorted(texts.get(k, "") for k in r["answer"])))


def clean_stem(s, qtype):
    s = re.sub(r"(?<=[/／])\s+", "", s)                 # "3D打印/ 增材造" -> "3D打印/增材造"
    s = re.sub(r"_{3,}", "______", s)                   # 下划线占位统一长度
    s = re.sub(r"（\s*）", "（　　）", s)                 # 空括号统一成全角空位
    s = re.sub(r"\(\s*\)$", "（　　）", s)
    s = s.strip()
    if qtype == "judge":
        s = re.sub(r"（　　）\s*$", "", s).strip()        # 判断题不用空位
        if s and not s.endswith(("。", "？", "！", "?", "!")):
            s += "。"
    return s


def main():
    recs = json.loads(RAW.read_text(encoding="utf-8"))
    by_key = {(r["section"], r["no"]): r for r in recs}
    issues = []
    overridden = []

    for r in recs:
        sec_key = {"单选题": "single", "多选题": "multi", "判断题": "judge"}[r["section"]]
        r["_sec"] = sec_key

        # ---- 判断题：A/B -> T/F ----
        if r["type"] == "judge":
            r["options"] = [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}]
            mapping = {"A": "T", "B": "F"}
            r["answer"] = [mapping.get(k, k) for k in r["answer"]]

        # ---- 选项：去掉残留的重复标号、尾部句号 ----
        seen_text = set()
        for i, o in enumerate(r["options"]):
            if r["type"] != "judge":
                o["text"] = strip_dup_label(o["text"], o["key"])
            t = o["text"].strip()
            if len(t) > 2:
                t = re.sub(r"[.．。]+$", "", t).strip()
            o["text"] = t
            if not t:
                issues.append((r, f"选项 {o['key']} 为空"))
            if norm(t) in seen_text:
                issues.append((r, f"选项 {o['key']} 与前面某项重复"))
            seen_text.add(norm(t))

        # ---- 题干 ----
        r["stem"] = clean_stem(r["stem"], r["type"])
        if len(r["stem"]) < 6:
            issues.append((r, "题干过短"))
        # 判断题的句子常以「等」「的」收尾（"...材料科学等。"），这不是截断，只标真截断
        if r["type"] == "judge" and re.search(r"(和|与|以及|、)$", r["stem"].rstrip("。")):
            issues.append((r, "题干疑似被 PDF 截断"))

        # ---- 答案必须落在选项里 ----
        keys = {o["key"] for o in r["options"]}
        bad = [k for k in r["answer"] if k not in keys]
        if bad:
            issues.append((r, f"答案 {bad} 不在选项中"))
        if not r["answer"]:
            issues.append((r, "缺答案"))

    # ---- 人工补丁 ----
    for no, patch in PATCHES.items():
        for r in recs:
            if r["no"] == no and r["_sec"] == "single":
                if "stem" in patch:
                    r["stem"] = patch["stem"]
                r.setdefault("notes", []).append(patch["note"])

    # ---- 去重：重复题保留但标记 dupOf，默认不抽取 ----
    seen = {}
    for r in recs:
        k = dedupe_key(r)
        if k in seen:
            r["dupOf"] = seen[k]
        else:
            seen[k] = r["no"]

    # ---- 章节归类 ----
    for r in recs:
        cid = chapter_of(r["_sec"], r["no"])
        text = r["stem"] + " " + " ".join(o["text"] for o in r["options"])
        for pat, target in OVERRIDES:
            if re.search(pat, text):
                if target != cid:
                    overridden.append((r["_sec"], r["no"], cid, target))
                    cid = target
                break
        r["chapter"] = cid

    # ---- 输出 ----
    qs = []
    for r in recs:
        prefix = {"single": "s", "multi": "m", "judge": "j"}[r["_sec"]]
        notes = r.get("notes", [])
        if len(r["options"]) != (2 if r["type"] == "judge" else 4):
            notes.append(f"选项数 {len(r['options'])}")
        qs.append({
            "id": f"q{prefix}{r['no']:03d}",
            "no": r["no"],
            "page": r["page"],
            "type": r["type"],
            "chapter": r["chapter"],
            "stem": r["stem"],
            "options": [{"key": o["key"], "text": o["text"]} for o in r["options"]],
            "answer": r["answer"],
            "explain": "",
            "flag": r.get("flag", ""),
            "dupOf": f"q{prefix}{r['dupOf']:03d}" if r.get("dupOf") else None,
            "note": "；".join(notes),
        })

    usable = [q for q in qs if not q["dupOf"] and q.get("flag") != "broken"]
    cnt = Counter(q["chapter"] for q in usable)
    chapter_rows = []
    for cid, name in CHAPTERS:
        if cnt.get(cid):
            chapter_rows.append({"id": cid, "name": name, "order": len(chapter_rows) + 1,
                                 "count": cnt[cid]})
    data = {
        "meta": {"title": TITLE, "version": VERSION, "total": len(qs),
                 "activeTotal": len(usable)},
        "chapters": chapter_rows,
        "questions": qs,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"解析 {len(recs)} 题 -> 输出 {len(qs)} 题（重复 {len(qs) - len(usable)}，可练 {len(usable)}）")
    print("题型:", dict(Counter(q["type"] for q in qs)))
    print("章节:", {cid: cnt.get(cid, 0) for cid, _ in CHAPTERS})
    print(f"区间外改判 {len(overridden)} 题")
    for item in overridden:
        print("   ", item)

    seen_no = set()
    print(f"\n数据问题 {len([i for i in issues if (i[0]['_sec'], i[0]['no']) not in seen_no])} 条：")
    for r, msg in issues:
        key = (r["_sec"], r["no"])
        if key in seen_no:
            continue
        seen_no.add(key)
        print(f"  {r['_sec'][:4]} Q{r['no']} p{r['page']} :: {msg} :: {r['stem'][:40]}")

    write_xlsx(recs, qs)
    print(f"\n写出 {OUT_JSON}\n写出 {OUT_XLSX}")


def write_xlsx(recs, qs):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    chname = dict(CHAPTERS)
    typ_name = {"single": "单选", "multi": "多选", "judge": "判断"}
    red = PatternFill("solid", fgColor="FFD6D6")
    yellow = PatternFill("solid", fgColor="FFF3CD")
    head_fill = PatternFill("solid", fgColor="DCE6F1")

    wb = Workbook()

    ws = wb.active
    ws.title = "概览"
    rows = [
        ("题库", TITLE),
        ("版本", VERSION),
        ("总题数", len(qs)),
        ("可练题数", sum(1 for q in qs if not q["dupOf"] and q["flag"] != "broken")),
        ("", ""),
        ("题型", ""),
    ]
    for t, c in Counter(q["type"] for q in qs).items():
        rows.append((f"  {typ_name[t]}", c))
    rows.append(("", ""))
    rows.append(("章节", ""))
    for cid, name in CHAPTERS:
        n = sum(1 for q in qs if q["chapter"] == cid)
        if n:
            rows.append((f"  {name}", n))
    rows += [
        ("", ""),
        ("红色行=需人工确认（题干截断/选项异常/答案可疑）", ""),
        ("黄色行=题干或选项做过规范化处理（去重标号、补空位等）", ""),
        ("校对方法：直接在本表改答案/题干，改完把文件发我，我重新生成", ""),
    ]
    for i, (a, b) in enumerate(rows, start=1):
        ws.cell(row=i, column=1, value=a)
        ws.cell(row=i, column=2, value=b)
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 52
    ws["A1"].font = Font(bold=True, size=13)

    ws = wb.create_sheet("全部题目")
    headers = ["题号", "页码", "题型", "章节", "题干", "A", "B", "C", "D", "答案", "备注"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    for q in qs:
        opt = {o["key"]: o["text"] for o in q["options"]}
        ans = "".join(q["answer"])
        if q["type"] == "judge":
            ans = "正确" if ans == "T" else "错误"
        ws.append([q["no"], q["page"], typ_name[q["type"]], chname.get(q["chapter"], ""),
                   q["stem"], opt.get("A", ""), opt.get("B", ""), opt.get("C", ""), opt.get("D", ""),
                   ans, q.get("note", "")])
        ri = ws.max_row
        fill = red if q["flag"] == "review" else (yellow if q.get("note") else None)
        if fill:
            for cell in ws[ri]:
                cell.fill = fill
        for col in range(1, len(headers) + 1):
            ws.cell(row=ri, column=col).alignment = Alignment(vertical="top", wrap_text=(col == 5))

    for i, w in enumerate([7, 6, 6, 18, 62, 24, 24, 24, 24, 8, 40], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_XLSX)


if __name__ == "__main__":
    main()
