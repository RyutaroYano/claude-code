import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

/** Dummy "AI video clip" used to test video cuts until real Flow clips exist. */
export const PlaceholderClip: React.FC = () => {
  const frame = useCurrentFrame();
  const hue = interpolate(frame, [0, 330], [200, 260]);
  const x = interpolate(frame, [0, 330], [-30, 30]);
  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, hsl(${hue},45%,22%), hsl(${hue + 40},50%,40%))`,
        justifyContent: "center",
        alignItems: "center",
        color: "rgba(255,255,255,0.85)",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ fontSize: 160, fontWeight: 800, transform: `translateX(${x}px)` }}>CUT 04</div>
      <div style={{ fontSize: 40, marginTop: 20 }}>VIDEO PLACEHOLDER (Flow)</div>
    </AbsoluteFill>
  );
};
