# -*- coding: utf-8 -*-
"""
リミックス絞り込みの検証（データは書き換えない）

resolve_remixes.py が何を落としたのかを、除外理由ごとに標本表示する。
絞り込みが厳しすぎないかを目視で判断するための道具。

  python audit_remixes.py            # 除外分の標本を見る
  python audit_remixes.py --song "Titanium"
"""

import argparse
import json
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "rr", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "resolve_remixes.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

CACHE = "cache_itunes.json"
BACKUP = "remixes_before_filter.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", help="この曲名を含む1曲だけ詳しく見る")
    ap.add_argument("--n", type=int, default=40, help="標本数")
    args = ap.parse_args()

    if not os.path.exists(BACKUP):
        sys.exit(
            f"{BACKUP} がありません。\n"
            "絞り込み前の remixes.json を remixes_before_filter.json という名前で\n"
            "置いてから実行してください（cache_remix.json から作り直せます）。")

    before = json.load(open(BACKUP, encoding="utf-8"))
    songs = {s["key"]: s for s in json.load(open("songs.json", encoding="utf-8"))}
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

    keys = list(before)
    if args.song:
        keys = [k for k in keys
                if args.song.lower() in songs.get(k, {}).get("title", "").lower()][:1]
        if not keys:
            sys.exit("該当する曲がありません")

    reasons = Counter()
    samples = {"別曲と判定": [], "重複": []}

    for k in keys:
        s = songs.get(k)
        if not s:
            continue
        pool = cache.get(f"{s['title']} {s['artist']}", [])
        pool = [c for c in pool
                if rr.same_artist(c.get("artist", ""), s["artist"])]
        sb = rr.base_title(s["title"])
        seen = set()

        for r in before[k]:
            hit = rr.best_match(r, pool, sb)
            by_artist = rr.same_artist(r.get("artist", ""), s["artist"])
            in_title = bool(rr.artist_tokens(s["artist"])
                            & rr.artist_tokens(r.get("title", "")))

            if not (by_artist or hit or in_title):
                reasons["別曲と判定"] += 1
                samples["別曲と判定"].append(
                    (s["title"], s["artist"], r.get("version") or r.get("title", ""),
                     r.get("artist", ""), r.get("rank", 0)))
                continue

            vkey = rr.norm(r.get("version") or r.get("title", ""))
            if vkey in seen:
                reasons["重複"] += 1
                samples["重複"].append(
                    (s["title"], s["artist"], r.get("version") or r.get("title", ""),
                     r.get("artist", ""), r.get("rank", 0)))
                continue
            seen.add(vkey)
            reasons["採用"] += 1

        if args.song:
            print(f"対象: {s['title']} / {s['artist']}")
            print(f"Apple候補（原曲アーティスト名義）{len(pool)} 件\n")
            for r in before[k]:
                hit = rr.best_match(r, pool, sb)
                ba = rr.same_artist(r.get("artist", ""), s["artist"])
                it = bool(rr.artist_tokens(s["artist"])
                          & rr.artist_tokens(r.get("title", "")))
                keep = ba or hit or it
                why = ("同アーティスト" if ba else
                       "Apple一致" if hit else "曲名に原曲アーティスト" if it
                       else "根拠なし")
                print(f"  {'採用' if keep else '除外'}  "
                      f"{(r.get('version') or r.get('title',''))[:44]:<46}"
                      f"{r.get('artist','')[:20]:<22}{why}")
            return

    total = sum(reasons.values())
    print(f"検証 {total} 件")
    for k2, v in reasons.most_common():
        print(f"  {k2:<12} {v:>6} 件 = {v * 100 // max(1, total)}%")

    random.seed(0)
    for label in ("別曲と判定", "重複"):
        rows = samples[label]
        if not rows:
            continue
        print(f"\n--- 「{label}」の標本 {min(args.n, len(rows))} 件 ---")
        print("（原曲 / 原曲アーティスト → 除外されたリミックス / そのアーティスト）")
        for t, a, v, ra, rk in random.sample(rows, min(args.n, len(rows))):
            print(f"  {t[:26]:<28}{a[:16]:<18}-> {v[:32]:<34}{ra[:22]}")


if __name__ == "__main__":
    main()
