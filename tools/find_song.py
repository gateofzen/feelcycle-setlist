import json, re, sys, unicodedata

def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]", " ", s)
    s = re.sub(r"\b(feat|ft)\.\s*", "feat ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()

q = norm(" ".join(sys.argv[1:]))
print("検索語:", repr(q), "\n")
songs = json.load(open("songs.json", encoding="utf-8"))
programs = json.load(open("programs.json", encoding="utf-8"))

hits = [s for s in songs if all(t in
    norm(s["title"]) + " " + norm(s.get("titleEn") or "") + " " +
    norm(s["artist"]) + " " + norm(s.get("artistEn") or "") + " " +
    " ".join(norm(p["name"]) for p in s.get("programs", []))
    for t in q.split())]
print(f"=== songs.json での一致: {len(hits)} 件 ===")
for s in hits[:10]:
    print("  表示 :", s.get("titleEn") or s["title"], "/", s.get("artistEn") or s["artist"])
    print("  元値 :", s["title"], "/", s["artist"])
    print("  英語 :", s.get("titleEn", "(なし)"), "/", s.get("artistEn", "(なし)"))
    print("  BPM  :", s.get("bpm"), f"({s.get('bpmSource')})")
    print("  収録 :", ", ".join(p["name"] for p in s.get("programs", [])), "\n")
if not hits: print("  一致なし\n")

print("=== programs.json での一致 ===")
found = False
for p in programs:
    pn = norm(p["name"]) + " " + " ".join(norm(a) for a in p.get("aliases", []))
    name_hit = all(t in pn for t in q.split())
    tr = [t for t in p["tracks"] if all(x in norm(t["title"]) + " " + norm(t["artist"]) for x in q.split())]
    if not (name_hit or tr): continue
    found = True
    print(f"  {p['name']} ({p['trackCount']}曲)")
    for t in (tr if tr else p["tracks"]):
        mark = "  <<<" if t in tr else ""
        print(f"    {t['no']:>2} {t['title']} / {t['artist']}  BPM={t.get('bpm')}{mark}")
    print()
if not found: print("  一致なし\n")

if not hits:
    for w in [w for w in q.split() if len(w) > 2]:
        n = sum(1 for s in songs if w in norm(s["title"]) + norm(s.get("titleEn") or ""))
        print(f"  {w!r} を含む曲: {n} 件")
