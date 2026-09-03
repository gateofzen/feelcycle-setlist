#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BPM補完スクリプト（merge_data.py の後に実行する）

第2段階: 同一曲が他プログラムで判明していればBPMを転記
第3段階: それでも不明な曲を Apple Music の30秒プレビューから推定

入出力とも programs.json / songs.json（上書き。bpmSource フィールドを追加）
  bpmSource: "report"    シラタキさんのレポート由来（実測）
             "linked"    他プログラムの同一曲から転記
             "estimated" プレビュー音源からの推定
             null        不明

使い方:
    pip install requests librosa soundfile audioread
    python estimate_bpm.py --validate     # まず推定器の精度を測る
    python estimate_bpm.py                # 納得したら本実行
"""

import argparse
import json
import os
import random
import statistics
import sys
import tempfile

import requests

PROGRAMS = "programs.json"
SONGS = "songs.json"
CACHE = "cache_preview"

BPM_LO, BPM_HI = 85, 175       # FEELCYCLEの実用域。ここへ折り畳む
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}


def fold(bpm):
    """倍/半分の誤検出を実用域へ補正する。"""
    if not bpm or bpm <= 0:
        return None
    while bpm < BPM_LO:
        bpm *= 2
    while bpm > BPM_HI:
        bpm /= 2
    return bpm if BPM_LO <= bpm <= BPM_HI else None


def analyze(url, key):
    """プレビュー音源をビートトラッキングしてBPMを返す。"""
    try:
        import librosa
    except ImportError:
        sys.exit("librosa が必要です: pip install librosa soundfile audioread")

    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, key + ".m4a")
    if not os.path.exists(path):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception:
            return None
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        if len(y) < sr * 5:
            return None
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, trim=False)
        t = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
        return fold(t)
    except Exception:
        return None


def song_key(t):
    return (t.get("title", "").strip().lower() + "|"
            + t.get("artist", "").strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true",
                    help="正解BPMがある曲で推定器の精度だけ測る")
    ap.add_argument("--n", type=int, default=80, help="検証に使う曲数")
    args = ap.parse_args()

    with open(PROGRAMS, encoding="utf-8") as f:
        programs = json.load(f)
    with open(SONGS, encoding="utf-8") as f:
        songs = json.load(f)

    # ---------------- 検証モード
    if args.validate:
        known = [s for s in songs if s.get("bpm") and s.get("previewUrl")]
        if not known:
            sys.exit("正解BPMと試聴URLの両方を持つ曲がありません")
        random.seed(0)
        sample = random.sample(known, min(args.n, len(known)))
        print(f"正解BPMつき {len(known)} 曲から {len(sample)} 曲で検証します\n")

        errs, exact, close, fails = [], 0, 0, 0
        for i, s in enumerate(sample, 1):
            est = analyze(s["previewUrl"], s["key"][:60].replace("/", "_"))
            if est is None:
                fails += 1
                continue
            true = s["bpm"]
            e = abs(est - true) / true * 100
            errs.append(e)
            if e <= 2:
                exact += 1
            if e <= 5:
                close += 1
            mark = "○" if e <= 2 else ("△" if e <= 5 else "×")
            print(f"  {i:>3} {mark} 実測{true:>3} 推定{est:6.1f} "
                  f"誤差{e:5.1f}%  {s['title'][:30]}")

        n = len(errs)
        print(f"\n--- 検証結果 ---")
        print(f"解析成功 {n}/{len(sample)}（失敗 {fails}）")
        if n:
            print(f"誤差2%以内  {exact}/{n} = {exact * 100 // n}%")
            print(f"誤差5%以内  {close}/{n} = {close * 100 // n}%")
            print(f"誤差中央値  {statistics.median(errs):.1f}%")
            print("\n誤差5%以内が8割を超えるなら実用に足ります。"
                  "\n下回る場合は推定を使わず null のままにすることをおすすめします。")
        return

    # ---------------- 第2段階: 同一曲から転記
    truth = {}
    for p in programs:
        for t in p["tracks"]:
            if t.get("bpm"):
                truth.setdefault(song_key(t), []).append(t["bpm"])
    truth = {k: statistics.mode(v) for k, v in truth.items()}

    linked = 0
    for p in programs:
        for t in p["tracks"]:
            if t.get("bpm"):
                t["bpmSource"] = "report"
                continue
            v = truth.get(song_key(t))
            if v:
                t["bpm"] = v
                t["bpmSource"] = "linked"
                linked += 1
            else:
                t["bpmSource"] = None

    missing = [t for p in programs for t in p["tracks"] if not t.get("bpm")]
    have_preview = [t for t in missing if t.get("previewUrl")]
    print(f"転記で補完 {linked} 曲")
    print(f"残り不明 {len(missing)} 曲"
          f"（うち試聴音源あり {len(have_preview)} 曲＝推定可能）")

    # ---------------- 第3段階: 音源から推定
    if have_preview:
        ans = input("\nプレビュー音源からBPMを推定しますか？ [y/N] ").strip().lower()
        if ans == "y":
            done = {}
            for i, t in enumerate(have_preview, 1):
                k = song_key(t)
                if k in done:
                    est = done[k]
                else:
                    est = analyze(t["previewUrl"],
                                  (t.get("appleId") or str(abs(hash(k)))))
                    done[k] = est
                if est:
                    t["bpm"] = round(est)
                    t["bpmSource"] = "estimated"
                if i % 25 == 0:
                    print(f"  {i}/{len(have_preview)}")
            got = sum(1 for t in have_preview if t.get("bpm"))
            print(f"推定で補完 {got}/{len(have_preview)} 曲")

    # ---------------- songs.json を作り直す
    # プログラム側の値を曲側へ反映
    agg = {}
    for p in programs:
        for t in p["tracks"]:
            if t.get("bpm"):
                agg.setdefault(song_key(t), []).append(
                    (t["bpm"], t.get("bpmSource")))
    for s in songs:
        k = (s["title"].strip().lower() + "|" + s["artist"].strip().lower())
        vals = agg.get(k)
        if not vals:
            s["bpmSource"] = None
            continue
        s["bpm"] = statistics.mode([v for v, _ in vals])
        srcs = [x for _, x in vals]
        s["bpmSource"] = ("report" if "report" in srcs
                          else "linked" if "linked" in srcs else "estimated")
        for pr in s["programs"]:
            for p in programs:
                if p["id"] == pr["id"]:
                    for t in p["tracks"]:
                        if song_key(t) == k:
                            pr["bpm"] = t.get("bpm")
                            break

    for p in programs:
        bl = [t["bpm"] for t in p["tracks"] if t.get("bpm")]
        p["bpmRange"] = [min(bl), max(bl)] if bl else None
        p["bpmMedian"] = round(statistics.median(bl)) if bl else None

    with open(PROGRAMS, "w", encoding="utf-8") as f:
        json.dump(programs, f, ensure_ascii=False, indent=1)
    with open(SONGS, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)

    cnt = {}
    for s in songs:
        cnt[s.get("bpmSource")] = cnt.get(s.get("bpmSource"), 0) + 1
    print("\n--- 最終的なBPM充足状況（曲単位）---")
    for k in ("report", "linked", "estimated", None):
        if k in cnt:
            label = {"report": "実測（レポート由来）", "linked": "転記",
                     "estimated": "推定", None: "不明"}[k]
            print(f"  {label:<20} {cnt[k]:>5} 曲")
    nobpm = sum(1 for p in programs if not p["bpmMedian"])
    print(f"BPMが1曲も無いプログラム {nobpm} 件")


if __name__ == "__main__":
    main()
