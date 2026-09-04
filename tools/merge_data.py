#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FEELCYCLE 楽曲検索データ構築（Apple Music × FEELCYCLIST マージ）

入力:
  apple_programs.json  … ブラウザConsoleスクリプトで取得（無くても動作する）
出力:
  programs.json        … プログラム -> 曲順つきセットリスト（BPM・ポジション・動作つき）
  songs.json           … 曲 -> 収録プログラム（逆引き、曲単位のBPMつき）
  unmatched.txt        … 照合できなかったプログラム（要確認）

使い方:
    pip install requests
    python merge_data.py
"""

import html
import json
import os
import re
import statistics
import time
import unicodedata
from collections import OrderedDict

import requests

APPLE_JSON = "apple_programs.json"
OUT_PROGRAMS = "programs.json"
OUT_SONGS = "songs.json"
OUT_UNMATCHED = "unmatched.txt"
CACHE_WP = "cache_wp.json"

WP_API = "https://feel.shirataki.me/wp-json/wp/v2/posts"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-setlist-indexer/1.0)"}

OVERLAP_MIN = 0.5
OVERLAP_MIN_COUNT = 3


# ---------------------------------------------------------------- 正規化

def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]", " ", s)
    s = re.sub(r"\b(feat|ft)\.\s*", "feat ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def norm_program(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]", "", s)


def uniq(seq):
    return list(OrderedDict.fromkeys(seq))


# ------------------------------------------------- FEELCYCLIST (WordPress)

def fetch_wp_posts():
    if os.path.exists(CACHE_WP):
        with open(CACHE_WP, encoding="utf-8") as f:
            posts = json.load(f)
        print(f"WPキャッシュを使用: {len(posts)} 記事")
        return posts

    posts, page = [], 1
    while page <= 10:
        r = requests.get(WP_API, headers=HEADERS, timeout=30,
                         params={"per_page": 100, "page": page,
                                 "_fields": "id,slug,link,title,content,date"})
        if r.status_code == 400:
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        print(f"  WP page {page}: +{len(batch)} (計 {len(posts)})")
        total = int(r.headers.get("X-WP-TotalPages", 0) or 0)
        page += 1
        if total and page > total:
            break
        time.sleep(1.0)

    with open(CACHE_WP, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False)
    return posts


RE_IFRAME = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
RE_TAG = re.compile(r"<[^>]+>")
RE_BR = re.compile(r"<br\s*/?>", re.I)
RE_BLOCK = re.compile(r"</(p|div|h[1-6]|li|blockquote)>", re.I)
RE_TRACKID = re.compile(r"[?&]i=(\d+)")
RE_BPM = re.compile(r"BPM\s*[:\uff1a]?\s*(\d{2,3})")
RE_DUR = re.compile(r"^\d{1,2}:\d{2}$")


def html_to_lines(h):
    h = RE_IFRAME.sub(lambda m: f"\nEMBED:{m.group(1)}\n", h)
    h = RE_BR.sub("\n", h)
    h = RE_BLOCK.sub("\n", h)
    h = RE_TAG.sub("", h)
    h = html.unescape(h)
    return [x.strip() for x in h.split("\n")]


def split_title_artist(line):
    if " / " in line:
        t, a = line.split(" / ", 1)
    elif "/" in line:
        t, a = line.split("/", 1)
    else:
        return line.strip(), ""
    return t.strip(), a.strip()


def parse_bracket(ln):
    """
    [P3↑× ST：BPM128]      -> ("P3↑× ST", "128")  ポジション行
    [↓：BPM124]            -> ("↓", "124")
    [BACK TO UP / PUSH UP] -> (None, None)        動作行
    """
    inner = ln.strip().strip("[]").strip()
    m = RE_BPM.search(inner)
    if not m:
        return None, None
    pos = re.split(r"[\uff1a:]?\s*BPM", inner)[0].strip().rstrip("\uff1a:").strip()
    return pos, m.group(1)


def parse_report(post):
    name = html.unescape(RE_TAG.sub("", post["title"]["rendered"]))
    name = re.split(r"の強度|\uff1aFEELCYCLE|【AE", name)[0].strip()

    content = post["content"]["rendered"]
    cut = re.search(r'<h2[^>]*>[^<]*セットリスト[^<]*</h2>', content, re.I)
    head = content[:cut.start()] if cut else content
    tail = content[cut.start():] if cut else ""

    def parse_chunk(src, want_detail):
        lines = html_to_lines(src)
        tracks, cur = [], None
        for ln in lines:
            m = re.match(r"^\U0001F6B2\s*0*(\d+)", ln)
            is_stretch = ln.startswith("\u231b")
            if m or is_stretch:
                if cur:
                    tracks.append(cur)
                cur = {"no": int(m.group(1)) if m else 0,
                       "stretch": bool(is_stretch), "title": "", "artist": "",
                       "appleId": "", "bpm": "", "position": "",
                       "actions": "", "duration": ""}
                rest = re.sub(r"^[\U0001F6B2\u231b]\s*\d*\s*(Stretch)?", "",
                              ln).strip()
                if rest and "/" in rest:
                    cur["title"], cur["artist"] = split_title_artist(rest)
                continue
            if not cur or not ln:
                continue
            if ln.startswith("EMBED:"):
                mm = RE_TRACKID.search(ln)
                if mm and not cur["appleId"]:
                    cur["appleId"] = mm.group(1)
                continue
            if RE_DUR.match(ln):
                cur["duration"] = ln
                continue
            if ln.startswith("[") and want_detail:
                pos, bpm = parse_bracket(ln)
                if bpm:
                    if not cur["bpm"]:
                        cur["bpm"] = bpm
                        cur["position"] = pos or ""
                elif not cur["actions"]:
                    cur["actions"] = ln.strip().strip("[]").strip()
                continue
            if not cur["title"] and "/" in ln and not ln.startswith("["):
                cur["title"], cur["artist"] = split_title_artist(ln)
        if cur:
            tracks.append(cur)
        return [t for t in tracks if t["title"]]

    tracks = parse_chunk(head, True)
    if len(tracks) < 3:
        tracks = parse_chunk(tail or content, False)

    n = 0
    for t in tracks:
        if not t["stretch"]:
            n += 1
            t["no"] = n
    for t in tracks:
        if t["stretch"]:
            t["no"] = n + 1

    return {"name": name, "slug": post["slug"], "url": post["link"],
            "tracks": tracks}


# ------------------------------------------------------------ iTunes lookup

def lookup(ids):
    out = {}
    ids = [i for i in ids if i]
    for i in range(0, len(ids), 180):
        chunk = ids[i:i + 180]
        try:
            r = requests.get("https://itunes.apple.com/lookup", headers=HEADERS,
                             timeout=30,
                             params={"id": ",".join(chunk), "country": "jp",
                                     "entity": "song"})
            r.raise_for_status()
            for it in json.loads(r.text).get("results", []):
                if it.get("wrapperType") != "track":
                    continue
                out[str(it["trackId"])] = {
                    "title": it.get("trackName", ""),
                    "artist": it.get("artistName", ""),
                    "appleUrl": it.get("trackViewUrl", ""),
                    "previewUrl": it.get("previewUrl", ""),
                    "artwork": (it.get("artworkUrl100") or "").replace(
                        "100x100bb", "300x300bb"),
                }
        except Exception as e:
            print("  lookup失敗:", e)
        print(f"  lookup {min(i + 180, len(ids))}/{len(ids)}")
        time.sleep(1.0)
    return out


# -------------------------------------------------------------------- main

def main():
    apple = []
    if os.path.exists(APPLE_JSON):
        with open(APPLE_JSON, encoding="utf-8") as f:
            apple = json.load(f)
        print(f"Apple Music: {len(apple)} プログラム")
    else:
        print(f"{APPLE_JSON} が無いのでFEELCYCLISTのみで構築します")

    posts = fetch_wp_posts()
    reports = []
    for p in posts:
        try:
            rep = parse_report(p)
        except Exception as e:
            print("  解析失敗:", p.get("slug"), e)
            continue
        if rep["tracks"]:
            reports.append(rep)
    bpm_ok = sum(1 for r in reports for t in r["tracks"] if t["bpm"])
    total_tr = sum(len(r["tracks"]) for r in reports)
    print(f"FEELCYCLIST: {len(reports)} プログラム / {total_tr} 曲 "
          f"（BPM取得 {bpm_ok} 曲 = {bpm_ok * 100 // max(1, total_tr)}%）")

    # --- 照合用の索引を2種類つくる
    # (1) Apple Music のトラックID   (2) 曲名+アーティスト名の正規化キー
    # 古い記事には Apple Music の埋め込みが無く (1) が空になるため、(2) が要る。
    ap_ids = [{t.get("id") for t in a.get("tracks", []) if t.get("id")}
              for a in apple]
    ap_keys = [{norm(t.get("title", "")) + "|" + norm(t.get("artist", ""))
                for t in a.get("tracks", []) if t.get("title")}
               for a in apple]
    ap_titles = [{norm(t.get("title", ""))
                  for t in a.get("tracks", []) if t.get("title")}
                 for a in apple]
    ap_name = {norm_program(a["name"]): i for i, a in enumerate(apple)}

    # 手動対応表。どうしても照合できない組を aliases.json に書ける。
    #   {"BB2 1D": "BB2 ONE DIRECTION", ...}   FEELCYCLIST名 -> Apple Music名
    manual = {}
    if os.path.exists("aliases.json"):
        with open("aliases.json", encoding="utf-8") as f:
            manual = {norm_program(k): norm_program(v)
                      for k, v in json.load(f).items()}
        print(f"手動対応表 {len(manual)} 件")

    # --- 全組み合わせを評価してから、確度の高い順に確定する
    # 報告順の先着だと、弱い一致が先に良い相手を確保してしまうため。
    METHOD_RANK = {"manual": 4, "id": 3, "key": 2, "title": 1, "name": 0}
    THRESHOLD = {"id": OVERLAP_MIN, "key": OVERLAP_MIN, "title": 0.65}

    def overlaps(target, pool, kind):
        """しきい値を超える候補を [(apple_index, score)] で返す。"""
        out = []
        if not target:
            return out
        for i, s in enumerate(pool):
            if not s:
                continue
            ov = len(target & s)
            sc = ov / max(1, min(len(target), len(s)))
            if ov >= OVERLAP_MIN_COUNT and sc >= THRESHOLD[kind]:
                out.append((i, sc))
        return out

    cands = []          # (優先度, 一致度, report_index, apple_index, 方式)
    for r, rep in enumerate(reports):
        m = manual.get(norm_program(rep["name"]))
        if m is not None and m in ap_name:
            cands.append((METHOD_RANK["manual"], 1.0, r, ap_name[m], "manual"))

        rids = {t["appleId"] for t in rep["tracks"] if t["appleId"]}
        for i, sc in overlaps(rids, ap_ids, "id"):
            cands.append((METHOD_RANK["id"], sc, r, i, "id"))

        rk = {norm(t["title"]) + "|" + norm(t["artist"])
              for t in rep["tracks"] if t["title"]}
        for i, sc in overlaps(rk, ap_keys, "key"):
            cands.append((METHOD_RANK["key"], sc, r, i, "key"))

        rt = {norm(t["title"]) for t in rep["tracks"] if t["title"]}
        for i, sc in overlaps(rt, ap_titles, "title"):
            cands.append((METHOD_RANK["title"], sc, r, i, "title"))

        i = ap_name.get(norm_program(rep["name"]))
        if i is not None:
            cands.append((METHOD_RANK["name"], 1.0, r, i, "name"))

    cands.sort(key=lambda x: (-x[0], -x[1]))
    taken_rep, used = {}, set()
    how = {}
    for rank, sc, r, i, method in cands:
        if r in taken_rep or i in used:
            continue
        taken_rep[r] = (i, method, sc)
        used.add(i)
        how[method] = how.get(method, 0) + 1

    pairs = [(taken_rep.get(r, (None,))[0], rep)
             for r, rep in enumerate(reports)]
    for i in range(len(apple)):
        if i not in used:
            pairs.append((i, None))

    print("照合の内訳: " + " / ".join(f"{k}={v}" for k, v in how.items()))
    weak = [(reports[r]["name"], apple[i]["name"], sc)
            for r, (i, m, sc) in taken_rep.items()
            if m == "title" and sc < 0.85]
    if weak:
        print(f"曲名のみ・一致度85%未満の照合 {len(weak)} 件（要確認）:")
        for a, b, sc in sorted(weak, key=lambda x: x[2])[:15]:
            print(f"  {sc:.2f}  {a}  <->  {b}")

    have = {}
    for a in apple:
        for t in a.get("tracks", []):
            if t.get("id"):
                have[t["id"]] = t
    need = uniq([t["appleId"] for _, rep in pairs if rep
                 for t in rep["tracks"]
                 if t["appleId"] and t["appleId"] not in have])
    if need:
        print(f"補完が必要な楽曲: {len(need)} 件")
        have.update({k: {"id": k, **v} for k, v in lookup(need).items()})

    def yt(title, artist):
        return ("https://www.youtube.com/results?search_query="
                + requests.utils.quote(f"{title} {artist}".strip()))

    programs, unmatched = [], []
    for ai, rep in pairs:
        a = apple[ai] if ai is not None else None
        name = (a or rep)["name"]
        aliases = uniq([x for x in [a["name"] if a else None,
                                    rep["name"] if rep else None] if x])
        if a is None:
            unmatched.append(f"[FEELCYCLISTのみ] {rep['name']}  {rep['url']}")
        elif rep is None:
            unmatched.append(f"[Apple Musicのみ] {a['name']}")

        tracks, seen = [], set()

        def add(title, artist, apple_id, no, ex, src):
            key = norm(title) + "|" + norm(artist)
            if key in seen or not title:
                return
            seen.add(key)
            meta = have.get(apple_id, {}) if apple_id else {}
            tracks.append({
                "no": no,
                "title": meta.get("title") or title,
                "artist": meta.get("artist") or artist,
                "appleId": apple_id,
                "appleUrl": meta.get("appleUrl", ""),
                "previewUrl": meta.get("previewUrl", ""),
                "artwork": meta.get("artwork", ""),
                "ytUrl": yt(meta.get("title") or title,
                            meta.get("artist") or artist),
                "bpm": int(ex["bpm"]) if ex.get("bpm") else None,
                "position": ex.get("position", ""),
                "actions": ex.get("actions", ""),
                "duration": ex.get("duration", ""),
                "stretch": ex.get("stretch", False),
                "source": src,
            })

        if rep:
            for t in rep["tracks"]:
                add(t["title"], t["artist"], t["appleId"], t["no"], t,
                    "both" if a else "fc")
        if a:
            base = len(tracks)
            for t in a.get("tracks", []):
                add(t.get("title", ""), t.get("artist", ""), t.get("id", ""),
                    base + t.get("no", 0), {}, "am")

        tracks.sort(key=lambda x: x["no"])
        for i, t in enumerate(tracks, 1):
            t["no"] = i

        bl = [t["bpm"] for t in tracks if t["bpm"]]
        programs.append({
            "id": (a or {}).get("id") or ("fc:" + rep["slug"]),
            "name": name,
            "aliases": aliases,
            "description": (a or {}).get("description", ""),
            "playlistUrl": (a or {}).get("playlistUrl", ""),
            "reportUrl": rep["url"] if rep else "",
            "trackCount": len(tracks),
            "bpmRange": [min(bl), max(bl)] if bl else None,
            "bpmMedian": round(statistics.median(bl)) if bl else None,
            "tracks": tracks,
        })

    # --- 逆引き（曲単位のBPMを持たせる）
    smap = {}
    for p in programs:
        for t in p["tracks"]:
            k = norm(t["title"]) + "|" + norm(t["artist"])
            s = smap.setdefault(k, {
                "key": k, "title": t["title"], "artist": t["artist"],
                "appleUrl": t["appleUrl"], "previewUrl": t["previewUrl"],
                "artwork": t["artwork"], "ytUrl": t["ytUrl"],
                "bpm": None, "_bpms": [], "programs": []})
            for fld in ("appleUrl", "previewUrl", "artwork"):
                if not s[fld] and t[fld]:
                    s[fld] = t[fld]
            if t["bpm"]:
                s["_bpms"].append(t["bpm"])
            if not any(q["id"] == p["id"] for q in s["programs"]):
                s["programs"].append({
                    "id": p["id"], "name": p["name"], "no": t["no"],
                    "bpm": t["bpm"], "position": t["position"],
                    "actions": t["actions"]})

    for s in smap.values():
        if s["_bpms"]:
            # 同じ曲でもプログラムによりBPM表記が違うことがあるので最頻値
            s["bpm"] = statistics.mode(s["_bpms"])
        del s["_bpms"]

    songs = sorted(smap.values(),
                   key=lambda s: (-len(s["programs"]), s["title"].lower()))

    with open(OUT_PROGRAMS, "w", encoding="utf-8") as f:
        json.dump(programs, f, ensure_ascii=False, indent=1)
    with open(OUT_SONGS, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)
    with open(OUT_UNMATCHED, "w", encoding="utf-8") as f:
        f.write("\n".join(unmatched))

    both = sum(1 for p in programs if p["playlistUrl"] and p["reportUrl"])
    with_bpm = [s for s in songs if s["bpm"]]
    print("\n--- 結果 ---")
    print(f"プログラム {len(programs)}（両ソース照合済み {both}）")
    print(f"曲 {len(songs)}"
          f"（試聴可 {sum(1 for s in songs if s['previewUrl'])} / "
          f"BPMあり {len(with_bpm)}）")
    print(f"複数プログラム収録曲 "
          f"{sum(1 for s in songs if len(s['programs']) > 1)}")
    if with_bpm:
        bs = sorted(s["bpm"] for s in with_bpm)
        print(f"BPM範囲 {bs[0]}〜{bs[-1]} / 中央値 {statistics.median(bs):.0f}")
    print(f"照合できなかったプログラム {len(unmatched)} 件 → {OUT_UNMATCHED}")
    print("\n最多収録:")
    for s in songs[:5]:
        b = f" BPM{s['bpm']}" if s["bpm"] else ""
        print(f"  {s['title']} / {s['artist']}{b} … {len(s['programs'])}本")


if __name__ == "__main__":
    main()
