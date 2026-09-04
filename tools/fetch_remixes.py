#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
リミックス版収集スクリプト（merge_data.py の後に実行する）

各曲について Deezer から人気のリミックス版を集めて songs.json に焼き込む。
Deezer API はキー不要、rank（人気スコア）と30秒プレビューを返す。

追加されるフィールド（songs.json の各曲）:
  isRemix      : セットリストの曲自体がリミックス版か
  remixOf      : リミックスの場合の元曲名
  remixes      : [{title, version, artist, rank, url, previewUrl, artwork}]
  remixSearchUrl : 取りこぼし用のYouTube検索リンク

使い方:
    pip install requests
    python fetch_remixes.py --test "Titanium"   # 1曲だけ試して生データを見る
    python fetch_remixes.py                     # 本実行
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

import requests

SONGS = "songs.json"
CACHE = "cache_remix.json"
DEEZER = "https://api.deezer.com/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}

SLEEP = 0.25        # Deezerは50req/5秒。余裕を持たせる
MAX_REMIX = 6       # 1曲あたりの表示上限

# リミックスと判定する語。versionフィールドにも本文にも出る。
RE_REMIX = re.compile(
    r"\b(remix|rmx|mix|edit|bootleg|rework|refix|flip|vip|dub|extended|"
    r"club|re-?work)\b", re.I)
# 「元曲そのもの」を示す語（リミックスとして扱わない）。
# radio edit は単なる短縮版なのでこちら側に置く。
RE_ORIGINAL = re.compile(
    r"\b(original\s*mix|album\s*version|single\s*version|radio\s*edit|"
    r"explicit|clean|remaster(ed)?|live|acoustic|instrumental|karaoke|"
    r"sped\s*up|slowed)\b", re.I)
RE_PAREN = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")

# フィットネス用の再演カバーなど、リミックスではないものを弾く
JUNK_ARTIST = re.compile(
    r"(workout|fitness|superfitness|power music|gym|cardio|spinning|running|"
    r"training|aerobic|treadmill|karaoke|tribute|cover band|the covers|"
    r"hits remixed|remix kingz|mixx party|party hits|dubstep hitz|"
    r"nightcore|slow mage|sped up|slowed|8-?bit|piano tribute|"
    r"made famous|in the style|instrumental version|bee entertainment)", re.I)
JUNK_TITLE = re.compile(
    r"(workout|\d{2,3}\s*bpm|karaoke|tribute|nightcore|slowed|sped\s*up|"
    r"in the style of|made famous by|8-?bit|music box|lullaby|"
    r"instrumental|backing track|reverb)", re.I)


def is_junk(title, version, artist):
    return bool(JUNK_ARTIST.search(artist or "")
                or JUNK_TITLE.search(title or "")
                or JUNK_TITLE.search(version or ""))


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def base_title(title):
    """'Titanium (Nicky Romero Remix)' -> 'titanium'"""
    t = RE_PAREN.sub(" ", title or "")
    t = re.sub(r"\s*-\s*.*(remix|mix|edit|version|bootleg).*$", "", t, flags=re.I)
    return norm(t)


def extract_version(title, version_field):
    """リミックス名を取り出す。'(Nicky Romero Remix)' -> 'Nicky Romero Remix'"""
    if version_field and version_field.strip():
        return version_field.strip().strip("()[]").strip()
    for m in RE_PAREN.findall(title or ""):
        if RE_REMIX.search(m):
            return m.strip()
    m = re.search(r"-\s*(.+(remix|mix|edit|bootleg|rework).*)$", title or "",
                  re.I)
    return m.group(1).strip() if m else ""


def looks_remix(title, version_field):
    """
    リミックスか判定する。'Original Mix' の "mix"、'Radio Edit' の "edit" に
    引っかからないよう、除外語を先に取り除いてから判定する。
    """
    blob = f"{title} {version_field or ''}"
    residual = RE_ORIGINAL.sub(" ", blob)
    return bool(RE_REMIX.search(residual))


def deezer_search(q, limit=40):
    try:
        r = requests.get(DEEZER, headers=HEADERS, timeout=20,
                         params={"q": q, "limit": limit})
        r.raise_for_status()
        return r.json().get("data", []) or []
    except Exception as e:
        print("   Deezer失敗:", e)
        return []


def find_remixes(title, artist, verbose=False):
    """1曲分のリミックスを人気順で返す。"""
    bt = base_title(title)
    na = norm(artist)
    seen, out = set(), []

    queries = [f'{title} {artist} remix', f'{base_title(title)} remix']
    for q in queries:
        for d in deezer_search(q):
            dt = d.get("title", "")
            ver = d.get("title_version", "")
            if verbose:
                print(f"    raw: {dt!r} version={ver!r} "
                      f"rank={d.get('rank')} artist={d.get('artist',{}).get('name')}")
            # 元曲と同じ曲であることを確認する
            if base_title(dt) != bt:
                continue
            if not looks_remix(dt, ver):
                continue
            if is_junk(dt, ver, (d.get("artist") or {}).get("name", "")):
                continue
            vname = extract_version(dt, ver)
            key = norm(vname) or norm(dt)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({
                "title": dt.strip(),
                "version": vname,
                "artist": (d.get("artist") or {}).get("name", ""),
                "rank": d.get("rank") or 0,
                "url": d.get("link", ""),
                "previewUrl": d.get("preview", ""),
                "artwork": (d.get("album") or {}).get("cover_medium", ""),
            })
        time.sleep(SLEEP)
        if len(out) >= MAX_REMIX * 2:
            break

    # 元アーティスト本人名義のものを少し優遇しつつ人気順
    out.sort(key=lambda x: (-(x["rank"] or 0), x["version"]))
    return out[:MAX_REMIX]


def yt_remix_url(title, artist):
    return ("https://www.youtube.com/results?search_query="
            + requests.utils.quote(f"{title} {artist} remix".strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", metavar="TITLE",
                    help="この曲名を含む最初の1曲だけ生データつきで試す")
    ap.add_argument("--min-rank", type=int, default=0,
                    help="このrank未満のリミックスは捨てる")
    args = ap.parse_args()

    with open(SONGS, encoding="utf-8") as f:
        songs = json.load(f)

    # ---- テストモード
    if args.test:
        hit = next((s for s in songs
                    if args.test.lower() in s["title"].lower()), None)
        if not hit:
            sys.exit(f"'{args.test}' を含む曲が見つかりません")
        print(f"対象: {hit['title']} / {hit['artist']}")
        print(f"  元曲判定: base='{base_title(hit['title'])}' "
              f"isRemix={looks_remix(hit['title'], '')}\n")
        rx = find_remixes(hit["title"], hit["artist"], verbose=True)
        print(f"\n  --> 採用 {len(rx)} 件")
        for r in rx:
            print(f"    rank{r['rank']:>7}  {r['version'] or r['title']}"
                  f"  ({r['artist']})")
        return

    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"キャッシュ {len(cache)} 曲")

    total = len(songs)
    print(f"{total} 曲のリミックスを収集します"
          f"（Deezer、1曲あたり最大2リクエスト）")

    for i, s in enumerate(songs, 1):
        s["isRemix"] = looks_remix(s["title"], "")
        s["remixOf"] = (RE_PAREN.sub("", s["title"]).strip()
                        if s["isRemix"] else "")
        s["remixSearchUrl"] = yt_remix_url(s["title"], s["artist"])

        k = s["key"]
        if k in cache:
            s["remixes"] = cache[k]
            continue
        rx = find_remixes(s["title"], s["artist"])
        rx = [r for r in rx if (r["rank"] or 0) >= args.min_rank]
        s["remixes"] = rx
        cache[k] = rx

        if i % 50 == 0:
            print(f"  {i}/{total}  （直近: {s['title'][:28]} "
                  f"→ {len(rx)}件）")
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    with open(SONGS, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)

    withrx = [s for s in songs if s.get("remixes")]
    print("\n--- 結果 ---")
    print(f"リミックスが見つかった曲 {len(withrx)}/{total} "
          f"= {len(withrx) * 100 // max(1, total)}%")
    print(f"セットリスト側がリミックス版だった曲 "
          f"{sum(1 for s in songs if s['isRemix'])}")
    if withrx:
        print(f"平均 {sum(len(s['remixes']) for s in withrx) / len(withrx):.1f} 件/曲")
        print("\nリミックスが多い曲:")
        for s in sorted(withrx, key=lambda x: -len(x["remixes"]))[:5]:
            print(f"  {s['title']} / {s['artist']} … {len(s['remixes'])}件")


if __name__ == "__main__":
    main()
