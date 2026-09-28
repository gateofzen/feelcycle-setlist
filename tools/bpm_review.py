# -*- coding: utf-8 -*-
"""
BPMの要確認リストを作る（複数デバイスで作業する版）

シラタキさん由来のBPMは大半が正しいが、一部に倍取りが混じっている。
疑わしいものだけを抽出し、スマホ・PCのどれからでも確認できるようにする。

出力（既定でリポジトリ直下）:
  review-data.json  要確認リストの中身
  review.html       確認用の画面（GitHub経由で同期する）

  python bpm_review.py
  python bpm_review.py --min-score 2   根拠が2つ以上のものだけ
  python bpm_review.py --out .         toolsフォルダに出す
"""

import argparse
import json
import os
import shutil

SONGS = "songs.json"
PROGRAMS = "programs.json"
CACHE_DEEZER = "cache_deezer_bpm.json"
HINTS = "bpm_rekordbox_hints.json"

HIGH, LOW = 160, 90
TOL = 0.08


def is_double(a, b):
    if not a or not b:
        return False
    return abs(a / b - 2) < 2 * TOL or abs(b / a - 2) < 2 * TOL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=int, default=1)
    ap.add_argument("--out", default="..",
                    help="出力先。既定はリポジトリ直下")
    args = ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    programs = json.load(open(PROGRAMS, encoding="utf-8"))
    deezer = (json.load(open(CACHE_DEEZER, encoding="utf-8"))
              if os.path.exists(CACHE_DEEZER) else {})
    hints = (json.load(open(HINTS, encoding="utf-8"))
             if os.path.exists(HINTS) else {})
    if hints:
        print(f"rekordbox との食い違い {len(hints)} 件を判断材料に取り込みます")

    spread = {}
    for p in programs:
        for t in p["tracks"]:
            if t.get("bpm"):
                k = (t.get("title", "").strip().lower() + "|"
                     + t.get("artist", "").strip().lower())
                spread.setdefault(k, set()).add(t["bpm"])

    rows = []
    for s in songs:
        bpm = s.get("bpm")
        if not bpm:
            continue
        key = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
        reasons, suggest = [], None

        # rekordbox が別の値を持っている曲は最優先で確認したい
        rb = hints.get(key)
        if rb:
            reasons.append(f"rekordbox={rb}")
            suggest = rb

        if bpm > HIGH:
            reasons.append(f"{HIGH}超")
            suggest = round(bpm / 2)
        elif bpm < LOW:
            reasons.append(f"{LOW}未満")

        dz = deezer.get(s["key"])
        if dz and is_double(bpm, dz):
            reasons.append(f"Deezer={dz}(倍/半分)")
        elif dz and abs(dz - bpm) > 3:
            reasons.append(f"Deezer={dz}(不一致)")

        vals = spread.get(key, set())
        if len(vals) > 1:
            reasons.append("プログラム間で" + "/".join(str(v) for v in sorted(vals)))

        if s.get("bpmSource") == "estimated":
            reasons.append("推定値")

        if len(reasons) < args.min_score:
            continue

        rows.append({
            "id": s["title"].strip().lower() + "|" + s["artist"].strip().lower(),
            "title": s.get("titleEn") or s["title"],
            "artist": s.get("artistEn") or s["artist"],
            "bpm": bpm,
            "src": s.get("bpmSource") or "",
            "why": reasons,
            "sug": suggest or None,
            "prev": s.get("previewUrl") or "",
            "progs": ", ".join(p["name"] for p in s.get("programs", [])[:3]),
        })

    # 根拠が多い順、次にBPMが極端な順（直しやすいものから）
    # rekordbox の値がある曲は判断しやすいので先に出す
    rows.sort(key=lambda r: (not any(x.startswith("rekordbox") for x in r["why"]),
                             -len(r["why"]), -abs(r["bpm"] - 125)))

    os.makedirs(args.out, exist_ok=True)
    dat = os.path.join(args.out, "review-data.json")
    with open(dat, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))

    here = os.path.dirname(os.path.abspath(__file__))
    src_html = os.path.join(here, "review.html")
    dst_html = os.path.join(args.out, "review.html")
    if os.path.exists(src_html) and \
            os.path.abspath(src_html) != os.path.abspath(dst_html):
        shutil.copy(src_html, dst_html)
        print(f"review.html を {args.out} にコピーしました")
    elif os.path.exists(src_html):
        print("review.html は同じ場所にあるのでコピーしません")
    else:
        print("警告: review.html が tools フォルダにありません")

    total = sum(1 for s in songs if s.get("bpm"))
    print(f"\nBPMがある曲 {total} 中、要確認 {len(rows)} 曲")
    print(f"  → {dat}")

    from collections import Counter
    c = Counter()
    for r in rows:
        for x in r["why"]:
            c[x.split("=")[0].split("で")[0]] += 1
    print("\n根拠の内訳:")
    for k, v in c.most_common():
        print(f"  {k:<20}{v:>5} 曲")

    print("\n次の手順:")
    print("  1. cd ..  &&  git add review.html review-data.json")
    print("  2. git commit -m \"BPM確認リスト\"  &&  git push")
    print("  3. https://<ユーザー名>.github.io/feelcycle-setlist/review.html を開く")
    print("     スマホでもPCでも同じURLで、進捗はGitHub経由で同期されます")


if __name__ == "__main__":
    main()
