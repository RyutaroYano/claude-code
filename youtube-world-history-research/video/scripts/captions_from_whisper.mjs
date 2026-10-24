#!/usr/bin/env node
/**
 * STUB: build cut captions from Whisper word timestamps.
 *
 * Idea: the caption TEXT comes from our own script (narration, already correct
 * kanji/kana), Whisper is only used for TIMING. Japanese Whisper output often
 * mis-converts kanji, so we never show Whisper text on screen.
 *
 * Input (words.json) — any of:
 *   A) openai-whisper:  whisper narration01.wav --language ja --word_timestamps True --output_format json
 *      -> { "segments": [ { "words": [ { "word": "昔", "start": 0.12, "end": 0.40 }, ... ] } ] }
 *   B) @remotion/whisper-cpp: toCaptions(transcribe(...)).captions
 *      -> [ { "text": "昔", "startMs": 120, "endMs": 400 }, ... ]
 *   C) plain list: [ { "text": "昔", "start": 0.12, "end": 0.40 }, ... ]
 *
 * Usage:
 *   node scripts/captions_from_whisper.mjs <episode.json> <cutId> <words.json> [audioStartInCutSec]
 * It rewrites cuts[cutId].captions in place.
 *
 * Output shape per caption: { "text": "…\n…", "startSec": 0.3, "endSec": 4.8 }
 * (seconds relative to the cut start).
 */
import fs from "node:fs";

const MAX_CHARS_PER_LINE = 18; // ~2 lines on screen
const MAX_CHARS = MAX_CHARS_PER_LINE * 2;

const [, , episodePath, cutId, wordsPath, offsetArg] = process.argv;
if (!episodePath || !cutId || !wordsPath) {
  console.error("usage: captions_from_whisper.mjs <episode.json> <cutId> <words.json> [audioStartInCutSec]");
  process.exit(1);
}
const offset = Number(offsetArg ?? 0);

const normalize = (s) => s.replace(/[\s、。，．,.!?！？「」『』（）()・…\n]/g, "");

const loadWords = (raw) => {
  const list = Array.isArray(raw) ? raw : (raw.segments ?? []).flatMap((s) => s.words ?? []);
  return list
    .map((w) => ({
      text: w.word ?? w.text ?? "",
      start: w.start ?? (w.startMs ?? 0) / 1000,
      end: w.end ?? (w.endMs ?? 0) / 1000,
    }))
    .filter((w) => normalize(w.text).length > 0);
};

/** Split narration into caption chunks at 。/、 keeping each chunk <= MAX_CHARS. */
const chunkNarration = (text) => {
  const sentences = text.match(/[^。！？]+[。！？]?/g) ?? [text];
  const chunks = [];
  for (const s of sentences) {
    if (s.length <= MAX_CHARS) { chunks.push(s); continue; }
    let buf = "";
    for (const part of s.match(/[^、]+、?/g) ?? [s]) {
      if ((buf + part).length > MAX_CHARS && buf) { chunks.push(buf); buf = ""; }
      buf += part;
    }
    if (buf) chunks.push(buf);
  }
  return chunks.map((c) => c.trim()).filter(Boolean);
};

/** Insert one line break near the middle: after 、 or a particle, never mid-word if avoidable. */
const twoLines = (c) => {
  if (c.length <= MAX_CHARS_PER_LINE) return c;
  const mid = Math.floor(c.length / 2);
  let best = -1;
  let bestScore = Infinity;
  for (let i = 1; i < c.length - 1; i++) {
    const ch = c[i - 1];
    const weight = ch === "、" ? 0 : "をはがにでもへ".includes(ch) ? 2 : -1;
    if (weight < 0) continue;
    const score = Math.abs(i - mid) + weight;
    if (score < bestScore && Math.abs(i - mid) <= 7) { best = i; bestScore = score; }
  }
  const at = best > 0 ? best : mid;
  return c.slice(0, at) + "\n" + c.slice(at);
};

const episode = JSON.parse(fs.readFileSync(episodePath, "utf8"));
const cut = episode.cuts.find((c) => c.id === cutId);
if (!cut) throw new Error(`cut ${cutId} not found`);
const words = loadWords(JSON.parse(fs.readFileSync(wordsPath, "utf8")));
if (!words.length) throw new Error("no words in whisper output");

// Character-proportional alignment: walk the narration's characters and the
// Whisper tokens' characters in parallel (counts are close even when Whisper
// picks different kanji). Good enough for subtitle timing; refine by hand in
// Remotion Studio if a caption feels early/late.
const whisperChars = [];
for (const w of words) {
  const n = normalize(w.text).length;
  for (let i = 0; i < n; i++) {
    whisperChars.push(w.start + ((w.end - w.start) * i) / n);
  }
}
whisperChars.push(words[words.length - 1].end);

const chunks = chunkNarration(cut.narration ?? "");
const total = chunks.reduce((a, c) => a + normalize(c).length, 0);
let consumed = 0;
cut.captions = chunks.map((c) => {
  const len = normalize(c).length;
  const i0 = Math.round((consumed / total) * (whisperChars.length - 1));
  consumed += len;
  const i1 = Math.round((consumed / total) * (whisperChars.length - 1));
  return {
    text: twoLines(c),
    startSec: +(offset + whisperChars[i0]).toFixed(2),
    endSec: +(offset + whisperChars[i1] + 0.2).toFixed(2),
  };
});
// No gaps/overlaps between consecutive captions.
for (let i = 0; i < cut.captions.length - 1; i++) {
  cut.captions[i].endSec = cut.captions[i + 1].startSec;
}

fs.writeFileSync(episodePath, JSON.stringify(episode, null, 2) + "\n");
console.log(JSON.stringify(cut.captions, null, 2));
