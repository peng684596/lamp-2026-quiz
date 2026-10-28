# -*- coding: utf-8 -*-
"""PDF -> 带页码标记的文本（pymupdf，按视觉行重建）。

这份 PDF 的文字流顺序与视觉顺序不一致（选项字母与文字被拆到不同 block），
所以必须按坐标重建行：先按 y 聚类成行，行内按 x 排序，再按字间距决定是否补空格。
斜置水印（"全国工业设计职业技能大赛理论试题库"）是旋转文字，按行方向过滤掉。

输出 tools/_raw_all.txt：
    ===== PAGE 1 =====
    <line>
"""
import sys
from pathlib import Path

import pymupdf

SRC = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent / "_raw_all.txt"

Y_TOL = 3.0        # 同一行的 y 容差
SPACE_GAP = 6.0    # 超过这个间距补一个空格
WATERMARK = "全国工业设计职业技能大赛理论试题库"


def page_rows(page):
    words = []
    dic = page.get_text("dict")
    for block in dic["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            dx, dy = line["dir"]
            if abs(dy) > 0.01 or dx < 0.9:      # 旋转文字 = 水印
                continue
            for span in line["spans"]:
                txt = span["text"]
                if not txt.strip():
                    continue
                if txt.strip() in WATERMARK or WATERMARK in txt:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                words.append((x0, y0, x1, y1, txt))

    if not words:
        return []
    words.sort(key=lambda w: (w[1], w[0]))
    rows = []
    for x0, y0, x1, y1, txt in words:
        if rows and abs(y0 - rows[-1]["y"]) <= Y_TOL:
            rows[-1]["items"].append((x0, x1, txt))
        else:
            rows.append({"y": y0, "items": [(x0, x1, txt)]})

    out = []
    for row in rows:
        items = sorted(row["items"], key=lambda p: p[0])
        buf = []
        prev_x1 = None
        for x0, x1, t in items:
            if prev_x1 is not None and x0 - prev_x1 > SPACE_GAP:
                buf.append(" ")
            buf.append(t)
            prev_x1 = x1 if prev_x1 is None else max(prev_x1, x1)
        line = "".join(buf).strip()
        if line:
            out.append(line)
    return out


def main():
    doc = pymupdf.open(SRC)
    out = []
    for i, page in enumerate(doc, start=1):
        out.append(f"===== PAGE {i} =====")
        out.extend(page_rows(page))
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"pages={len(doc)} lines={len(out)} -> {OUT}")


if __name__ == "__main__":
    main()
