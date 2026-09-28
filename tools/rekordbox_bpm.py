# -*- coding: utf-8 -*-
"""
rekordbox のBPMを取り込む

rekordbox はビートグリッド解析済みのBPMを AverageBpm として保持している。
推定値やレッスン由来の値より信頼できるので、未確定のBPMをこれで置き換える。

書き出し方:
  rekordbox → ファイル → ライブラリ → コレクションをxmlファイルとして保存

既存の値と一致するもの（±2）だけを自動で確定させる。食い違うものは
rekordbox 側が別バージョンを指していることがある（Uptown Funk が 115 なのに
ライブラリ上は 128 の版、など）ので、値は変えずに要確認リストへ回す。

優先順位: 手動確定(manual) > rekordbox > レッスン由来(report) > 推定(estimated)

  python rekordbox_bpm.py path/to/rekordbox.xml --dry-run
  python rekordbox_bpm.py path/to/rekordbox.xml
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata
import xml.etree.ElementTree as ET

from artistmatch import same_artist

SONGS = "songs.json"
PROGRAMS = "programs.json"
MANUAL_CANDIDATES = ["bpm_manual.json", os.path.join("..", "bpm_manual.json")]
OUT = "bpm_rekordbox.json"       # 自動確定した値
HINTS = "bpm_rekordbox_hints.json"  # 食い違い（判断材料）


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def base_title(t):
    """リミックス表記や共演表記を外した曲名。"""
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t or "")
    t = re.sub(r"\s*[-–—]\s*.*\b(remix|mix|edit|version)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+\b(feat|ft|featuring)\b\.?\s+.*$", "", t, flags=re.I)
    return norm(t)


def load_rekordbox(path):
    """XMLから (曲名, アーティスト, BPM) を読む。"""
    root = ET.parse(path).getroot()
    tracks = []
    for tr in root.iter("TRACK"):
        name = tr.get("Name")
        if not name:            # プレイリスト側のTRACKは参照だけなので飛ばす
            continue
        try:
            bpm = float(tr.get("AverageBpm") or 0)
        except ValueError:
            bpm = 0
        if not (30 <= bpm <= 260):
            continue
        tracks.append({
            "title": name,
            "artist": tr.get("Artist") or "",
            "remixer": tr.get("Remixer") or "",
            "bpm": round(bpm),
        })
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", help="rekordbox.xml のパス")
    ap.add_argument("--dry-run", action="store_true", help="書き換えずに結果だけ見る")
    ap.add_argument("--overwrite-manual", action="store_true",
                    help="手動確定した値も上書きする（通常は不要）")
    ap.add_argument("--force", action="store_true",
                    help="食い違う値もrekordboxで上書きする（推奨しない）")
    ap.add_argument("--tol", type=int, default=2,
                    help="一致とみなす差（既定±2）")
    ap.add_argument("--show", type=int, default=15,
                    help="食い違いを何件表示するか")
    args = ap.parse_args()

    if not os.path.exists(args.xml):
        sys.exit(f"{args.xml} が見つかりません")

    tracks = load_rekordbox(args.xml)
    print(f"rekordbox から {len(tracks)} 曲（BPMあり）を読み込みました")

    # 曲名で索引をつくる
    index = {}
    for t in tracks:
        index.setdefault(base_title(t["title"]), []).append(t)

    songs = json.load(open(SONGS, encoding="utf-8"))
    programs = json.load(open(PROGRAMS, encoding="utf-8"))

    manual = {}
    mp = next((p for p in MANUAL_CANDIDATES if os.path.exists(p)), None)
    if mp:
        manual = json.load(open(mp, encoding="utf-8"))
        print(f"手動確定 {len(manual)} 件は上書きしません（{mp}）")

    hit, skipped_manual, changed, same_val, conflict = 0, 0, 0, 0, 0
    big_diff = []
    table = {}      # 自動確定するもの
    hints = {}      # 食い違い。要確認リストの判断材料に回す

    for s in songs:
        key = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
        keyEn = ((s.get("titleEn") or "").strip().lower() + "|"
                 + (s.get("artistEn") or "").strip().lower())
        if not args.overwrite_manual and (key in manual or keyEn in manual):
            skipped_manual += 1
            continue

        cands = []
        for t in (s.get("titleEn"), s.get("title")):
            cands += index.get(base_title(t), [])
        if not cands:
            continue

        # アーティストも一致するものを選ぶ
        pick = None
        for c in cands:
            for a in (s.get("artistEn"), s.get("artist")):
                if a and same_artist(c["artist"], a):
                    pick = c
                    break
            if pick:
                break
        if not pick:
            continue

        hit += 1
        old = s.get("bpm")
        agree = old is not None and abs(old - pick["bpm"]) <= args.tol

        if agree or args.force or old is None:
            # 既存値と一致するものだけ自動確定する
            same_val += 1 if agree else 0
            table[key] = pick["bpm"]
            if not args.dry_run:
                s["bpm"] = pick["bpm"]
                s["bpmSource"] = "rekordbox"
            if not agree:
                changed += 1
                big_diff.append((s.get("titleEn") or s["title"],
                                 s.get("artistEn") or s["artist"],
                                 old, pick["bpm"], s.get("bpmSource")))
        else:
            # 食い違うものは値を変えず、判断材料として記録だけ残す
            conflict += 1
            hints[key] = pick["bpm"]
            big_diff.append((s.get("titleEn") or s["title"],
                             s.get("artistEn") or s["artist"],
                             old, pick["bpm"], s.get("bpmSource")))

    print(f"\n照合できた {hit} 曲 / 手動確定のため除外 {skipped_manual} 曲")
    print(f"  既存と一致（±{args.tol}）→ 自動確定  {same_val}")
    if changed:
        print(f"  既存値なし・強制で確定        {changed}")
    print(f"  食い違い → 要確認へ回す        {conflict}")

    if big_diff:
        dbl = [x for x in big_diff if x[2] and
               (abs(x[2] / x[3] - 2) < 0.16 or abs(x[3] / x[2] - 2) < 0.16)]
        print(f"    うち倍・半分の関係 {len(dbl)}")
        print(f"\n食い違ったもの（{min(args.show, len(big_diff))}/{len(big_diff)}件）:")
        for row in big_diff[:args.show]:
            t, a, old, new, src = row
            mark = " ←倍/半分" if row in dbl else ""
            print(f"  {t[:32]:<34}{a[:18]:<20}"
                  f"{str(old):>4} vs rekordbox {new:>4}  ({src}){mark}")
        if len(big_diff) > args.show:
            print(f"  （--show {len(big_diff)} で全件表示）")

    if args.dry_run:
        print("\n--dry-run のため書き込んでいません")
        return

    # セットリスト側にも反映
    fixed = {k: v for k, v in table.items()}
    tcount = 0
    for p in programs:
        for t in p["tracks"]:
            k = (t.get("title", "").strip().lower() + "|"
                 + t.get("artist", "").strip().lower())
            if k in fixed:
                t["bpm"] = fixed[k]
                t["bpmSource"] = "rekordbox"
                tcount += 1
        bl = [t["bpm"] for t in p["tracks"] if t.get("bpm")]
        p["bpmRange"] = [min(bl), max(bl)] if bl else None
        p["bpmMedian"] = round(statistics.median(bl)) if bl else None

    for s in songs:
        k = s["title"].strip().lower() + "|" + s["artist"].strip().lower()
        if k in fixed:
            for pr in s.get("programs", []):
                pr["bpm"] = fixed[k]

    json.dump(songs, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(programs, open(PROGRAMS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(table, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(hints, open(HINTS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n曲 {len(table)} 件 / セットリスト {tcount} 箇所に確定しました")
    print(f"{OUT} に記録（データを作り直しても再適用できます）")
    if hints:
        print(f"{HINTS} に食い違い {len(hints)} 件を記録")
        print("  → bpm_review.py が判断材料として取り込みます")
    print("\n次の手順:")
    print("  python bpm_apply.py --restore   手動確定を再適用")
    print("  python bpm_review.py            要確認リストを作り直す")


if __name__ == "__main__":
    main()
