import React from "react";
import { AbsoluteFill, OffthreadVideo } from "remotion";

/** AI-generated clip (e.g. Google Flow). Muted: narration is the only voice. */
export const VideoCut: React.FC<{ src: string }> = ({ src }) => {
  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        muted
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};
