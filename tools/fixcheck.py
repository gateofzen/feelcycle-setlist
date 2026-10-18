import pathlib, importlib.util, sys
from collections import Counter

# --- merge_data.py を修正する（絵文字の異体字セレクタに対応）
p = pathlib.Path("merge_data.py")
s = p.read_text(encoding="utf-8")
pairs = [
 (r'm = re.match(r"^\U0001F6B2\s*0*(\d+)", ln)',
  r'm = re.match(r"^\U0001F6B2\uFE0F?\s*0*(\d+)", ln)'),
 (r'is_stretch = ln.startswith("\u231b")',
  r'is_stretch = bool(re.match(r"^\u231b\uFE0F?", ln))'),
 (r'rest = re.sub(r"^[\U0001F6B2\u231b]\s*\d*\s*(Stretch)?", "",',
  r'rest = re.sub(r"^[\U0001F6B2\u231b]\uFE0F?\s*\d*\s*(Stretch)?", "",'),
]
done = 0
for old, new in pairs:
    if old in s:
        s = s.replace(old, new); done += 1
    elif new in s:
        done += 1
    else:
        print("!! 見つかりません:", old[:48])
p.write_text(s, encoding="utf-8")
print(f"修正 {done}/3 箇所\n")
if done < 3:
    sys.exit("修正できなかった箇所があります")

# --- 全記事を解析して効果を確認する
spec = importlib.util.spec_from_file_location("m", "merge_data.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

posts = m.fetch_wp_posts()
print(f"記事 {len(posts)} 件を解析します\n")
zero, few, ok = [], [], 0
counts = Counter()
for post in posts:
    try:
        rep = m.parse_report(post)
    except Exception as e:
        zero.append((post.get("slug","?"), "解析エラー", str(e)[:40])); continue
    n = len(rep["tracks"]); counts[n] += 1
    if n == 0: zero.append((post.get("slug","?"), rep["name"], ""))
    elif n < 5: few.append((post.get("slug","?"), rep["name"], n))
    else: ok += 1

print(f"曲が取れた記事      {ok}")
print(f"曲が少ない記事(1-4) {len(few)}")
print(f"曲が0の記事         {len(zero)}")
if zero:
    print(f"\n=== 曲が0の記事 ===")
    for slug, name, note in zero[:30]:
        print(f"  {name[:28]:<30}{slug:<22}{note}")
if few:
    print(f"\n=== 4曲以下の記事 ===")
    for slug, name, n in few[:20]:
        print(f"  {name[:28]:<30}{slug:<22}{n}曲")
