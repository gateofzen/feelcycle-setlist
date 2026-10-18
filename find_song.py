# -*- coding: utf-8 -*-
"""
曲やプログラムがデータにどう入っているかを調べる

検索で出てこない曲の原因を切り分けるための道具。
曲名の一部、アーティスト名、プログラム名のどれでも渡せる。

  python find_song.py "What Are You Waiting For"
  python find_song.py "BB2 HIT 10"
  python find_song.py "waiting"
"""

import json
import re
import sys
import unicodedata

SONGS = "songs.json"
PROGRAMS = "programs.json"


def norm(s):
    """サイト側の検索と同じ正規化。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]", " ", s)
    s = re.sub(r"\b(feat|ft)\.\s*", "feat ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def main():
    if len(sys.argv) < 2:
        sys.exit("検索語を指定してください")
    q = norm(" ".join(sys.argv[1:]))
    print(f"検索語（正規化後）: {q!r}\n")

    songs = json.load(open(SONGS, encoding="utf-8"))
    programs = json.load(open(PROGRAMS, encoding="utf-8"))

    # --- 1. サイトと同じ条件で曲を探す
    hits = []
    for s in songs:
        hay = (norm(s["title"]) + " " + norm(s.get("titleEn") or "") + " "
               + norm(s["artist"]) + " " + norm(s.get("artistEn") or "") + " "
               + " ".join(norm(p["name"]) for p in s.get("programs", [])))
        if all(t in hay for t in q.split()):
            hits.append(s)

    print(f"=== songs.json での一致: {len(hits)} 件 ===")
    for s in hits[:10]:
        print(f"  表示名 : {s.get('titleEn') or s['title']} / "
              f"{s.get('artistEn') or s['artist']}")
        print(f"  元の値 : {s['title']} / {s['artist']}")
        print(f"  英語   : {s.get('titleEn', '(なし)')} / {s.get('artistEn', '(なし)')}")
        print(f"  BPM    : {s.get('bpm')} ({s.get('bpmSource')})"
              f"  試聴={'あり' if s.get('previewUrl') else 'なし'}")
        print(f"  収録   : {', '.join(p['name'] for p in s.get('programs', []))}")
        print()
    if not hits:
        print("  一致なし\n")

    # --- 2. プログラムのセットリストを直接見る
    print("=== programs.json のセットリストでの一致 ===")
    found = False
    for p in programs:
        pn = norm(p["name"]) + " " + " ".join(norm(a) for a in p.get("aliases", []))
        name_hit = all(t in pn for t in q.split())
        tracks = [t for t in p["tracks"]
                  if all(x in norm(t["title"]) + " " + norm(t["artist"])
                         for x in q.split())]
        if not (name_hit or tracks):
            continue
        found = True
        print(f"  {p['name']}  （{p['trackCount']}曲）")
        if p.get("aliases"):
            print(f"    別名: {', '.join(p['aliases'])}")
        for t in (tracks if tracks else p["tracks"] if name_hit else []):
            mark = "  ←該当" if t in tracks else ""
            print(f"    {t['no']:>2} {t['title']} / {t['artist']}"
                  f"  BPM={t.get('bpm')}{mark}")
        print()
    if not found:
        print("  一致なし\n")

    # --- 3. 部分一致でも拾えないときの手がかり
    if not hits:
        words = [w for w in q.split() if len(w) > 2]
        if words:
            print("=== 一部の語だけで探した場合 ===")
            for w in words:
                n = sum(1 for s in songs
                        if w in norm(s["title"]) + norm(s.get("titleEn") or ""))
                print(f"  {w!r} を含む曲: {n} 件")


if __name__ == "__main__":
    main()
