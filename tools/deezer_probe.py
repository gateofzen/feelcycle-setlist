# -*- coding: utf-8 -*-
"""
Deezer の BPM 充足率を測る（データは書き換えない）

Deezer のトラックには bpm フィールドがあるが、値が入っていない曲がある。
本実行に30〜40分かけるか判断するため、無作為抽出で先に確かめる。

  python deezer_probe.py            # 40曲で試す
  python deezer_probe.py --n 100
"""

import argparse
import json
import random
import sys

sys.path.insert(0, ".")
import importlib.util

spec = importlib.util.spec_from_file_location("db", "deezer_bpm.py")
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    songs = json.load(open("songs.json", encoding="utf-8"))
    random.seed(0)
    sample = random.sample(songs, min(args.n, len(songs)))

    found = nobpm = nomatch = 0
    rows = []
    for i, s in enumerate(sample, 1):
        title = s.get("titleEn") or s["title"]
        artist = s.get("artistEn") or s["artist"]
        cands = db.find_tracks(title, artist)
        if not cands:
            nomatch += 1
            rows.append(("×照合不可", title, artist, None, s.get("bpm")))
            continue
        bpm = None
        for d in cands[:3]:
            bpm = db.track_bpm(d["id"])
            if bpm:
                break
        if bpm:
            found += 1
            rows.append(("○", title, artist, bpm, s.get("bpm")))
        else:
            nobpm += 1
            rows.append(("△BPM未登録", title, artist, None, s.get("bpm")))
        if i % 10 == 0:
            print(f"  {i}/{len(sample)}")

    print(f"\n--- {len(sample)} 曲の結果 ---")
    print(f"  BPM取得できた      {found} = {found*100//len(sample)}%")
    print(f"  曲は見つかるが未登録 {nobpm} = {nobpm*100//len(sample)}%")
    print(f"  曲自体が照合できず   {nomatch} = {nomatch*100//len(sample)}%")

    ok = [r for r in rows if r[0] == "○" and r[4]]
    if ok:
        dbl = [r for r in ok if abs(r[4]/r[3] - 2) < 0.08 or abs(r[3]/r[4] - 2) < 0.08]
        same = [r for r in ok if abs(r[3] - r[4]) <= 3]
        print(f"\n両方判明した {len(ok)} 曲のうち")
        print(f"  ほぼ一致      {len(same)}")
        print(f"  倍・半分の関係 {len(dbl)}")

    print("\n明細:")
    for mark, t, a, bpm, ride in rows:
        print(f"  {mark:<12}{t[:34]:<36}{(a or '')[:18]:<20}"
              f"楽曲 {str(bpm or '-'):>4} / ペダル {str(ride or '-'):>4}")


if __name__ == "__main__":
    main()
