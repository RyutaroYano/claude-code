import type { Episode } from "./types";

export type TimedCut = {
  index: number;
  startFrame: number;
  durationInFrames: number;
};

/** Converts cut durations to frame ranges. Cuts are laid out back-to-back. */
export const buildTimeline = (episode: Episode) => {
  const { fps } = episode;
  let cursor = 0;
  const cuts: TimedCut[] = episode.cuts.map((cut, index) => {
    const durationInFrames = Math.max(1, Math.round(cut.durationSec * fps));
    const timed = { index, startFrame: cursor, durationInFrames };
    cursor += durationInFrames;
    return timed;
  });
  return { cuts, totalFrames: Math.max(1, cursor) };
};

export const secToFrame = (sec: number, fps: number) => Math.round(sec * fps);
