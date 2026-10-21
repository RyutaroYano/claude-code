#!/usr/bin/env python3
"""Generate placeholder images + narration audio for the sample episode.

Images: 1920x1080 gradients with a big cut number (stand-ins for ChatGPT images).
Audio:  quiet sine-tone WAVs (stand-ins for Gemini TTS narration per block).

Usage: python3 scripts/make_placeholders.py
"""
import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "episodes" / "sample"
W, H = 1920, 1080

PALETTES = [
    ((52, 38, 28), (150, 110, 70)),   # 01 sepia: medieval Europe
    ((20, 34, 58), (90, 120, 160)),   # 02 blue: city ~1500
    ((60, 30, 24), (190, 120, 80)),   # 03 warm: bathhouse
    ((24, 44, 34), (120, 150, 110)),  # 04 green: Kyoto
    ((40, 40, 48), (130, 130, 150)),  # 05 grey: spare
]
LABELS = ["Europe / 不潔説", "Town ~1500", "Public bath", "Kyoto 風呂屋", "Spare"]


def font(size):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def jp_font(size):
    for p in [
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return font(size)


def make_image(i, top, bottom, label):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(0, W):
            # diagonal gradient
            t = (x / W * 0.4 + y / H * 0.6)
            px[x, y] = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
    d = ImageDraw.Draw(img)
    # grid lines make Ken Burns motion visible
    for gx in range(0, W, 160):
        d.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 40), width=1)
    for gy in range(0, H, 160):
        d.line([(0, gy), (W, gy)], fill=(255, 255, 255, 40), width=1)
    num = f"{i:02d}"
    f = font(420)
    bbox = d.textbbox((0, 0), num, font=f)
    d.text(((W - (bbox[2] - bbox[0])) / 2, H * 0.12), num, font=f, fill=(255, 255, 255))
    lf = jp_font(72)
    lb = d.textbbox((0, 0), label, font=lf)
    d.text(((W - (lb[2] - lb[0])) / 2, H * 0.62), label, font=lf, fill=(240, 240, 240))
    d.text((40, H - 70), "PLACEHOLDER 1920x1080", font=font(36), fill=(255, 255, 255))
    path = OUT / "images" / f"cut{i:02d}.png"
    img.save(path)
    return path


def make_tone(path, seconds, freq, sr=16000):
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for k in range(n):
            t = k / sr
            env = min(1.0, t / 0.2, (seconds - t) / 0.4)  # fade in/out
            # slow amplitude wobble ~ "speech-like" phrasing
            env *= 0.55 + 0.45 * math.sin(2 * math.pi * 1.7 * t) ** 2
            v = 0.12 * env * math.sin(2 * math.pi * freq * t)
            frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
        w.writeframes(bytes(frames))
    return path


def main():
    for sub in ("images", "audio", "video"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    for i, ((top, bottom), label) in enumerate(zip(PALETTES, LABELS), start=1):
        print("image", make_image(i, top, bottom, label))
    for i, freq in enumerate([220, 247, 262, 294], start=1):
        print("audio", make_tone(OUT / "audio" / f"narration{i:02d}.wav", 9.0, freq))


if __name__ == "__main__":
    main()
