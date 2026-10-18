import sys, importlib.util, requests, re

spec = importlib.util.spec_from_file_location("m", "merge_data.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

slug = sys.argv[1] if len(sys.argv) > 1 else "bb2hit10"
r = requests.get("https://feel.shirataki.me/wp-json/wp/v2/posts",
                 params={"slug": slug, "_fields": "title,content"},
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
html = r.json()[0]["content"]["rendered"]

print("=== 目印の有無 ===")
for mark, label in [("\U0001F6B2", "自転車絵文字"), ("\u231b", "砂時計"),
                    ("BPM", "BPM表記"), ("embed.music.apple.com", "Apple埋め込み")]:
    print(f"  {label:<16} {html.count(mark)} 個")

cut = re.search(r"<h2[^>]*>[^<]*セットリスト[^<]*</h2>", html, re.I)
print(f"  セットリスト見出し  {'あり' if cut else 'なし'}")

print("\n=== 本文の先頭（空行を除く60行）===")
lines = [x for x in m.html_to_lines(html) if x][:60]
for i, ln in enumerate(lines):
    print(f"{i:>3} {ln[:96]}")
