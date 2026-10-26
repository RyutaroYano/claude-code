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
  - ナレーションは、指示文で1分300字の速さを頼んだうえで、話している部分を測り、1分300字からずれていれば
    声の高さを変えずに速さだけ合わせる（AIは字数を数えて読めないため。台本の字で数え、句読点は除く）。台詞は合わせない。
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
TARGET_CPM = 300     # ナレーションの速さ：1分あたりの字数（句読点を除く、台本の字で数える）
CPM_TOLERANCE = 0.03 # これより小さいずれは直さない


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


def bursts(pcm: bytes) -> list[float]:
    """無音の直後に、いきなり大きな音が来る所（ヘッダーやデータの混入による雑音）を探す。"""
    import array
    x = array.array("h", pcm)
    win, out, prev = RATE // 100, [], 0.0
    for i in range(0, len(x) - win, win):
        rms = (sum(v * v for v in x[i:i + win]) / win) ** 0.5 / 32768
        if rms > 0.3 and prev < 0.01:
            out.append(i / RATE)
        prev = rms
    return out


def trim(pcm: bytes, thresh: int = 300) -> tuple[bytes, bytes, bytes]:
    """前後の無音と、話している部分に分ける。"""
    import array
    x = array.array("h", pcm)
    i, j = 0, len(x)
    while i < j and abs(x[i]) < thresh:
        i += 1
    while j > i and abs(x[j - 1]) < thresh:
        j -= 1
    return pcm[:i * 2], pcm[i * 2:j * 2], pcm[j * 2:]


def to_pace(pcm: bytes, chars: int) -> tuple[bytes, float]:
    """話している部分が 1分あたり TARGET_CPM 字になるよう、声の高さを変えずに速さだけ変える（ffmpeg atempo）。"""
    import subprocess
    head, body, tail = trim(pcm)
    speech = len(body) / 2 / RATE
    factor = speech / (chars / TARGET_CPM * 60)
    if abs(factor - 1) < CPM_TOLERANCE or not body:
        return pcm, 1.0
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-",
                          "-filter:a", f"atempo={factor:.4f}", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-"],
                         input=body, capture_output=True, check=True).stdout
    return head[:int(RATE * 0.1) * 2] + out + tail[:int(RATE * 0.1) * 2], factor


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(RATE * sec)


def make_part(parts_dir: Path, name: str, prompt: str, voice: str, model: str, key: str | None) -> Path:
    h = hashlib.sha1(f"{model}\n{voice}\n{prompt}".encode()).hexdigest()[:10]
    path = parts_dir / f"{name}_{voice}_{h}.wav"
    if not path.exists():
        print(f"  作成中：{path.name}", flush=True)
        audio = tts(prompt, voice, model, key)
        if audio[:4] == b"RIFF":
            # 2026-10 から、WAVファイル（頭にヘッダー、後ろにAI生成の来歴情報）で返ってくる。
            # そのまま保存し、音は read_pcm で data の部分だけを読む（ヘッダーや来歴情報を音として鳴らさない）
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
        else:
            write_wav(path, audio)  # 以前の形：生のPCM
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
              "| ブロック | 区切り | カット | 声 | 字数 | 秒 | 1分の字数 | 速さの調整 |", "|---|---|---|---|---|---|---|---|"]
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
            seg, factor = read_pcm(p), 1.0
            if s["kind"] == "narration":
                seg, factor = to_pace(seg, count(s["text"]))
            if pcm and not pcm.endswith(silence(ledger["pause_sec"])):
                pcm += silence(ledger["gap_sec"])
            pcm += seg
            sec = len(seg) / 2 / RATE
            report.append(f"| {bi:02d} | {n} | {label} | {voice} | {count(s['text'])} | {sec:.1f} | {count(s['text']) / sec * 60:.0f} | ×{factor:.2f} |")
        if not a.dry_run:
            for t in bursts(pcm):
                print(f"  注意：block{bi:02d} の {t:.2f}秒に、無音から急に大きな音（雑音の疑い）")
            write_wav(out_dir / f"block{bi:02d}.wav", pcm)
            print(f"block{bi:02d}.wav  {len(pcm) / 2 / RATE / 60:.1f}分")
    if a.dry_run:
        print(f"\nAPIを呼ぶ回数：{calls}")
    else:
        (out_dir / "voice_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
