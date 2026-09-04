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
    python -m pip install requests librosa soundfile imageio-ffmpeg
    python estimate_bpm.py --diagnose     # まず復号できるか確かめる
    python estimate_bpm.py --validate     # 推定器の精度を測る
    python estimate_bpm.py                # 本実行

Apple Music のプレビューは .m4a (AAC) なので、soundfile だけでは復号できない。
imageio-ffmpeg を入れると ffmpeg 本体が同梱され、管理者権限なしで解決する。
"""

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import traceback

import requests

PROGRAMS = "programs.json"
SONGS = "songs.json"
CACHE = "cache_preview"

BPM_LO, BPM_HI = 85, 170       # 推定値を折り畳む基準オクターブ
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}

_ffmpeg = None
_backend_note = []


def song_key(t):
    return (t.get("title", "").strip().lower() + "|"
            + t.get("artist", "").strip().lower())


def fold(bpm):
    """倍/半分の誤検出を基準オクターブへ補正する（手がかりが無い場合）。"""
    if not bpm or bpm <= 0:
        return None
    while bpm < BPM_LO:
        bpm *= 2
    while bpm > BPM_HI:
        bpm /= 2
    return bpm if BPM_LO <= bpm <= BPM_HI else None


# 実データ上のBPMは62〜195。1オクターブに収まらないので、固定窓では折り畳めない。
RANGE_LO, RANGE_HI = 60, 200
# 拍の取り違えで生じる倍率。2倍・半分に加え、3拍子系の3:2も含める。
MULTIPLIERS = [0.25, 1 / 3, 0.5, 2 / 3, 1, 1.5, 2, 3, 4]


def fold_with_anchor(bpm, anchor):
    """
    同じプログラム内の他の曲のBPM(anchor)に最も近い倍率を選ぶ。
    anchor が無ければ従来の固定窓に戻す。
    """
    if not bpm or bpm <= 0:
        return None
    if not anchor:
        return fold(bpm)
    import math
    cands = [bpm * m for m in MULTIPLIERS]
    cands = [c for c in cands if RANGE_LO <= c <= RANGE_HI]
    if not cands:
        return fold(bpm)
    return min(cands, key=lambda c: abs(math.log(c / anchor)))


def build_anchors(programs, exclude_self=True):
    """曲キー -> その曲が属するプログラムの他曲BPMの中央値。"""
    key_progs = {}
    for p in programs:
        for t in p["tracks"]:
            key_progs.setdefault(song_key(t), set()).add(p["id"])
    by_id = {p["id"]: p for p in programs}

    anchors = {}
    for k, pids in key_progs.items():
        vals = []
        for pid in pids:
            for t in by_id[pid]["tracks"]:
                if not t.get("bpm"):
                    continue
                if exclude_self and song_key(t) == k:
                    continue
                vals.append(t["bpm"])
        if vals:
            anchors[k] = statistics.median(vals)
    return anchors


def ffmpeg_exe():
    """同梱ffmpegのパスを返す。無ければPATH上のffmpegを試す。"""
    global _ffmpeg
    if _ffmpeg is not None:
        return _ffmpeg
    try:
        import imageio_ffmpeg
        _ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        _ffmpeg = which("ffmpeg") or ""
    return _ffmpeg


def decode(path, verbose=False):
    """
    音声ファイルを (モノラル float32 配列, サンプリングレート) で返す。
    soundfile → ffmpeg の順に試す。
    """
    import numpy as np

    # 1) soundfile（wav/flac/ogg/mp3 は読めるが m4a は読めない）
    try:
        import soundfile as sf
        y, sr = sf.read(path, dtype="float32", always_2d=True)
        if verbose:
            print(f"      soundfile で復号 sr={sr} 長さ={len(y)/sr:.1f}秒")
        return y.mean(axis=1), sr
    except Exception as e:
        if verbose:
            print(f"      soundfile 失敗: {type(e).__name__}: {e}")

    # 2) ffmpeg で生PCMへ変換（m4a/AAC はこちら）
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError(
            "m4a を復号できません。python -m pip install imageio-ffmpeg "
            "を実行してください")
    sr = 22050
    p = subprocess.run(
        [exe, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
         "-ar", str(sr), "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"ffmpeg 失敗: {p.stderr.decode('utf-8', 'ignore')[:200]}")
    y = np.frombuffer(p.stdout, dtype=np.float32).copy()
    if verbose:
        print(f"      ffmpeg で復号 sr={sr} 長さ={len(y)/sr:.1f}秒")
    return y, sr


def download(url, key, verbose=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, key + ".audio")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    if verbose:
        print(f"      ダウンロード {len(r.content)//1024} KB")
    return path


def analyze(url, key, verbose=False, anchor=None):
    """プレビュー音源からBPMを推定する。失敗時は None。"""
    try:
        import librosa
    except ImportError:
        sys.exit("librosa が必要です: python -m pip install librosa")
    try:
        path = download(url, key, verbose)
        y, sr = decode(path, verbose)
        if len(y) < sr * 5:
            if verbose:
                print("      音源が短すぎます")
            return None
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, trim=False)
        raw = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
        out = fold_with_anchor(raw, anchor)
        if verbose:
            print(f"      生の推定値 {raw:.1f} / 手がかり {anchor} "
                  f"-> 補正後 {out}")
        return out
    except Exception as e:
        if verbose:
            traceback.print_exc()
        else:
            _backend_note.append(f"{type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnose", action="store_true",
                    help="3曲だけ詳細ログつきで試し、復号可否を確かめる")
    ap.add_argument("--validate", action="store_true",
                    help="正解BPMがある曲で推定器の精度を測る")
    ap.add_argument("--n", type=int, default=80, help="検証に使う曲数")
    args = ap.parse_args()

    with open(PROGRAMS, encoding="utf-8") as f:
        programs = json.load(f)
    with open(SONGS, encoding="utf-8") as f:
        songs = json.load(f)

    # ---------------- 診断モード
    if args.diagnose:
        print(f"ffmpeg: {ffmpeg_exe() or '見つかりません'}")
        for mod in ("numpy", "soundfile", "librosa", "imageio_ffmpeg"):
            try:
                m = __import__(mod)
                print(f"  {mod}: {getattr(m, '__version__', 'ok')}")
            except Exception as e:
                print(f"  {mod}: 未導入 ({e})")
        pool = [s for s in songs if s.get("previewUrl")][:3]
        if not pool:
            sys.exit("試聴URLを持つ曲がありません")
        print()
        for s in pool:
            print(f"  {s['title']} / {s['artist']}")
            est = analyze(s["previewUrl"], (s.get("key") or "x")[:50]
                          .replace("/", "_").replace("|", "_"), verbose=True)
            print(f"      結果: {est}\n")
        return

    # ---------------- 検証モード
    if args.validate:
        known = [s for s in songs if s.get("bpm") and s.get("previewUrl")]
        if not known:
            sys.exit("正解BPMと試聴URLの両方を持つ曲がありません")
        random.seed(0)
        sample = random.sample(known, min(args.n, len(known)))
        anchors = build_anchors(programs)
        n_anchor = sum(1 for s in sample if anchors.get(s["key"]))
        print(f"正解BPMつき {len(known)} 曲から {len(sample)} 曲で検証します")
        print(f"（うち {n_anchor} 曲は同一プログラム内に手がかりあり）\n")

        errs, exact, close, fails = [], 0, 0, 0
        old_close = 0
        for i, s in enumerate(sample, 1):
            key = (s.get("key") or str(i))[:50].replace("/", "_").replace("|", "_")
            anchor = anchors.get(s["key"])
            est = analyze(s["previewUrl"], key, anchor=anchor)
            if est is None:
                fails += 1
                continue
            true = s["bpm"]
            e = abs(est - true) / true * 100
            errs.append(e)
            exact += e <= 2
            close += e <= 5
            # 参考: 従来の固定窓ならどうだったか
            old = analyze(s["previewUrl"], key)
            if old and abs(old - true) / true * 100 <= 5:
                old_close += 1
            mark = "○" if e <= 2 else ("△" if e <= 5 else "×")
            tag = "" if anchor else "  (手がかり無し)"
            print(f"  {i:>3} {mark} 実測{true:>3} 推定{est:6.1f} "
                  f"誤差{e:5.1f}%  {s['title'][:28]}{tag}")

        n = len(errs)
        print("\n--- 検証結果 ---")
        print(f"解析成功 {n}/{len(sample)}（失敗 {fails}）")
        if n:
            print(f"参考: 従来の固定窓だと 誤差5%以内 {old_close}/{n} "
                  f"= {old_close * 100 // n}%")
        if fails and _backend_note:
            from collections import Counter
            print("失敗の内訳:")
            for msg, c in Counter(_backend_note).most_common(3):
                print(f"  {c}件  {msg[:120]}")
            print("→ --diagnose で詳細を確認してください")
        if n:
            print(f"誤差2%以内  {exact}/{n} = {exact * 100 // n}%")
            print(f"誤差5%以内  {close}/{n} = {close * 100 // n}%")
            print(f"誤差中央値  {statistics.median(errs):.1f}%")
            print("\n誤差5%以内が8割を超えるなら実用に足ります。"
                  "\n下回る場合は推定を使わず不明のままにするのが無難です。")
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

    if have_preview:
        ans = input("\nプレビュー音源からBPMを推定しますか？ [y/N] ").strip().lower()
        if ans == "y":
            anchors = build_anchors(programs, exclude_self=False)
            done, ok = {}, 0
            for i, t in enumerate(have_preview, 1):
                k = song_key(t)
                if k not in done:
                    done[k] = analyze(
                        t["previewUrl"],
                        (t.get("appleId") or str(abs(hash(k))))[:50],
                        anchor=anchors.get(k))
                if done[k]:
                    t["bpm"] = round(done[k])
                    t["bpmSource"] = "estimated"
                    ok += 1
                if i % 25 == 0:
                    print(f"  {i}/{len(have_preview)}  成功 {ok}")
            print(f"推定で補完 {ok}/{len(have_preview)} 曲")
            if ok == 0 and _backend_note:
                from collections import Counter
                print("全件失敗しました。原因:")
                for msg, c in Counter(_backend_note).most_common(3):
                    print(f"  {c}件  {msg[:120]}")

    # ---------------- 曲側へ反映
    agg = {}
    for p in programs:
        for t in p["tracks"]:
            if t.get("bpm"):
                agg.setdefault(song_key(t), []).append(
                    (t["bpm"], t.get("bpmSource")))
    for s in songs:
        k = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
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
                if p["id"] != pr["id"]:
                    continue
                for t in p["tracks"]:
                    if song_key(t) == k:
                        pr["bpm"] = t.get("bpm")
                        break
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
    label = {"report": "実測（レポート由来）", "linked": "転記",
             "estimated": "推定", None: "不明"}
    print("\n--- 最終的なBPM充足状況（曲単位）---")
    for k in ("report", "linked", "estimated", None):
        if k in cnt:
            print(f"  {label[k]:<20} {cnt[k]:>5} 曲")
    print(f"BPMが1曲も無いプログラム "
          f"{sum(1 for p in programs if not p['bpmMedian'])} 件")


if __name__ == "__main__":
    main()
