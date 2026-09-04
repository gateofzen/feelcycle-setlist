# -*- coding: utf-8 -*-
"""
絞り込み前のリミックス一覧を cache_remix.json から復元する。

resolve_remixes.py は remixes.json を上書きしてしまうので、
検証用に絞り込み前の状態を remixes_before_filter.json として作り直す。

  python restore_remixes.py
"""

import json
import os
import sys

CACHE = "cache_remix.json"
SONGS = "songs.json"
OUT = "remixes_before_filter.json"

if not os.path.exists(CACHE):
    sys.exit(f"{CACHE} がありません。fetch_remixes.py のキャッシュが必要です。")

cache = json.load(open(CACHE, encoding="utf-8"))
songs = json.load(open(SONGS, encoding="utf-8"))
keys = {s["key"] for s in songs}

table = {k: v for k, v in cache.items() if k in keys and v}
json.dump(table, open(OUT, "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

print(f"{OUT} を作成")
print(f"  {len(table)} 曲 / {sum(len(v) for v in table.values())} 件")
print("\n注意: これは fetch_remixes.py 直後の状態です。"
      "\nclean_remixes.py のフィットネスカバー除去は含まれません。")
