import React from "react";
import { Composition } from "remotion";
import { HistoryEpisode } from "./HistoryEpisode";
import { buildTimeline } from "./timeline";
import type { Episode } from "./types";
import sampleEpisode from "../episodes/sample/episode.json";
import { PlaceholderClip } from "./PlaceholderClip";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="HistoryEpisode"
        component={HistoryEpisode}
        defaultProps={sampleEpisode as Episode}
        // Props = the episode JSON itself (pass another one with --props=path/to/episode.json).
        // Size / fps / length all come from it.
        calculateMetadata={({ props }) => {
          const episode = props;
          return {
            fps: episode.fps,
            width: episode.width,
            height: episode.height,
            durationInFrames: buildTimeline(episode).totalFrames,
          };
        }}
        fps={30}
        width={1280}
        height={720}
        durationInFrames={1}
      />
      {/* Only used to make a placeholder mp4 for testing video cuts. */}
      <Composition
        id="PlaceholderClip"
        component={PlaceholderClip}
        fps={30}
        width={1280}
        height={720}
        durationInFrames={330}
      />
    </>
  );
};
