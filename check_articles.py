# -*- coding: utf-8 -*-
"""
FEELCYCLIST の全記事を解析して、曲が取れない記事を洗い出す

merge_data.py の解析器をそのまま使うので、修正の効果を確認できる。
WordPress から記事を取り直すので cache_wp.json も作られる
（この後の merge_data.py が速くなる）。

  python check_articles.py
"""

import importlib.util
import sys
from collections import Counter

spec = importlib.util.spec_from_file_location("m", "merge_data.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

posts = m.fetch_wp_posts()
print(f"記事 {len(posts)} 件を解析します\n")

zero, few, ok = [], [], 0
counts = Counter()

for p in posts:
    try:
        rep = m.parse_report(p)
    except Exception as e:
        zero.append((p.get("slug", "?"), "解析エラー", f"{type(e).__name__}: {e}"))
        continue
    n = len(rep["tracks"])
    counts[n] += 1
    if n == 0:
        zero.append((p.get("slug", "?"), rep["name"], ""))
    elif n < 5:
        few.append((p.get("slug", "?"), rep["name"], n))
    else:
        ok += 1

print(f"曲が取れた記事      {ok}")
print(f"曲が少ない記事(1-4) {len(few)}")
print(f"曲が0の記事         {len(zero)}")

if zero:
    print(f"\n=== 曲が取れなかった記事 {len(zero)} 件 ===")
    for slug, name, note in zero:
        print(f"  {name[:28]:<30}{slug:<22}{note}")

if few:
    print(f"\n=== 曲が4曲以下の記事 {len(few)} 件 ===")
    for slug, name, n in few:
        print(f"  {name[:28]:<30}{slug:<22}{n}曲")

print("\n曲数の分布:")
for n in sorted(counts):
    if n <= 12 or counts[n] > 3:
        print(f"  {n:>3} 曲 … {counts[n]:>3} 記事")
