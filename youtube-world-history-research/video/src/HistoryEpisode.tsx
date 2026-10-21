import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { KenBurnsImage } from "./components/KenBurnsImage";
import { VideoCut } from "./components/VideoCut";
import { CaptionLayer } from "./components/CaptionLayer";
import { buildTimeline, secToFrame } from "./timeline";
import type { Cut, Episode } from "./types";

/** Fades a cut in over `fadeFrames` (used for crossfades). */
const FadeIn: React.FC<{ fadeFrames: number; children: React.ReactNode }> = ({
  fadeFrames,
  children,
}) => {
  const frame = useCurrentFrame();
  const opacity =
    fadeFrames > 0
      ? interpolate(frame, [0, fadeFrames], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

const CutVisual: React.FC<{ cut: Cut }> = ({ cut }) => {
  if (cut.video) {
    return <VideoCut src={staticFile(cut.video)} />;
  }
  if (cut.image) {
    return <KenBurnsImage src={staticFile(cut.image)} motion={cut.motion ?? "zoomIn"} />;
  }
  return <AbsoluteFill style={{ backgroundColor: "black" }} />;
};

export const HistoryEpisode: React.FC<Episode> = (episode) => {
  const { fps } = useVideoConfig();
  const { cuts: timed } = buildTimeline(episode);
  const fadeFrames = secToFrame(episode.crossfadeSec ?? 0.5, fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {/* Visual layer. Each cut (except the first) starts `fadeFrames` early and
          fades in over the previous one, so the total length does not change. */}
      {timed.map(({ index, startFrame, durationInFrames }) => {
        const cut = episode.cuts[index];
        const lead = index === 0 ? 0 : Math.min(fadeFrames, startFrame);
        return (
          <Sequence
            key={cut.id}
            from={startFrame - lead}
            durationInFrames={durationInFrames + lead}
            name={`cut ${cut.id}`}
          >
            <FadeIn fadeFrames={lead}>
              <CutVisual cut={cut} />
            </FadeIn>
          </Sequence>
        );
      })}

      {/* Caption layer (times are relative to each cut). */}
      {timed.map(({ index, startFrame, durationInFrames }) => {
        const cut = episode.cuts[index];
        if (!cut.captions?.length) return null;
        return (
          <Sequence
            key={`cap-${cut.id}`}
            from={startFrame}
            durationInFrames={durationInFrames}
            name={`captions ${cut.id}`}
          >
            <CaptionLayer captions={cut.captions} />
          </Sequence>
        );
      })}

      {/* Narration tracks (absolute start times). */}
      {(episode.audio ?? []).map((track, i) => (
        <Sequence
          key={`audio-${i}`}
          from={secToFrame(track.startSec, fps)}
          name={`audio ${track.src}`}
          layout="none"
        >
          <Audio src={staticFile(track.src)} volume={track.volume ?? 1} />
        </Sequence>
      ))}

      {episode.bgm ? (
        <Sequence from={secToFrame(episode.bgm.startSec, fps)} layout="none" name="bgm">
          <Audio src={staticFile(episode.bgm.src)} volume={episode.bgm.volume ?? 0.08} loop />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};
