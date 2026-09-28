# -*- coding: utf-8 -*-
"""
手で確定させたBPMを反映する（bpm_review.py の後）

bpm_review.csv の「確定値」列に入力された値を songs.json と programs.json
へ書き戻す。空欄の行は現在の値を維持する。

確定した値は bpm_manual.json に残るので、データを作り直しても
python bpm_apply.py --restore で復元できる。

  python bpm_apply.py            CSVを読んで反映
  python bpm_apply.py --restore  bpm_manual.json から再適用
"""

import argparse
import csv
import json
import os
import statistics

SONGS = "songs.json"
PROGRAMS = "programs.json"
CSV_IN = "bpm_review.csv"
# GitHub同期版はリポジトリ直下に置かれるので、両方を探す
MANUAL_CANDIDATES = ["bpm_manual.json", os.path.join("..", "bpm_manual.json")]
MANUAL = next((p for p in MANUAL_CANDIDATES if os.path.exists(p)),
              MANUAL_CANDIDATES[0])


def load_manual():
    return json.load(open(MANUAL, encoding="utf-8")) if os.path.exists(MANUAL) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true",
                    help="CSVを読まず bpm_manual.json だけで反映する")
    args = ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    programs = json.load(open(PROGRAMS, encoding="utf-8"))
    manual = load_manual()

    if not args.restore:
        if not os.path.exists(CSV_IN):
            raise SystemExit(f"{CSV_IN} がありません。先に bpm_review.py を実行してください。")
        added = 0
        with open(CSV_IN, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                v = (row.get("確定値") or "").strip()
                if not v:
                    continue
                try:
                    bpm = int(float(v))
                except ValueError:
                    print(f"  数値として読めません: {row.get('曲名')} = {v!r}")
                    continue
                if not (40 <= bpm <= 260):
                    print(f"  範囲外なので無視: {row.get('曲名')} = {bpm}")
                    continue
                k = (row["曲名"].strip().lower() + "|"
                     + row["アーティスト"].strip().lower())
                manual[k] = bpm
                added += 1
        json.dump(manual, open(MANUAL, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"CSVから {added} 件を読み込み（累計 {len(manual)} 件）")

    if not manual:
        print("確定値がありません。CSVの「確定値」列に記入してください。")
        return

    def keys_of(s):
        """英語表記・日本語表記のどちらでも引けるようにする。"""
        out = set()
        for t, a in ((s.get("titleEn"), s.get("artistEn")),
                     (s.get("title"), s.get("artist"))):
            if t:
                out.add((t.strip().lower() + "|" + (a or "").strip().lower()))
        return out

    # 曲側
    fixed = 0
    fixed_map = {}
    for s in songs:
        for k in keys_of(s):
            if k in manual:
                s["bpm"] = manual[k]
                s["bpmSource"] = "manual"
                fixed_map[s["title"].strip().lower() + "|"
                          + s["artist"].strip().lower()] = manual[k]
                fixed += 1
                break

    # プログラム側のセットリストにも反映
    tracks = 0
    for p in programs:
        for t in p["tracks"]:
            k = (t.get("title", "").strip().lower() + "|"
                 + t.get("artist", "").strip().lower())
            if k in fixed_map:
                t["bpm"] = fixed_map[k]
                t["bpmSource"] = "manual"
                tracks += 1
        bl = [t["bpm"] for t in p["tracks"] if t.get("bpm")]
        p["bpmRange"] = [min(bl), max(bl)] if bl else None
        p["bpmMedian"] = round(statistics.median(bl)) if bl else None

    # 逆引き側のBPMも揃える
    for s in songs:
        k = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
        if k in fixed_map:
            for pr in s.get("programs", []):
                pr["bpm"] = fixed_map[k]

    json.dump(songs, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(programs, open(PROGRAMS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"曲 {fixed} 件 / セットリスト {tracks} 箇所に反映しました")
    unmatched = len(manual) - fixed
    if unmatched > 0:
        print(f"照合できなかった確定値 {unmatched} 件"
              "（曲名が変わった可能性があります）")


if __name__ == "__main__":
    main()
