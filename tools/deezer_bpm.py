# -*- coding: utf-8 -*-
"""
楽曲BPMの取得（Deezer）

FEELCYCLIST由来のBPMは「レッスンでのペダル回転数」であり、楽曲そのものの
テンポとは倍・半分でずれることがある（Fortnight は楽曲96・レッスン192）。
ここでは楽曲としてのBPMを Deezer から取得し、bpmSong として保存する。

Deezer のトラック情報には bpm フィールドがある。認証不要。
ただし検索結果には含まれないため、曲を特定してから /track/{id} を引く。

  python -m pip install requests
  python deezer_bpm.py --test "Fortnight"
  python deezer_bpm.py
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

import requests

from artistmatch import same_artist

SONGS = "songs.json"
CACHE = "cache_deezer_bpm.json"
API = "https://api.deezer.com"
HEADERS = {"User-Agent": "cadence-setlist-search/1.0"}
SLEEP = 0.25          # Deezer は 50件/5秒


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def base_title(t):
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t or "")
    t = re.sub(r"\s*[-–—]\s*.*\b(remix|mix|edit|version)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+\b(feat|ft|featuring)\b\.?\s+.*$", "", t, flags=re.I)
    return norm(t)


def get(path, params=None, verbose=False):
    for _ in range(3):
        try:
            r = requests.get(API + path, headers=HEADERS, params=params,
                             timeout=30)
            if r.status_code == 429:
                time.sleep(3)
                continue
            r.raise_for_status()
            j = r.json()
            if isinstance(j, dict) and j.get("error"):
                if verbose:
                    print("   APIエラー:", j["error"])
                # 呼び出し過多は待って再試行
                if j["error"].get("code") == 4:
                    time.sleep(3)
                    continue
                return None
            return j
        except Exception as e:
            if verbose:
                print("   失敗:", e)
            time.sleep(1)
    return None


def find_tracks(title, artist, verbose=False):
    """
    曲名とアーティストの両方が一致する候補を、人気順で返す。
    アーティストが一致しないものは採らない。似た名前のカバー
    （Taylor Swift に対する "Taylor Swi ng"）を掴まないため。
    """
    bt = base_title(title)
    queries = [
        {"q": f'artist:"{artist}" track:"{bt}"'},
        {"q": f"{bt} {artist}"},
    ]
    found, seen = [], set()
    for params in queries:
        j = get("/search", {**params, "limit": 25}, verbose)
        time.sleep(SLEEP)
        data = (j or {}).get("data") or []
        ok = 0
        for d in data:
            if d.get("id") in seen:
                continue
            if base_title(d.get("title", "")) != bt:
                continue
            a = (d.get("artist") or {}).get("name", "")
            if not same_artist(a, artist):
                continue
            seen.add(d["id"])
            found.append(d)
            ok += 1
        if verbose:
            print(f"   検索 {params['q']} → {len(data)}件中 "
                  f"アーティスト一致 {ok}件")
        if found:
            break
    found.sort(key=lambda d: -(d.get("rank") or 0))
    return found


def track_bpm(tid, verbose=False):
    j = get(f"/track/{tid}", None, verbose)
    time.sleep(SLEEP)
    if not j:
        return None
    bpm = j.get("bpm")
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        return None
    # 0 は「不明」を意味する
    if bpm < 30 or bpm > 260:
        return None
    return round(bpm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", metavar="TITLE", help="1曲だけ詳細に試す")
    ap.add_argument("--limit", type=int, help="処理する曲数の上限（試験用）")
    args = ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    if cache:
        print(f"キャッシュ {len(cache)} 件")

    targets = songs
    if args.test:
        q = args.test.lower()
        targets = [s for s in songs
                   if q in (s.get("titleEn") or s["title"]).lower()][:1]
        if not targets:
            sys.exit(f"'{args.test}' を含む曲が見つかりません")

    hit = miss = 0
    for n, s in enumerate(targets, 1):
        if args.limit and n > args.limit:
            break
        title = s.get("titleEn") or s["title"]
        artist = s.get("artistEn") or s["artist"]
        k = s["key"]

        if k in cache and not args.test:
            if cache[k]:
                s["bpmSong"] = cache[k]
                hit += 1
            else:
                miss += 1
            continue

        if args.test:
            print(f"対象: {title} / {artist}")
            print(f"  レッスンでのBPM: {s.get('bpm')} ({s.get('bpmSource')})")

        cands = find_tracks(title, artist, verbose=bool(args.test))
        # BPM未登録（0）の版があるので、見つかるまで上位3件を試す
        bpm, used = None, None
        for d in cands[:3]:
            v = track_bpm(d["id"], verbose=bool(args.test))
            if args.test:
                print(f"   候補: {d.get('title')} / "
                      f"{(d.get('artist') or {}).get('name')}  → "
                      f"BPM {v if v else '未登録'}")
            if v:
                bpm, used = v, d
                break

        if args.test:
            if used:
                print(f"\n  採用: {used.get('link')}")
            print(f"  → 楽曲BPM {bpm if bpm else '不明'}")
            return

        if bpm:
            s["bpmSong"] = bpm
            cache[k] = bpm
            hit += 1
        else:
            cache[k] = None
            miss += 1

        if n % 50 == 0:
            print(f"  {n}/{len(targets)}  取得 {hit} / 不明 {miss}")
            json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                      ensure_ascii=False)

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(songs, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    both = [s for s in songs if s.get("bpmSong") and s.get("bpm")]
    dbl = [s for s in both
           if abs(s["bpm"] / s["bpmSong"] - 2) < 0.08
           or abs(s["bpmSong"] / s["bpm"] - 2) < 0.08]
    same = [s for s in both if abs(s["bpm"] - s["bpmSong"]) <= 3]
    other = len(both) - len(dbl) - len(same)

    print("\n--- 結果 ---")
    print(f"楽曲BPMを取得 {hit} / 不明 {miss}")
    print(f"両方ある曲 {len(both)}")
    print(f"  ほぼ一致（±3）      {len(same)} = {len(same)*100//max(1,len(both))}%")
    print(f"  倍または半分の関係  {len(dbl)} = {len(dbl)*100//max(1,len(both))}%")
    print(f"  それ以外の食い違い  {other} = {other*100//max(1,len(both))}%")
    print("\n倍・半分になっていた例:")
    for s in dbl[:10]:
        print(f"  {(s.get('titleEn') or s['title'])[:38]:<40}"
              f"レッスン {s['bpm']:>3} / 楽曲 {s['bpmSong']:>3}")


if __name__ == "__main__":
    main()
