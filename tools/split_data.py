# -*- coding: utf-8 -*-
"""
songs.json からリミックス情報を切り出して別ファイルにする。

リミックスは初期表示に不要なので、サイトでは後から遅延読み込みする。

  python split_data.py

  songs.json    リミックスを除いた検索用データ（軽い）
  remixes.json  曲キー -> リミックス配列（後から読む）
"""

import json
import os

SONGS = "songs.json"
REMIXES = "remixes.json"


def mb(path):
    return os.path.getsize(path) / 1024 / 1024


def main():
    songs = json.load(open(SONGS, encoding="utf-8"))
    before = mb(SONGS)

    table, moved = {}, 0
    for s in songs:
        rx = s.pop("remixes", None)
        if rx:
            table[s["key"]] = rx
            moved += len(rx)
        # 「リミックスがある曲だけ」の絞り込み用に件数だけ残す
        s["remixCount"] = len(rx) if rx else 0

    if not table:
        print("リミックス情報が見つかりません。"
              "\nsongs.json が既に分割済みか、fetch_remixes.py が未実行です。"
              "\n何も書き換えずに終了します。")
        return

    with open(SONGS, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=1)
    with open(REMIXES, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{moved} 件のリミックスを {len(table)} 曲分だけ切り出しました\n")
    print(f"  songs.json    {before:6.1f} MB -> {mb(SONGS):5.1f} MB")
    print(f"  remixes.json                 {mb(REMIXES):5.1f} MB（遅延読み込み）")
    print("\nGitHub Pages は自動で gzip 圧縮するため、"
          "実際の転送量はこの3割程度になります。")


if __name__ == "__main__":
    main()
