# FEELCYCLE 選曲検索

FEELCYCLE の楽曲がどのプログラムで使われているかを、曲名・アーティスト名・
BPM から検索する個人用ツール。手持ちの Apple Music / YouTube プレイリストを
貼り付けて一括照合することもできる。

## 構成

    index.html        検索UI（これ1枚で完結）
    matcher.js        プレイリスト照合エンジン
    programs.json     プログラム別セットリスト（生成物）
    songs.json        曲→プログラムの逆引き（生成物）
    robots.txt        検索エンジンからの除外
    tools/            データ生成スクリプト

## データの作り方

1. Apple Music の FEELCYCLE キュレーターページで Console スクリプトを実行し、
   `apple_programs.json` を得る（`tools/export_snippets.md` 参照）
2. データを組み立てる

       cd tools
       python merge_data.py          # Apple Music × FEELCYCLIST をマージ
       python estimate_bpm.py --validate   # BPM推定の精度を確認
       python estimate_bpm.py        # BPMを補完
       python fetch_remixes.py --test "Titanium"   # 動作確認
       python fetch_remixes.py       # リミックスを収集
       cp programs.json songs.json ..

## ローカルで動かす

`file://` では JSON を読めないため、簡易サーバー経由で開く。

    python -m http.server 8000
    # http://localhost:8000

## データの出どころ

- プログラムとセットリスト: Apple Music の FEELCYCLE 公式キュレーター
- BPM・ハンドルポジション・動作、および Apple Music 非収録曲の補完:
  [FEELCYCLIST](https://feel.shirataki.me/)（シラタキ氏）
- リミックス情報: Deezer API

強度評価やレッスン解説は取り込んでいない。各プログラムから FEELCYCLIST の
該当記事へリンクしている。個人利用を前提とした構成。
