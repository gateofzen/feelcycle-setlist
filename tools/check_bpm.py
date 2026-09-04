# -*- coding: utf-8 -*-
"""推定BPMが妥当かを確認する"""
import json
import statistics
from collections import Counter

songs = json.load(open('songs.json', encoding='utf-8'))
programs = json.load(open('programs.json', encoding='utf-8'))

rep = [s['bpm'] for s in songs if s.get('bpmSource') == 'report' and s.get('bpm')]
est = [s['bpm'] for s in songs if s.get('bpmSource') == 'estimated' and s.get('bpm')]


def band(v):
    for lo in (60, 90, 105, 120, 135, 150, 170):
        if v < lo + (15 if lo >= 90 else 30):
            return lo
    return 185


print(f"実測 {len(rep)} 曲 / 推定 {len(est)} 曲\n")
print("テンポ帯の分布（実測 vs 推定）")
br, be = Counter(map(band, rep)), Counter(map(band, est))
for lo in sorted(set(br) | set(be)):
    r = br.get(lo, 0) * 100 // max(1, len(rep))
    e = be.get(lo, 0) * 100 // max(1, len(est))
    flag = '  ← 偏り' if abs(r - e) > 12 else ''
    print(f"  {lo:>3}台  実測 {r:>3}%  推定 {e:>3}%{flag}")

print(f"\n中央値  実測 {statistics.median(rep):.0f} / 推定 {statistics.median(est):.0f}")

out = [s for s in songs if s.get('bpmSource') == 'estimated'
       and s.get('bpm') and not (70 <= s['bpm'] <= 185)]
print(f"\n実用域を外れた推定値: {len(out)} 曲")
for s in out[:10]:
    print(f"  {s['bpm']}  {s['title'][:40]} / {s['artist'][:24]}")

print("\nBPMが1曲も無いプログラム:")
for p in programs:
    if not p.get('bpmMedian'):
        print(f"  {p['name']}  ({p['trackCount']}曲)")

nb = [s for s in songs if not s.get('bpm')]
print(f"\nBPM不明の曲 {len(nb)} 件（試聴URLが無く推定できなかったもの）")
for s in nb[:8]:
    print(f"  {s['title'][:44]} / {s['artist'][:24]}")
