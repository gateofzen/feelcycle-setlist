# -*- coding: utf-8 -*-
"""
確定させたBPMを反映する

bpm_manual.json（手で確定した値）と bpm_rekordbox.json（rekordbox由来）を
songs.json / programs.json へ書き戻す。
どちらもリポジトリに入れてあるので、rekordbox.xml が無い端末でも揃えられる。

優先順位: 手動確定(manual) > rekordbox

  python bpm_apply.py --restore
"""

import argparse
import json
import os
import statistics

SONGS = "songs.json"
PROGRAMS = "programs.json"
# リポジトリ直下にも置かれるので両方を探す
MANUAL_CANDIDATES = ["bpm_manual.json", os.path.join("..", "bpm_manual.json")]
REKORDBOX_CANDIDATES = ["bpm_rekordbox.json",
                        os.path.join("..", "bpm_rekordbox.json")]


def load(cands):
    p = next((x for x in cands if os.path.exists(x)), None)
    if not p:
        return {}, None
    return json.load(open(p, encoding="utf-8")), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true",
                    help="記録済みの値から再適用する（既定の動作）")
    ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    programs = json.load(open(PROGRAMS, encoding="utf-8"))
    manual, mp = load(MANUAL_CANDIDATES)
    rekordbox, rp = load(REKORDBOX_CANDIDATES)

    if mp:
        print(f"手動確定 {len(manual)} 件（{mp}）")
    if rp:
        print(f"rekordbox {len(rekordbox)} 件（{rp}）")
    if not manual and not rekordbox:
        print("確定値が見つかりません。")
        return

    def keys_of(s):
        out = set()
        for t, a in ((s.get("titleEn"), s.get("artistEn")),
                     (s.get("title"), s.get("artist"))):
            if t:
                out.add(t.strip().lower() + "|" + (a or "").strip().lower())
        return out

    # rekordbox を先に当て、手動確定で上書きする
    n_rb = n_manual = 0
    fixed_map = {}
    for s in songs:
        hit = None
        for k in keys_of(s):
            if k in rekordbox:
                hit = (rekordbox[k], "rekordbox"); break
        for k in keys_of(s):
            if k in manual:
                hit = (manual[k], "manual"); break
        if not hit:
            continue
        s["bpm"], s["bpmSource"] = hit
        fixed_map[s["title"].strip().lower() + "|"
                  + s["artist"].strip().lower()] = hit
        if hit[1] == "manual":
            n_manual += 1
        else:
            n_rb += 1

    tracks = 0
    for p in programs:
        for t in p["tracks"]:
            k = (t.get("title", "").strip().lower() + "|"
                 + t.get("artist", "").strip().lower())
            if k in fixed_map:
                t["bpm"], t["bpmSource"] = fixed_map[k]
                tracks += 1
        bl = [t["bpm"] for t in p["tracks"] if t.get("bpm")]
        p["bpmRange"] = [min(bl), max(bl)] if bl else None
        p["bpmMedian"] = round(statistics.median(bl)) if bl else None

    for s in songs:
        k = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
        if k in fixed_map:
            for pr in s.get("programs", []):
                pr["bpm"] = fixed_map[k][0]

    json.dump(songs, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(programs, open(PROGRAMS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n曲 {n_rb + n_manual} 件 / セットリスト {tracks} 箇所に反映")
    print(f"  手動確定 {n_manual} 件 / rekordbox {n_rb} 件")
    miss = len(manual) - n_manual
    if miss > 0:
        print(f"照合できなかった手動確定 {miss} 件（曲名が変わった可能性）")


if __name__ == "__main__":
    main()
