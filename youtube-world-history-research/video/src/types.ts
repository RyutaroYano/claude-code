export type Motion = "zoomIn" | "zoomOut" | "panLeft" | "panRight" | "none";

export type Caption = {
  text: string;
  /** Seconds, relative to the start of the cut. */
  startSec: number;
  endSec: number;
};

export type Cut = {
  id: string;
  durationSec: number;
  /** Path relative to public/ (e.g. "episodes/sample/images/cut01.png"). */
  image?: string;
  /** Path relative to public/. If set, takes precedence over image. */
  video?: string;
  motion?: Motion;
  narration?: string;
  captions?: Caption[];
};

export type AudioTrack = {
  /** Path relative to public/. */
  src: string;
  /** Seconds, absolute from the start of the episode. */
  startSec: number;
  volume?: number;
};

export type Episode = {
  title?: string;
  fps: number;
  width: number;
  height: number;
  /** Crossfade between cuts in seconds (0 = hard cut). Default 0.5. */
  crossfadeSec?: number;
  cuts: Cut[];
  audio?: AudioTrack[];
  /** Optional BGM, looped under the narration. */
  bgm?: AudioTrack;
};
