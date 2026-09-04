# -*- coding: utf-8 -*-
"""
英語表記の取得（SoundCloud 検索用）

Apple Music の JP ストアから取ったデータはアーティスト名が
「コールドプレイ」のような日本語表記になる。SoundCloud は日本語では
検索できないため、同じトラックIDで US ストアを引いて英語表記を得る。

songs.json に titleEn / artistEn を追加する。

  python -m pip install requests
  python english_names.py
"""

import json
import os
import re
import sys
import time

import requests

SONGS = "songs.json"
CACHE = "cache_en.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}
CHUNK = 180
SLEEP = 1.0

RE_ID = re.compile(r"[?&]i=(\d+)")


def has_japanese(s):
    return any("\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff"
               for c in (s or ""))


def main():
    songs = json.load(open(SONGS, encoding="utf-8"))
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    if cache:
        print(f"キャッシュ {len(cache)} 件")

    # appleUrl から トラックID を取り出す
    need, id_of = [], {}
    for s in songs:
        m = RE_ID.search(s.get("appleUrl") or "")
        if not m:
            continue
        tid = m.group(1)
        id_of[s["key"]] = tid
        if tid not in cache:
            need.append(tid)

    need = list(dict.fromkeys(need))
    print(f"トラックID判明 {len(id_of)} 曲 / 未取得 {len(need)} 件")

    for i in range(0, len(need), CHUNK):
        part = need[i:i + CHUNK]
        try:
            r = requests.get("https://itunes.apple.com/lookup", headers=HEADERS,
                             timeout=30,
                             params={"id": ",".join(part), "country": "us",
                                     "entity": "song"})
            r.raise_for_status()
            for it in json.loads(r.text).get("results", []):
                if it.get("wrapperType") != "track":
                    continue
                cache[str(it["trackId"])] = {
                    "title": it.get("trackName", ""),
                    "artist": it.get("artistName", ""),
                }
        except Exception as e:
            print("  取得失敗:", e)
        print(f"  {min(i + CHUNK, len(need))}/{len(need)}")
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        time.sleep(SLEEP)

    filled, jp_left = 0, 0
    for s in songs:
        en = cache.get(id_of.get(s["key"], ""))
        if en and en.get("artist"):
            s["titleEn"] = en["title"] or s["title"]
            s["artistEn"] = en["artist"]
            filled += 1
        else:
            # US側が引けなければ元の表記をそのまま使う
            s["titleEn"] = s["title"]
            s["artistEn"] = s["artist"]
            if has_japanese(s["artist"]) or has_japanese(s["title"]):
                jp_left += 1

    json.dump(songs, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n--- 結果 ---")
    print(f"英語表記を取得 {filled}/{len(songs)} 曲")
    print(f"日本語のまま残った曲 {jp_left} 件（トラックIDが無く引けないもの）")
    print("\n例:")
    n = 0
    for s in songs:
        if s.get("artistEn") and s["artistEn"] != s["artist"]:
            print(f"  {s['artist']}  ->  {s['artistEn']}")
            n += 1
            if n >= 8:
                break


if __name__ == "__main__":
    main()
