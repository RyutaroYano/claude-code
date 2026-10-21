#!/usr/bin/env python3
"""カット表（Markdown）＋ブロック音声＋Whisper の時間情報から episode.json を組み立てる。

使い方:
  python3 scripts/build_episode.py <回のID> <カット表のMarkdown> [<カット表のMarkdown> ...]
  例: python3 scripts/build_episode.py ep001 ../youtube_script_system_starter/06_案件進行中/第01回_風呂/0[4-9]_ブロック*.md

入力（public/episodes/<回のID>/ の下に置く）:
  audio/block01.wav  … ブロックごとの音声（ナレーション＋台詞）。カット表のファイル順に block01, block02, …
  timing/block01.json … その音声を Whisper にかけた結果（言葉ごとの時間）。形式は次のどれでもよい
       A) openai-whisper: {"segments":[{"words":[{"word":"昔","start":0.1,"end":0.3}]}]}
       B) @remotion/whisper-cpp の toCaptions: [{"text":"昔","startMs":100,"endMs":300}]
       C) [{"text":"昔","start":0.1,"end":0.3}]
  images/cut001.png  … カット番号と同じ名前の画像（png / jpg / webp）
  video/cut001.mp4   … 動画生成したカット（あれば画像より優先）

出力:
  episodes/<回のID>/episode.json  … Remotion に渡すファイル
  episodes/<回のID>/build_report.md … 足りない画像、10秒を超えて分けたカット、時間合わせの注意

ルール（設計書 第7章・第14章）:
  - カットの切れ目はナレーションの区切り。10秒を超えるカットは、テロップの区切りで分ける（cut012a, cut012b …）。
  - テロップは1行16字まで、2行まで。句点（。）と読点（、）で区切る。文字は台本のものを使い、Whisper の文字は使わない。
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_CUT_SEC = 10.0
MAX_PER_LINE = 16
MAX_LINES = 2
LEAD_IN_SEC = 0.3  # 各ブロックの音声の前に置く間
FPS, WIDTH, HEIGHT = 30, 1920, 1080

MOTION = {"寄る": "zoomIn", "引く": "zoomOut", "左へ流す": "panLeft", "右へ流す": "panRight",
          "動画生成": "zoomIn", "なし": "none"}
PUNCT = re.compile(r"[\s、。，．,.!?！？「」『』（）()・…\-―ー〜~:：]")


def norm(s: str) -> str:
    return PUNCT.sub("", s)


# ---------- カット表を読む ----------
def parse_cut_table(md_path: Path) -> list[dict]:
    rows, header = [], None
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            if header and rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            if "カット" in cells[0] and any("ナレーション" in c for c in cells):
                header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        num = re.sub(r"\D", "", row.get("カット", ""))
        if not num:
            continue
        rows.append({
            "id": f"cut{int(num):03d}",
            "narration": row.get("ナレーション", ""),
            "line": re.sub(r"^[^：:]{1,15}[：:]", "", row.get("台詞", "")).strip(),
            "screen": row.get("画面", ""),
            "motion_ja": row.get("動かし方", ""),
        })
    return rows


def spoken(cut: dict) -> str:
    """そのカットで話される文。順番はナレーション → 台詞。"""
    return cut["narration"] + cut["line"]


# ---------- 時間情報を読む ----------
def load_words(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [w for s in raw.get("segments", []) for w in s.get("words", [])]
    words = []
    for w in items:
        text = w.get("word", w.get("text", ""))
        start = w.get("start", w.get("startMs", 0) / 1000)
        end = w.get("end", w.get("endMs", 0) / 1000)
        if norm(text):
            words.append({"text": norm(text), "start": float(start), "end": float(end)})
    return words


def char_times(words: list[dict]) -> tuple[str, list[float]]:
    """Whisper の文字列と、1文字ごとの話し始めの時刻。"""
    text, times = "", []
    for w in words:
        n = len(w["text"])
        for i in range(n):
            times.append(w["start"] + (w["end"] - w["start"]) * i / n)
        text += w["text"]
    return text, times


def align(script: str, whisper: str) -> list[int | None]:
    """台本の各文字が、Whisper の何文字目に当たるか（見つからなければ None）。"""
    mapping: list[int | None] = [None] * len(script)
    sm = difflib.SequenceMatcher(None, script, whisper, autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            mapping[a + k] = b + k
    return mapping


def time_at(idx: int, mapping, times, total: float, n: int) -> float:
    """台本の idx 文字目が話される時刻。見つからなければ前後から補う。"""
    if not times:
        return total * idx / max(n, 1)
    for j in range(idx, len(mapping)):
        if mapping[j] is not None:
            return times[min(mapping[j], len(times) - 1)]
    return total


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return None


# ---------- テロップ ----------
def chunks(text: str) -> list[str]:
    limit = MAX_PER_LINE * MAX_LINES
    out = []
    for sent in re.findall(r"[^。！？]+[。！？]?", text) or [text]:
        if len(sent) <= limit:
            out.append(sent)
            continue
        buf = ""
        for part in re.findall(r"[^、]+、?", sent):
            while len(part) > limit:  # 読点がなく長すぎる場合は機械的に切る
                if buf:
                    out.append(buf)
                    buf = ""
                out.append(part[:limit])
                part = part[limit:]
            if len(buf + part) > limit and buf:
                out.append(buf)
                buf = ""
            buf += part
        if buf:
            out.append(buf)
    return out


def two_lines(s: str) -> str:
    if len(s) <= MAX_PER_LINE:
        return s
    mid = len(s) / 2
    cands = [i + 1 for i, ch in enumerate(s[:-1]) if ch in "、をにがはでとへもの" and 0 < i + 1 < len(s)]
    cands = [i for i in cands if len(s[:i]) <= MAX_PER_LINE and len(s[i:]) <= MAX_PER_LINE] or [min(MAX_PER_LINE, len(s) - 1)]
    cut = min(cands, key=lambda i: abs(i - mid))
    return s[:cut] + "\n" + s[cut:]


# ---------- 本体 ----------
def find_media(ep_dir: Path, ep: str, cut_id: str, base_id: str) -> tuple[dict, bool]:
    for cid in (cut_id, base_id):
        v = ep_dir / "video" / f"{cid}.mp4"
        if v.exists():
            return {"video": f"episodes/{ep}/video/{cid}.mp4"}, True
        for ext in ("png", "jpg", "jpeg", "webp"):
            p = ep_dir / "images" / f"{cid}.{ext}"
            if p.exists():
                return {"image": f"episodes/{ep}/images/{cid}.{ext}"}, True
    return {"image": "episodes/_common/missing.png"}, False


def ensure_missing_placeholder() -> None:
    p = ROOT / "public/episodes/_common/missing.png"
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (1920, 1080), (40, 40, 40))
        d = ImageDraw.Draw(im)
        for x in range(0, 1920, 120):
            d.line([(x, 0), (x, 1080)], fill=(60, 60, 60))
        d.rectangle([660, 480, 1260, 600], outline=(200, 200, 200), width=4)
        im.save(p)
    except ImportError:
        p.write_bytes(b"")


def build(ep: str, md_files: list[Path]) -> None:
    ep_dir = ROOT / "public/episodes" / ep
    report = [f"# 組み立ての報告：{ep}", ""]
    missing, splits, warnings = [], [], []
    cuts_out, audio_out = [], []
    t0 = 0.0

    for bi, md in enumerate(md_files, start=1):
        rows = parse_cut_table(md)
        if not rows:
            warnings.append(f"{md.name}：カット表が見つからない")
            continue
        audio = ep_dir / "audio" / f"block{bi:02d}.wav"
        timing = ep_dir / "timing" / f"block{bi:02d}.json"
        words = load_words(timing) if timing.exists() else []
        if not words:
            warnings.append(f"block{bi:02d}：時間情報（{timing.name}）がない。文字数で秒数を割り振った（1秒5文字）")
        w_text, w_times = char_times(words)
        script = "".join(norm(spoken(c)) for c in rows)
        mapping = align(script, w_text) if words else [None] * len(script)
        matched = sum(m is not None for m in mapping) / max(len(script), 1)
        if words and matched < 0.8:
            warnings.append(f"block{bi:02d}：台本と音声の一致が {matched:.0%}。読み間違いや台本との食い違いがないか確かめる")
        dur = wav_duration(audio) if audio.exists() else None
        if not audio.exists():
            warnings.append(f"block{bi:02d}：音声（{audio.name}）がない")
        total = dur or (w_times[-1] + 0.5 if w_times else len(script) / 5.0)
        if not words:
            w_times = []

        # カットごとの始まり（ブロック内の秒）
        starts, pos = [], 0
        for c in rows:
            starts.append(0.0 if not starts else time_at(pos, mapping, w_times, total, len(script)))
            pos += len(norm(spoken(c)))
        ends = starts[1:] + [total]

        for ci, c in enumerate(rows):
            # テロップの区切りと時刻（ブロック内の秒）
            cps, cpos = [], sum(len(norm(spoken(r))) for r in rows[:ci])
            for ch in chunks(spoken(c)):
                cps.append((ch, time_at(cpos, mapping, w_times, total, len(script)) if cpos else 0.0))
                cpos += len(norm(ch))
            cps = [(t, max(s, starts[ci])) for t, s in cps]
            length = ends[ci] - starts[ci]
            # 10秒を超えたら、10秒以内に収まるいちばん遅いテロップの区切りで分ける（足りなければ10秒で切る）
            bounds = [starts[ci]]
            while ends[ci] - bounds[-1] > MAX_CUT_SEC:
                cand = [s for _, s in cps if bounds[-1] + 1.0 < s <= bounds[-1] + MAX_CUT_SEC]
                bounds.append(max(cand) if cand else bounds[-1] + MAX_CUT_SEC)
            bounds.append(ends[ci])
            bounds = sorted(set(bounds))
            if len(bounds) - 1 > 1:
                splits.append(f"{c['id']}（{length:.1f}秒）→ {len(bounds) - 1}つに分けた。分けた分の画像（{c['id']}a, b…）と画面の指示が要る")
            for k in range(len(bounds) - 1):
                sid = c["id"] + ("" if len(bounds) == 2 else "abcdefgh"[k])
                media, ok = find_media(ep_dir, ep, sid, c["id"])
                if not ok:
                    missing.append(f"{sid}：{c['screen'] or '（画面の指示なし）'}")
                caps = []
                inside = [(t, s) for t, s in cps if bounds[k] - 0.01 <= s < bounds[k + 1]]
                for j, (txt, s) in enumerate(inside):
                    e = inside[j + 1][1] if j + 1 < len(inside) else bounds[k + 1] - 0.1
                    caps.append({"text": two_lines(txt), "startSec": round(s - bounds[k], 2),
                                 "endSec": round(max(e, s + 0.5) - bounds[k], 2)})
                motion = "none" if "video" in media else MOTION.get(c["motion_ja"].split("（")[0].strip(), "zoomIn")
                cuts_out.append({"id": sid, "durationSec": round(bounds[k + 1] - bounds[k] + (LEAD_IN_SEC if not cuts_out else 0), 2),
                                 **media, "motion": motion, "narration": spoken(c), "captions": caps})
        # 最初のカットだけ前に間を置いたので、テロップをずらす
        if bi == 1 and cuts_out:
            for cap in cuts_out[0]["captions"]:
                cap["startSec"] = round(cap["startSec"] + LEAD_IN_SEC, 2)
                cap["endSec"] = round(cap["endSec"] + LEAD_IN_SEC, 2)
        audio_out.append({"src": f"episodes/{ep}/audio/{audio.name}", "startSec": round(t0 + LEAD_IN_SEC, 2)})
        t0 += total

    ensure_missing_placeholder()
    episode = {"title": ep, "fps": FPS, "width": WIDTH, "height": HEIGHT, "crossfadeSec": 0.5,
               "cuts": cuts_out, "audio": [a for a in audio_out if (ROOT / "public" / a["src"]).exists()]}
    out_dir = ROOT / "episodes" / ep
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "episode.json").write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8")

    total_sec = sum(c["durationSec"] for c in cuts_out)
    report += [f"- カット数：{len(cuts_out)}", f"- 長さ：{int(total_sec // 60)}分{total_sec % 60:.0f}秒", ""]
    report += ["## 足りない画像・動画（カット番号と同じ名前で images/ か video/ に置く）"] + [f"- {m}" for m in missing or ["なし"]] + [""]
    report += ["## 10秒を超えて分けたカット"] + [f"- {s}" for s in splits or ["なし"]] + [""]
    report += ["## 注意"] + [f"- {w}" for w in warnings or ["なし"]]
    (out_dir / "build_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1], [Path(p) for p in sys.argv[2:]])
