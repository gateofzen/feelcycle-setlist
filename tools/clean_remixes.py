# -*- coding: utf-8 -*-
"""
リミックス一覧の掃除（fetch_remixes.py の後に実行する）

Deezer にはフィットネス用の再演カバーが大量にあり、rank も高めに出るため
有名リミックスを押しのける。songs.json を再取得せずに後処理で除去する。

  python clean_remixes.py --dry-run   # 何が消えるか確認
  python clean_remixes.py             # 実行（songs.json を上書き）
"""

import argparse
import json
import re
import unicodedata
from collections import Counter

SONGS = "songs.json"

# 再演カバー・作業用BGMを出しているレーベル/アーティスト
JUNK_ARTIST = re.compile(
    r"(workout|fitness|superfitness|power music|gym|cardio|spinning|running|"
    r"training|aerobic|treadmill|karaoke|tribute|cover band|the covers|"
    r"hits remixed|remix kingz|mixx party|party hits|dubstep hitz|"
    r"nightcore|slow mage|sped up|slowed|8-?bit|piano tribute|"
    r"made famous|in the style|instrumental version|bee entertainment)",
    re.I)

# タイトル側に出る同種の目印
JUNK_TITLE = re.compile(
    r"(workout|\d{2,3}\s*bpm|karaoke|tribute|nightcore|slowed|sped\s*up|"
    r"in the style of|made famous by|8-?bit|music box|lullaby|"
    r"instrumental|backing track|reverb)",
    re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def is_junk(r):
    return bool(JUNK_ARTIST.search(r.get("artist", ""))
                or JUNK_TITLE.search(r.get("title", ""))
                or JUNK_TITLE.search(r.get("version", "")))


def artist_tokens(s):
    return {w for w in norm(s).split() if len(w) > 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=5, help="1曲あたりの上限")
    args = ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    removed, kept, dropped_names = 0, 0, Counter()
    lost_all = []

    for s in songs:
        rx = s.get("remixes") or []
        if not rx:
            continue
        before = len(rx)

        clean = []
        for r in rx:
            if is_junk(r):
                removed += 1
                dropped_names[r.get("artist", "?")] += 1
                continue
            clean.append(r)

        # 原曲と同じアーティスト名義のものを優先しつつ人気順
        base = artist_tokens(s.get("artist", ""))
        for r in clean:
            same = bool(base & artist_tokens(r.get("artist", "")))
            r["official"] = same
            r["_score"] = (r.get("rank") or 0) * (2.0 if same else 1.0)
        clean.sort(key=lambda r: -r["_score"])
        for r in clean:
            r.pop("_score", None)
        clean = clean[:args.max]

        kept += len(clean)
        if before and not clean:
            lost_all.append(s["title"])
        if not args.dry_run:
            s["remixes"] = clean

    print(f"除去 {removed} 件 / 残存 {kept} 件")
    print(f"リミックスが全滅した曲 {len(lost_all)} 件")
    for t in lost_all[:8]:
        print(f"  {t[:50]}")
    print("\n除去元の内訳（上位15）:")
    for name, c in dropped_names.most_common(15):
        print(f"  {c:>4}件  {name[:44]}")

    if args.dry_run:
        print("\n--dry-run のため書き込んでいません")
        return

    with open(SONGS, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)

    withrx = [s for s in songs if s.get("remixes")]
    print(f"\nリミックスを持つ曲 {len(withrx)}/{len(songs)} "
          f"= {len(withrx) * 100 // len(songs)}%")
    off = sum(1 for s in withrx for r in s["remixes"] if r.get("official"))
    print(f"原曲アーティスト名義のリミックス {off} 件")


if __name__ == "__main__":
    main()
