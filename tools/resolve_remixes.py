# -*- coding: utf-8 -*-
"""
リミックスの再生先を Apple Music / YouTube に差し替える
（fetch_remixes.py → clean_remixes.py → split_data.py の後に実行する）

Deezer はリミックスの同定と人気度の判定にのみ使い、視聴は
  Apple Music … iTunes Search API で30秒プレビューと購入ページを解決
  YouTube     … 検索URLを組み立て
に任せる。Deezer のプレビューは有料アカウントが必要になったため。

  python resolve_remixes.py --test "Titanium"
  python resolve_remixes.py

remixes.json を更新する（appleUrl / previewUrl / artwork / ytUrl を追加）。
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

import requests

from artistmatch import same_artist, tokens as artist_tokens

REMIXES = "remixes.json"
SONGS = "songs.json"
CACHE = "cache_itunes.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}
SLEEP = 0.7          # iTunes Search API は概ね毎分20回まで
LIMIT = 200          # 1回の検索で返せる上限

RE_VER = re.compile(
    r"\b(remix|rmx|mix|edit|bootleg|rework|refix|flip|vip|dub|extended|club)\b",
    re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def base_title(t):
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t or "")
    t = re.sub(r"\s*[-–—]\s*.*\b(remix|mix|edit|version)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+\b(feat|ft|featuring)\b\.?\s+.*$", "", t, flags=re.I)
    return norm(t)


def tokens(s):
    """バージョン名から、リミキサーを指す語だけ残す。"""
    stop = {"remix", "mix", "edit", "extended", "radio", "club", "version",
            "rework", "vip", "dub", "official", "feat", "ft", "the", "and"}
    return {w for w in norm(s).split() if len(w) > 2 and w not in stop}


def search(term, cache):
    """曲名+アーティストで検索し、リミックスらしきものだけ残して返す。"""
    if term in cache:
        return cache[term]
    try:
        r = requests.get("https://itunes.apple.com/search", headers=HEADERS,
                         timeout=30,
                         params={"term": term, "country": "jp", "media": "music",
                                 "entity": "song", "limit": LIMIT})
        r.raise_for_status()
        items = json.loads(r.text).get("results", [])
    except Exception as e:
        print("   検索失敗:", e)
        return []
    out = []
    for it in items:
        name = it.get("trackName", "")
        if not RE_VER.search(name):
            continue
        out.append({
            "name": name,
            "artist": it.get("artistName", ""),
            "appleUrl": it.get("trackViewUrl", ""),
            "previewUrl": it.get("previewUrl", ""),
            "artwork": (it.get("artworkUrl100") or "").replace(
                "100x100bb", "300x300bb"),
        })
    cache[term] = out
    time.sleep(SLEEP)
    return out


def version_part(name):
    """
    Apple Music のトラック名からバージョン表記だけ取り出す。
    'Titanium (feat. Sia) [Alesso Remix]' -> 'Alesso Remix'
    曲名部分を含めたまま比較すると、無関係な語が分母に入って一致度が落ちる。
    """
    for m in re.findall(r"[\(\[]([^\)\]]*)[\)\]]", name or ""):
        if RE_VER.search(m):
            return m
    m = re.search(r"[-–—]\s*(.+)$", name or "")
    return m.group(1) if m and RE_VER.search(m.group(1)) else ""


def best_match(remix, pool, song_base):
    """Deezer のリミックスに対応する Apple Music のトラックを選ぶ。"""
    want = tokens(remix.get("version") or remix.get("title", ""))
    if not want:
        return None
    best, score, tie = None, 0.0, 0.0
    for c in pool:
        if base_title(c["name"]) != song_base:
            continue
        got = tokens(version_part(c["name"]))
        if not got:
            continue
        inter = len(want & got)
        if not inter:
            continue
        # want 側がどれだけ含まれるかで見る（包含率）
        sc = inter / len(want)
        jac = inter / len(want | got)
        if (sc, jac) > (score, tie):
            best, score, tie = c, sc, jac
    return best if score >= 0.6 else None


# 日英の表記ゆれ（スティング / Sting）を吸収する照合器


def yt(*parts):
    q = " ".join(p for p in parts if p).strip()
    return "https://www.youtube.com/results?search_query=" + requests.utils.quote(q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", metavar="TITLE", help="1曲だけ詳細に試す")
    args = ap.parse_args()

    if not os.path.exists(REMIXES):
        sys.exit(f"{REMIXES} がありません。split_data.py を先に実行してください。")
    table = json.load(open(REMIXES, encoding="utf-8"))
    songs = {s["key"]: s for s in json.load(open(SONGS, encoding="utf-8"))}

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
        print(f"キャッシュ {len(cache)} 件")

    keys = list(table)
    if args.test:
        keys = [k for k in keys
                if args.test.lower() in (songs.get(k, {}).get("title", "").lower())][:1]
        if not keys:
            sys.exit(f"'{args.test}' を含む曲が見つかりません")

    total, matched, no_apple, dropped = 0, 0, 0, 0
    for n, k in enumerate(keys, 1):
        s = songs.get(k)
        if not s:
            continue
        sb = base_title(s["title"])
        pool = search(f"{s['title']} {s['artist']}", cache)
        # Apple側の候補。原曲アーティスト名義のものを本命とし、
        # 別名義でも曲名が一致するものは候補に残す（網羅性優先）。
        pool_strict = [c for c in pool
                       if same_artist(c.get("artist", ""), s["artist"])]
        pool = pool_strict or [c for c in pool if base_title(c["name"]) == sb]

        kept, seen_ver = [], set()
        for r in table[k]:
            total += 1
            hit = best_match(r, pool, sb)

            # 採否の根拠を3つのいずれかに求める
            by_artist = same_artist(r.get("artist", ""), s["artist"])
            in_title = bool(artist_tokens(s["artist"])
                            & artist_tokens(r.get("title", "")))
            if not (by_artist or hit or in_title):
                dropped += 1
                continue

            # Apple側で裏が取れたならアーティスト表記はそちらを正とする
            if hit:
                r["artist"] = hit["artist"] or r.get("artist", "")
                if hit.get("artwork"):
                    r["artwork"] = hit["artwork"]
                matched += 1
            else:
                no_apple += 1

            r["previewUrl"] = hit["previewUrl"] if hit else ""
            r["appleUrl"] = hit["appleUrl"] if hit else ""
            r["official"] = same_artist(r.get("artist", ""), s["artist"])
            r["ytUrl"] = yt(s["title"], r.get("version") or "", r.get("artist"))
            r["deezerUrl"] = r.pop("url", "")

            # 表記が揃った結果として生じる重複を畳む
            vkey = norm(r.get("version") or r.get("title", ""))
            if vkey in seen_ver:
                dropped += 1
                continue
            seen_ver.add(vkey)
            kept.append(r)

        kept.sort(key=lambda x: (not x["appleUrl"], -(x.get("rank") or 0)))
        table[k] = kept

        if args.test:
            print(f"\n対象: {s['title']} / {s['artist']}")
            print(f"Apple Music側の候補 {len(pool)} 件\n")
            for r in table[k]:
                mark = "○" if r["appleUrl"] else "△"
                print(f"  {mark} {r.get('version') or r['title']}")
                print(f"      アーティスト: {r['artist']}"
                      f"{'  [公式]' if r.get('official') else ''}")
                print(f"      Apple: {r['appleUrl'][:74] or '(見つからず・YouTubeのみ)'}")
            print(f"\n  残存 {len(table[k])} 件 / 除外 {dropped} 件")
            return

        if n % 100 == 0:
            print(f"  {n}/{len(keys)} 曲  照合 {matched}/{total}")
            json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                      ensure_ascii=False)

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    # 空になった曲はキーごと落とす
    table = {k: v for k, v in table.items() if v}
    json.dump(table, open(REMIXES, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # サイトの絞り込みが参照する件数を合わせる
    slist = json.load(open(SONGS, encoding="utf-8"))
    for x in slist:
        x["remixCount"] = len(table.get(x["key"], []))
    json.dump(slist, open(SONGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    left = sum(len(v) for v in table.values())
    empty = sum(1 for v in table.values() if not v)
    have = sum(1 for v in table.values() if v)
    print("\n--- 結果 ---")
    print(f"元のリミックス {total} 件 -> 残存 {left} 件")
    print(f"  除外（別曲・重複）  {dropped} 件")
    print(f"  Apple Musicで試聴可 {matched} 件")
    print(f"  YouTube検索のみ     {no_apple} 件")
    print(f"リミックスが無くなった曲 {empty} 件")
    print(f"リミックスを持つ曲 {have} 曲")


if __name__ == "__main__":
    main()
