import statistics, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from data import CHANNELS

rows = []
for c in CHANNELS:
    v = c["views"]
    judged = v[c["recent"]:]
    hane = sum(x > c["subs"] for x in judged)
    med = statistics.median(judged)
    rows.append(dict(c, n=len(judged), hane=hane, rate=hane / len(judged),
                     med=med, med_ratio=med / c["subs"], top=max(v), top_ratio=max(v) / c["subs"]))

rows.sort(key=lambda r: -r["rate"])
lines = []
lines.append("| # | チャンネル | 区分 | 開設 | 登録者 | 形式 | 判定本数 | はねた本数 | はね率 | 中央値再生/登録者 | 最大再生/登録者 |")
lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
for i, r in enumerate(rows, 1):
    lines.append(f"| {i} | {r['name']} | {r['group']} | {r['created']} | {r['subs']:,} | {r['fmt']} | {r['n']} | {r['hane']} | {r['rate']:.0%} | {r['med_ratio']:.2f} | {r['top_ratio']:.1f} |")

out = os.path.join(os.path.dirname(__file__), "..", "output", "hane_ratio_table.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
