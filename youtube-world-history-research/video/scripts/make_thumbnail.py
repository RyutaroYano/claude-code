"""サムネの背景画像に、チャンネルの決まりどおりの文字を載せる（設計書 第6章）。

Usage:
  python3 scripts/make_thumbnail.py <背景画像> <左の地域名> <右の地域名> <問いの言葉> <出力.png>
  例: python3 scripts/make_thumbnail.py bg.webp ロンドン 江戸 同じ大火なのに？ out/thumb.png
  左右に分ける形: 問いの言葉を「左|真ん中|右」と書く
  例: python3 scripts/make_thumbnail.py bg.webp ロンドン 日本 "石造り？|なんで|木造り？" out/thumb.png
      → 真ん中の上に「なんで」、その下の左に「石造り？」、右に「木造り？」
  文字を白い枠に入れる形（白地・黒い縁・赤い文字）: 最後に --box をつける

- 1280x720 に切り抜く（足りない向きは中央で切る）。
- 上18%を黒い帯で塗り、左右の中央に地域名（黄色・極太明朝）。
- 真ん中に赤い縦線（上の帯から画像の下まで通す）。
- 下の中央に問いの言葉（黄色・黒い縁取り・極太明朝。横幅の80%に収める）。
- フォントは public/fonts/ の Noto Serif JP Black（scripts/fetch_font.sh）。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BAND = 0.18
YELLOW = (255, 214, 0)
RED = (225, 0, 20)
LINE_W = 10
ROOT = os.path.join(os.path.dirname(__file__), "..")
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


BOX_PAD_X, BOX_PAD_Y, BOX_BORDER = 22, 12, 10


def draw_box(draw, text, font, cx, cy):
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    w, h = x1 - x0 + BOX_PAD_X * 2, y1 - y0 + BOX_PAD_Y * 2
    draw.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), radius=14,
                           fill=(255, 255, 255), outline=(0, 0, 0), width=BOX_BORDER)
    draw_center(draw, text, font, cx, cy, RED)


def main(bg, left, right, question, out, box=False):
    img = cover(Image.open(bg).convert("RGB"))
    draw = ImageDraw.Draw(img)
    band_h = round(H * BAND)
    draw.rectangle((0, 0, W, band_h), fill=(0, 0, 0))
    draw.rectangle((W / 2 - LINE_W / 2, 0, W / 2 + LINE_W / 2, H), fill=RED)

    label_font = fit_font(SERIF, max(left, right, key=len), W / 2 * 0.8, band_h * 0.7)
    draw_center(draw, left, label_font, W / 4, band_h / 2, YELLOW)
    draw_center(draw, right, label_font, W * 3 / 4, band_h / 2, YELLOW)

    stroke = 10
    parts = question.split("|")
    if box and len(parts) == 3:
        q_left, q_mid, q_right = parts
        side_font = fit_font(SERIF, max(q_left, q_right, key=len), W / 2 * 0.8, H * 0.17)
        draw_box(draw, q_left, side_font, W / 4, H * 0.86)
        draw_box(draw, q_right, side_font, W * 3 / 4, H * 0.86)
        mid_font = fit_font(SERIF, q_mid, W * 0.32, H * 0.12)
        draw_box(draw, q_mid, mid_font, W / 2, H * 0.66)
    elif box:
        q_font = fit_font(SERIF, question, W * 0.72, H * 0.16)
        draw_box(draw, question, q_font, W / 2, H * 0.85)
    elif len(parts) == 3:
        q_left, q_mid, q_right = parts
        side_font = fit_font(SERIF, max(q_left, q_right, key=len), W / 2 * 0.86, H * 0.17, stroke)
        draw_center(draw, q_left, side_font, W / 4, H * 0.87, YELLOW, stroke, (0, 0, 0))
        draw_center(draw, q_right, side_font, W * 3 / 4, H * 0.87, YELLOW, stroke, (0, 0, 0))
        mid_font = fit_font(SERIF, q_mid, W * 0.4, H * 0.15, stroke)
        draw_center(draw, q_mid, mid_font, W / 2, H * 0.68, YELLOW, stroke, (0, 0, 0))
    else:
        q_font = fit_font(SERIF, question, W * 0.8, H * 0.2, stroke)
        draw_center(draw, question, q_font, W / 2, H * 0.86, YELLOW, stroke, (0, 0, 0))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--box"]
    if len(args) != 5:
        sys.exit(__doc__)
    main(*args, box="--box" in sys.argv)
