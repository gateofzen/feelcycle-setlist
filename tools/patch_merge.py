import io
import shutil

F = "merge_data.py"

OLD = '''    need = uniq([t["appleId"] for _, rep in pairs if rep
                 for t in rep["tracks"]
                 if t["appleId"] and t["appleId"] not in have])
'''

NEW = '''    # Apple側のトラックに試聴URLが無いこともある（取得スクリプトが
    # その項目を集めなかった場合）。appleId があるだけで「補完不要」と
    # 判断すると、試聴URLとBPM推定が丸ごと欠ける。ここで拾い直す。
    thin = [k for k, v in have.items() if not v.get("previewUrl")]
    if thin:
        print(f"Apple側のメタ情報が不足: {len(thin)} 件 → iTunesで補完します")
    need = uniq([t["appleId"] for _, rep in pairs if rep
                 for t in rep["tracks"]
                 if t["appleId"] and t["appleId"] not in have] + thin)
'''

src = io.open(F, encoding="utf-8").read()

if NEW.strip() in src:
    print("すでに適用済みです。何もしません。")
    raise SystemExit(0)

n = src.count(OLD)
if n != 1:
    raise SystemExit(f"想定した箇所が {n} 件見つかりました（1件であるべき）。中止します。")

shutil.copy2(F, F + ".bak")
io.open(F, "w", encoding="utf-8", newline="\n").write(src.replace(OLD, NEW))
print(f"{F} を更新しました（元のファイルは {F}.bak に残しています）")
