import json, sys, importlib.util, requests

spec = importlib.util.spec_from_file_location("m", "merge_data.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

slug = sys.argv[1] if len(sys.argv) > 1 else "bb2hit10"
r = requests.get("https://feel.shirataki.me/wp-json/wp/v2/posts",
                 params={"slug": slug, "_fields": "id,slug,link,title,content"},
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
posts = r.json()
if not posts:
    print("記事が見つかりません:", slug)
else:
    rep = m.parse_report(posts[0])
    print("記事タイトル:", posts[0]["title"]["rendered"])
    print("プログラム名として抽出:", repr(rep["name"]))
    print("抽出できた曲:", len(rep["tracks"]), "曲\n")
    for t in rep["tracks"]:
        print(f"  {t['no']:>2} {t['title']} / {t['artist']}")
        print(f"      BPM={t['bpm']} pos={t['position']!r} appleId={t['appleId']!r}")

print()
d = json.load(open("programs.json", encoding="utf-8"))
n = [p for p in d if not p.get("reportUrl")]
print(f"FEELCYCLISTと未照合: {len(n)} 件")
for p in sorted(n, key=lambda x: x["name"]):
    print("  ", p["name"], f"({p['trackCount']})")
