# 動画組み立て（Remotion）

顔出しなし・世界史チャンネル用の動画を、エピソードJSONから自動で組み立てる仕組み。
1本 約20分 = 約10秒の「カット」を並べたもの。各カットは静止画＋ゆっくりした動き（Ken Burns）か、AI動画クリップ。
そこにナレーション音声とテロップを重ねる。

今はダミー素材（グラデーション画像・トーン音・ダミー動画）で動く状態。

## フォルダ構成

```
video/
  package.json            依存（バージョン固定）と npm スクリプト
  remotion.config.ts      レンダリング設定（ブラウザの場所など）
  tsconfig.json
  src/
    index.ts              エントリ
    Root.tsx              コンポジション登録（HistoryEpisode / PlaceholderClip）
    HistoryEpisode.tsx    本体：カット並べ・クロスフェード・テロップ・音声
    timeline.ts           秒 → フレーム換算、全体の長さ計算
    types.ts              エピソードJSONの型
    fonts.ts              テロップ用フォント（Noto Sans JP Black）読み込み
    components/
      KenBurnsImage.tsx   静止画のズーム／パン
      VideoCut.tsx        動画カット（OffthreadVideo、音はミュート）
      CaptionLayer.tsx    テロップ（白文字＋黒フチ、下中央、最大2行）
    PlaceholderClip.tsx   ダミー動画を作るためだけのコンポジション
  episodes/
    sample/episode.json   サンプル回（4カット・40秒）
  public/                 素材置き場（JSONのパスはここからの相対パス）
    episodes/sample/images/cut01.png …  ダミー画像（1920x1080）
    episodes/sample/audio/narration01.wav …  ダミー音声
    episodes/sample/video/cut04.mp4     ダミー動画
    fonts/NotoSansJP-Black.ttf          ※gitに入れない。fetch_font.sh で取得
  scripts/
    make_placeholders.py    ダミー画像・音声の生成（PIL）
    fetch_font.sh           Noto Sans JP Black を Google Fonts から取得
    captions_from_whisper.mjs  Whisperの単語タイムスタンプ → テロップ（スタブ）
  out/                    レンダリング結果（gitに入れない）
```

## 使い方

```bash
cd youtube-world-history-research/video
npm ci                     # 初回のみ
npm run fetch-font         # 初回のみ（テロップ用フォント 約5.7MB）
npm run render:sample      # → out/sample.mp4（1280x720, 40秒）
npm run studio             # ブラウザでプレビュー・微調整
```

- 別の回をレンダリング：
  `npx remotion render HistoryEpisode out/ep001.mp4 --props=./episodes/ep001/episode.json`
- 解像度はJSONの width/height で決まる。サンプルは確認用に 1280x720。本番は 1920x1080 にする。
  （JSONを変えずに一時的に縮小したいときは `--scale=0.5` など）
- ダミー素材を作り直す：`npm run placeholders`
- ブラウザ：Remotion は普段は自分で Chrome Headless Shell をダウンロードする。
  この開発環境ではダウンロード先（remotion.media）がブロックされているので、
  `remotion.config.ts` で `/opt/pw-browsers/.../headless_shell` があればそれを使うようにしてある。
  別の場所を使うなら `REMOTION_BROWSER_EXECUTABLE=/path/to/headless_shell` を指定。普通のPCなら何もしなくてよい。

## エピソードJSONの形

```jsonc
{
  "title": "サンプル: ヨーロッパと日本の風呂",
  "fps": 30,
  "width": 1920,
  "height": 1080,
  "crossfadeSec": 0.5,          // カット間のクロスフェード（0で切り替え）
  "cuts": [
    {
      "id": "c01",
      "durationSec": 10,
      "image": "episodes/ep001/images/cut01.png",   // public/ からの相対パス
      "video": "episodes/ep001/video/cut01.mp4",    // 任意。あれば image より優先
      "motion": "zoomIn",       // zoomIn | zoomOut | panLeft | panRight | none
      "narration": "昔のヨーロッパの人は、…",       // 台本の文（テロップ生成の元）
      "captions": [
        { "text": "昔のヨーロッパの人は、\nあまり風呂に入らなかった。", "startSec": 0.3, "endSec": 5.0 }
      ]                         // 時間はカットの頭からの秒。\n で改行（最大2行）
    }
  ],
  "audio": [                    // ナレーション。時間はエピソード頭からの秒
    { "src": "episodes/ep001/audio/narration01.wav", "startSec": 0.3, "volume": 1 }
  ],
  "bgm": { "src": "episodes/ep001/audio/bgm.mp3", "startSec": 0, "volume": 0.08 }  // 任意。ループ再生
}
```

- 全体の長さ = 各カットの durationSec の合計（自動計算）。
- クロスフェードは次のカットが少し早く始まって重なるだけなので、全体の長さは変わらない。

## 本物の素材への差し替え

1. フォルダを作る：`public/episodes/ep001/{images,video,audio}` と `episodes/ep001/episode.json`
2. 画像（ChatGPT）
   - 16:9 で生成（1920x1080 推奨、1280x720 でも可）。`cut01.png` のようにカット番号で保存。
   - 違う比率でも `object-fit: cover` で中央トリミングされる。
   - ズームで少し拡大する（最大1.12倍）ので、端の重要な物は避ける。
3. 動画クリップ（Google Flow）
   - mp4 を `video/` に置き、そのカットに `"video": "..."` を書く。
   - 音声はミュートして使う（ナレーションだけ聞かせる）。
   - クリップがカットより短いと最後のフレームで止まる。durationSec をクリップ長以下にするか、長めに生成。
4. ナレーション（Gemini TTS）
   - 1ブロック（1カット or 数カット）ごとに WAV/MP3 を作り `audio/` に置く。
   - `audio` 配列に `{src, startSec}` を並べる。startSec はそのブロックの最初のカットの開始秒＋0.3秒くらい。
   - 音声の長さに合わせてカットの durationSec を決める（音声長＋0.5〜1秒の余白）。
     音声長は `npx remotion ffprobe -v error -show_entries format=duration -of csv=p=0 file.wav` で確認できる。
5. `npx tsc --noEmit` で型チェック → `npm run studio` で目視 → render。

## テロップのタイミング（予定）

方針：**文字は台本から、タイミングだけWhisperから取る。**
（Whisperは漢字の変換を間違えやすいので、Whisperの文字はそのまま出さない）

手順：
1. Gemini TTS でブロックごとの音声を作る（上の4）。
2. Whisper で単語（トークン）ごとのタイムスタンプを取る。どちらか：
   - openai-whisper（Python）
     ```bash
     pip install openai-whisper
     whisper narration01.wav --language ja --model medium --word_timestamps True --output_format json --output_dir whisper/
     ```
   - whisper.cpp（Remotion公式ラッパー、Node内で完結）
     ```bash
     npm i -E @remotion/install-whisper-cpp@4.0.532
     ```
     ```ts
     import { installWhisperCpp, downloadWhisperModel, transcribe, toCaptions } from "@remotion/install-whisper-cpp";
     await installWhisperCpp({ to: "./whisper.cpp", version: "1.5.5" });
     await downloadWhisperModel({ model: "medium", folder: "./whisper.cpp" });
     // 入力は 16kHz WAV（ffmpeg -i in.wav -ar 16000 out16k.wav）
     const out = await transcribe({ inputPath: "out16k.wav", whisperPath: "./whisper.cpp",
       whisperCppVersion: "1.5.5", model: "medium", tokenLevelTimestamps: true, language: "ja" });
     fs.writeFileSync("words.json", JSON.stringify(toCaptions({ whisperCppOutput: out }).captions));
     ```
3. 変換スクリプトでそのカットの captions を書き換える：
   ```bash
   node scripts/captions_from_whisper.mjs episodes/ep001/episode.json c01 whisper/narration01.json 0.3
   #                                      エピソードJSON           カットID 単語JSON           音声がカット内で始まる秒
   ```
   - narration を「。」で文に分け、長い文は「、」で分けて1枚最大36文字（18文字×2行）にする。
   - 各チャンクの文字数の比率で Whisper のタイムスタンプに対応づける（漢字が違っても文字数はほぼ同じ）。
   - 2行に分ける位置は「、」や助詞の後を優先。
4. Studio で見て、ずれている所だけ JSON を手で直す。

Whisper の入力として受け付ける形（どれでもよい）：
```jsonc
// openai-whisper
{ "segments": [ { "words": [ { "word": "昔", "start": 0.12, "end": 0.40 } ] } ] }
// @remotion/install-whisper-cpp の toCaptions().captions
[ { "text": "昔", "startMs": 120, "endMs": 400 } ]
// 単純なリスト
[ { "text": "昔", "start": 0.12, "end": 0.40 } ]
```
出力（captions）：`[{ "text": "…\n…", "startSec": 0.4, "endSec": 5.4 }]`（カット頭からの秒）

※ 1ブロックの音声が複数カットにまたがる場合は、今のスクリプトは1カット単位なので、
  カットごとに音声を分けるか、スクリプトを拡張する（TODO）。

## ライセンス（Remotion）

- Remotion は「ソース公開・条件付き無料」のライセンス（いわゆるOSSではない）。
- **個人**、**従業員3人以下の営利企業**、非営利団体は無料。商用（YouTube収益化など）でもOK。
- それより大きい営利企業は Company License（有料）が必要。
- 禁止：Remotion 自体を改造・コピーして、自分の動画制作ツールとして売る／貸すこと。
- 出典：`node_modules/remotion/LICENSE.md`（v4.0.532）、https://www.remotion.dev/license 。
  v5.0 で少し条件が変わる予告あり。アップデート時に再確認する。
- フォント Noto Sans JP は SIL Open Font License（動画への使用は自由）。
