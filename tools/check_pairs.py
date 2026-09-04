# -*- coding: utf-8 -*-
"""照合結果の確認: 名前が違うのに結びついたペアを一覧する"""
import json, sys

d = json.load(open('programs.json', encoding='utf-8'))
flat = lambda s: s.lower().replace(' ', '').replace('「', '').replace('」', '')

pairs = [p for p in d if len(p.get('aliases', [])) > 1
         and flat(p['aliases'][0]) != flat(p['aliases'][1])]
print(f'名前が異なるのに照合されたペア: {len(pairs)} 件\n')
for p in sorted(pairs, key=lambda x: x['name']):
    print(f"  {p['aliases'][0]:<30} <- {p['aliases'][1]}")

both = sum(1 for p in d if p['playlistUrl'] and p['reportUrl'])
am = sum(1 for p in d if p['playlistUrl'] and not p['reportUrl'])
fc = sum(1 for p in d if p['reportUrl'] and not p['playlistUrl'])
print(f'\n合計 {len(d)} プログラム')
print(f'  両ソース照合済み {both}')
print(f'  Apple Musicのみ  {am}')
print(f'  FEELCYCLISTのみ  {fc}')
assert both + am + fc == len(d), '内訳が合いません'
dup = len(d) - len({p['id'] for p in d})
print(f'  ID重複 {dup}' + ('  ← 異常' if dup else ''))
