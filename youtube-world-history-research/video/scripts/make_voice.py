#!/usr/bin/env python3
"""カット表（Markdown）から、Gemini の音声生成でブロックごとの音声を作る。

使い方:
  python3 scripts/make_voice.py <回のID> <カット表のMarkdown> ... [--dry-run] [--only 1,3] [--trial]
  例: python3 scripts/make_voice.py ep001 ../05_各回/第01回_大火/0[4-9]_ブロック*.md --dry-run

  --dry-run  APIを呼ばずに、読み上げる文（読み方を置き換えた後）と、呼ぶ回数だけを出す
  --only     作るブロックの番号（カンマ区切り）
  --trial    声の試し録り。ブロック01の最初の約30秒分だけを、--voices の声で1回ずつ作る
  --voices   --trial で比べる声（カンマ区切り。既定は台帳の声）

APIキーは、環境の Network secrets（ホスト generativelanguage.googleapis.com、ヘッダー X-Goog-Api-Key）に登録してあれば、
つなぐときに自動で付く（このスクリプトもClaudeも、キーの中身は見ない）。手元のPCで流すときだけ、環境変数 GEMINI_API_KEY に入れる。

出力（public/episodes/<回のID>/ の下）:
  audio/block01.wav …   ブロックごとの音声（build_episode.py が読む）
  audio/parts/…         区切りごとの音声。同じ設定・同じ文なら作り直さない（無料枠の回数を節約するため）
  audio/voice_report.md 区切りごとの文、声、長さ、1分あたりの字数

決まり（設計書 第15章）:
  - モデル・声の名前・指示文は voices.json（声の台帳）のものを、一字一句そのまま使う。指示文は英語で、本文の前に置き、1行空けて本文。
  - 読み方の辞書（設計書 第15章）の言葉は、ひらがなに置き換えて渡す。
  - 「（ここで間をあける）」のところで区切り、pause_sec の無音を入れる。台詞は役ごとの声で別に作る。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT.parent / "01_設計書" / "channel_design_spec.md"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATE = 24000  # Gemini の音声は 24kHz・16bit・モノラル
PAUSE_MARK = "（ここで間をあける）"
MAX_RUN_CHARS = 700  # 1回で読ませる長さの上限（長すぎると途中で調子が崩れやすい）
TRIAL_CHARS = 150    # 試し録り：約30秒（1分300字）


def count(s: str) -> int:
    return len(re.sub(r"[\s、。「」『』（）・？！]", "", s))


# ---------- 読み方の辞書 ----------
def load_readings() -> list[tuple[str, str]]:
    pairs, inside = [], False
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("### 読み方の辞書"):
            inside = True
            continue
        if inside and line.startswith("#"):
            break
        if not (inside and line.startswith("|")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("言葉", "") or set(cells[0]) <= set("-: "):
            continue
        words, reads = cells[0].split("／"), cells[1].split("／")
        if len(words) == len(reads):
            pairs += zip(words, reads)
    return sorted(pairs, key=lambda p: -len(p[0]))  # 長い言葉から置き換える（火除地 → 火除）


def apply_readings(text: str, readings: list[tuple[str, str]]) -> str:
    for word, read in readings:
        text = text.replace(word, read)
    return text


# ---------- カット表を読む ----------
def parse_cuts(md: Path) -> list[dict]:
    cuts, header = [], None
    for line in md.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            if "カット" in cells[0] and any("ナレーション" in c for c in cells):
                header = cells
            continue
        row = dict(zip(header, cells))
        if not re.fullmatch(r"\d{3}", row.get("カット", "")):
            continue
        m = re.match(r"^([^：:「]{1,15})[：:]\s*「(.*)」$", row.get("台詞", ""))
        cuts.append({"cut": row["カット"], "narration": row.get("ナレーション", ""),
                     "role": m.group(1) if m else None, "line": m.group(2) if m else ""})
    return cuts


def segments(cuts: list[dict]) -> list[dict]:
    """ナレーションを続けて読む区切りと、台詞の区切りに分ける。間は {"pause": 秒} で表す。"""
    out, run, run_cuts = [], "", []

    def flush():
        nonlocal run, run_cuts
        if run:
            out.append({"kind": "narration", "text": run, "cuts": run_cuts})
        run, run_cuts = "", []

    for c in cuts:
        text = c["narration"]
        if text.startswith(PAUSE_MARK):
            flush()
            if out:
                out.append({"pause": True})
            text = text[len(PAUSE_MARK):]
        if run and count(run) + count(text) > MAX_RUN_CHARS:
            flush()
        if text:
            run += text
            run_cuts.append(c["cut"])
        if c["role"]:
            flush()
            out.append({"kind": "line", "role": c["role"], "text": c["line"], "cuts": [c["cut"]]})
    flush()
    return out


# ---------- Gemini ----------
def tts(text: str, voice: str, model: str, key: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-goog-api-key"] = key
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.load(r)
            part = data["candidates"][0]["content"]["parts"][0]
            return base64.b64decode(part["inlineData"]["data"])
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code == 429:
                sys.exit(f"回数の上限に達しました（429）。作れた分は audio/parts に残っています。時間をおいて同じコマンドを流すと続きから作ります。\n{msg}")
            if e.code >= 500 and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            sys.exit(f"Gemini がエラーを返しました（{e.code}）：{msg}")
        except (KeyError, IndexError) as e:
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            sys.exit(f"音声が返ってきませんでした：{e}")
    raise RuntimeError("unreachable")


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(RATE * sec)


def make_part(parts_dir: Path, name: str, prompt: str, voice: str, model: str, key: str | None) -> Path:
    h = hashlib.sha1(f"{model}\n{voice}\n{prompt}".encode()).hexdigest()[:10]
    path = parts_dir / f"{name}_{voice}_{h}.wav"
    if not path.exists():
        print(f"  作成中：{path.name}", flush=True)
        write_wav(path, tts(prompt, voice, model, key))
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("md", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--trial", action="store_true")
    ap.add_argument("--voices", default="")
    a = ap.parse_args()

    ledger = json.loads((ROOT / "voices.json").read_text(encoding="utf-8"))
    model, nar = ledger["model"], ledger["narrator"]
    readings = load_readings()
    key = os.environ.get("GEMINI_API_KEY")

    out_dir = ROOT / "public" / "episodes" / a.episode / "audio"
    parts_dir = out_dir / "parts"
    blocks = [segments(parse_cuts(Path(p))) for p in a.md]

    if a.trial:
        first = next(s for s in blocks[0] if s.get("kind") == "narration")
        text = ""
        for sent in re.findall(r"[^。]+。", first["text"]):
            if count(text) >= TRIAL_CHARS:
                break
            text += sent
        prompt = nar["instruction"] + "\n\n" + apply_readings(text, readings)
        print(prompt)
        for v in (a.voices.split(",") if a.voices else [nar["voice"]]):
            if a.dry_run:
                continue
            p = make_part(parts_dir, "trial", prompt, v.strip(), model, key)
            print(f"{v}: {p}  {len(read_pcm(p)) / 2 / RATE:.1f}秒")
        return

    only = {int(x) for x in a.only.split(",") if x}
    report = ["# 声の記録", "", f"- モデル：{model}", f"- ナレーター：{nar['voice']}", "",
              "| ブロック | 区切り | カット | 声 | 字数 | 秒 | 1分の字数 |", "|---|---|---|---|---|---|---|"]
    calls = 0
    for bi, segs in enumerate(blocks, 1):
        if only and bi not in only:
            continue
        pcm, n = b"", 0
        for s in segs:
            if s.get("pause"):
                pcm += silence(ledger["pause_sec"])
                continue
            n += 1
            if s["kind"] == "narration":
                voice, instr = nar["voice"], nar["instruction"]
            else:
                role = ledger["roles"].get(s["role"])
                if role is None:
                    sys.exit(f"voices.json に役「{s['role']}」がありません（ブロック{bi:02d}、カット{s['cuts'][0]}）。")
                voice, instr = role["voice"], ledger["line_instruction"].format(role=role["role_en"])
            prompt = instr + "\n\n" + apply_readings(s["text"], readings)
            label = f"{s['cuts'][0]}〜{s['cuts'][-1]}" if len(s["cuts"]) > 1 else s["cuts"][0]
            if a.dry_run:
                calls += 1
                print(f"\n[ブロック{bi:02d}・区切り{n}・{voice}・{count(s['text'])}字・カット{label}]\n{prompt}")
                continue
            p = make_part(parts_dir, f"block{bi:02d}_s{n:02d}", prompt, voice, model, key)
            seg = read_pcm(p)
            if pcm and not pcm.endswith(silence(ledger["pause_sec"])):
                pcm += silence(ledger["gap_sec"])
            pcm += seg
            sec = len(seg) / 2 / RATE
            report.append(f"| {bi:02d} | {n} | {label} | {voice} | {count(s['text'])} | {sec:.1f} | {count(s['text']) / sec * 60:.0f} |")
        if not a.dry_run:
            write_wav(out_dir / f"block{bi:02d}.wav", pcm)
            print(f"block{bi:02d}.wav  {len(pcm) / 2 / RATE / 60:.1f}分")
    if a.dry_run:
        print(f"\nAPIを呼ぶ回数：{calls}")
    else:
        (out_dir / "voice_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
