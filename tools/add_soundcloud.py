# -*- coding: utf-8 -*-
"""
お気に入りリミックス（SoundCloud）の登録

SoundCloud は API のオープン登録が終了しており、認証情報なしで検索できない。
そのため自動収集はせず、自分で見つけたものを手で登録する。
埋め込みプレイヤーは認証不要なので、登録すればサイト内で再生できる。

  python add_soundcloud.py "Clocks" https://soundcloud.com/xxx/clocks-haas-remix
  python add_soundcloud.py "Clocks" https://soundcloud.com/xxx/... --label "HAAS Remix"
  python add_soundcloud.py --list                 登録済みを一覧
  python add_soundcloud.py --remove "Clocks"      その曲の登録を削除

soundcloud.json（曲キー -> [{url, label}]）を更新する。
このファイルはサイトが起動時に読み込む。無くても動作する。
"""

import argparse
import json
import os
import re
import sys
import unicodedata

SONGS = "songs.json"
OUT = "soundcloud.json"


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def load():
    return json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}


def save(table):
    json.dump(table, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def find(songs, query):
    """曲名の部分一致で候補を返す。"""
    q = norm(query)
    hits = [s for s in songs if q in norm(s["title"])]
    if not hits:
        hits = [s for s in songs if q in norm(s["title"] + " " + s["artist"])]
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song", nargs="?", help="曲名（部分一致）")
    ap.add_argument("url", nargs="?", help="SoundCloud のトラックURL")
    ap.add_argument("--label", help="表示名（省略時はURLから推測）")
    ap.add_argument("--list", action="store_true", help="登録済みを一覧")
    ap.add_argument("--remove", metavar="SONG", help="その曲の登録を削除")
    args = ap.parse_args()

    songs = json.load(open(SONGS, encoding="utf-8"))
    by_key = {s["key"]: s for s in songs}
    table = load()

    if args.list:
        if not table:
            print("まだ登録がありません")
            return
        for k, items in table.items():
            s = by_key.get(k)
            name = f"{s['title']} / {s['artist']}" if s else k
            print(f"{name}")
            for it in items:
                print(f"    {it.get('label') or ''}  {it['url']}")
        print(f"\n{len(table)} 曲 / {sum(len(v) for v in table.values())} 件")
        return

    if args.remove:
        hits = find(songs, args.remove)
        if not hits:
            sys.exit("該当する曲がありません")
        for s in hits:
            if s["key"] in table:
                del table[s["key"]]
                print(f"削除: {s['title']} / {s['artist']}")
        save(table)
        return

    if not args.song or not args.url:
        ap.print_help()
        return

    if "soundcloud.com" not in args.url:
        sys.exit("SoundCloud のトラックURLを指定してください")

    hits = find(songs, args.song)
    if not hits:
        sys.exit(f"'{args.song}' に一致する曲がありません")
    if len(hits) > 1:
        print(f"候補が {len(hits)} 件あります。番号を選んでください。")
        for i, s in enumerate(hits[:20]):
            progs = ", ".join(p["name"] for p in s.get("programs", [])[:3])
            print(f"  [{i}] {s['title']} / {s['artist']}   ({progs})")
        try:
            sel = int(input("番号: ").strip())
            target = hits[sel]
        except (ValueError, IndexError):
            sys.exit("中止しました")
    else:
        target = hits[0]

    label = args.label
    if not label:
        # URL末尾から推測: .../clocks-haas-remix -> Clocks Haas Remix
        tail = args.url.rstrip("/").split("/")[-1].split("?")[0]
        label = tail.replace("-", " ").title()

    items = table.setdefault(target["key"], [])
    if any(it["url"] == args.url for it in items):
        print("登録済みです")
        return
    items.append({"url": args.url, "label": label})
    save(table)

    print(f"登録: {target['title']} / {target['artist']}")
    print(f"      {label}")
    print(f"      {args.url}")
    print(f"\nsoundcloud.json を feelcycle-setlist 直下にコピーしてください。")


if __name__ == "__main__":
    main()
