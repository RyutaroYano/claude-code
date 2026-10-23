"""サムネの背景画像に、チャンネルの決まりどおりの文字を載せる（設計書 第6章）。

Usage:
  python3 scripts/make_thumbnail.py <背景画像> <左の地域名> <右の地域名> <問いの言葉> <出力.png>
  例: python3 scripts/make_thumbnail.py bg.webp ロンドン 江戸 同じ大火なのに？ out/thumb.png

- 1280x720 に切り抜く（足りない向きは中央で切る）。
- 上18%を黒い帯で塗り、左右の中央に地域名（黄色・極太ゴシック）。
- 下の中央に問いの言葉（黄色・黒い縁取り・極太明朝。横幅の80%に収める）。
- フォントは public/fonts/ の Noto Sans JP Black と Noto Serif JP Black（scripts/fetch_font.sh）。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BAND = 0.18
YELLOW = (255, 214, 0)
ROOT = os.path.join(os.path.dirname(__file__), "..")
SANS = os.path.join(ROOT, "public/fonts/NotoSansJP-Black.ttf")
SERIF = os.path.join(ROOT, "public/fonts/NotoSerifJP-Black.ttf")


def cover(img):
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def fit_font(path, text, max_w, max_h, stroke=0):
    size = int(max_h)
    while size > 10:
        font = ImageFont.truetype(path, size)
        x0, y0, x1, y1 = font.getbbox(text, stroke_width=stroke)
        if x1 - x0 <= max_w and y1 - y0 <= max_h:
            return font
        size -= 2
    return ImageFont.truetype(path, size)


def draw_center(draw, text, font, cx, cy, fill, stroke=0, stroke_fill=None):
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    draw.text((cx - (x0 + x1) / 2, cy - (y0 + y1) / 2), text, font=font, fill=fill,
              stroke_width=stroke, stroke_fill=stroke_fill)


def main(bg, left, right, question, out):
    img = cover(Image.open(bg).convert("RGB"))
    draw = ImageDraw.Draw(img)
    band_h = round(H * BAND)
    draw.rectangle((0, 0, W, band_h), fill=(0, 0, 0))

    label_font = fit_font(SANS, max(left, right, key=len), W / 2 * 0.8, band_h * 0.7)
    draw_center(draw, left, label_font, W / 4, band_h / 2, YELLOW)
    draw_center(draw, right, label_font, W * 3 / 4, band_h / 2, YELLOW)

    stroke = 10
    q_font = fit_font(SERIF, question, W * 0.8, H * 0.2, stroke)
    draw_center(draw, question, q_font, W / 2, H * 0.86, YELLOW, stroke, (0, 0, 0))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    main(*sys.argv[1:])
