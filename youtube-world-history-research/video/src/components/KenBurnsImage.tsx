import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Motion } from "../types";

// How far the camera moves over one cut. Kept small: calm documentary feel.
const ZOOM_AMOUNT = 0.12; // 1.00 -> 1.12
const PAN_SCALE = 1.12; // image is scaled up so panning never shows edges
const PAN_PERCENT = 4; // translateX range in % of width (must be < (PAN_SCALE-1)/2*100)

const ease = Easing.bezier(0.33, 0, 0.67, 1);

export const KenBurnsImage: React.FC<{ src: string; motion: Motion }> = ({ src, motion }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig(); // = this Sequence's length
  const t = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

  let scale = 1;
  let x = 0;
  switch (motion) {
    case "zoomIn":
      scale = 1 + ZOOM_AMOUNT * t;
      break;
    case "zoomOut":
      scale = 1 + ZOOM_AMOUNT * (1 - t);
      break;
    case "panLeft": // camera moves left -> image slides right
      scale = PAN_SCALE;
      x = -PAN_PERCENT + 2 * PAN_PERCENT * t;
      break;
    case "panRight": // camera moves right -> image slides left
      scale = PAN_SCALE;
      x = PAN_PERCENT - 2 * PAN_PERCENT * t;
      break;
    case "none":
    default:
      break;
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translateX(${x}%) scale(${scale})`,
          transformOrigin: "50% 50%",
          willChange: "transform",
        }}
      />
    </AbsoluteFill>
  );
};
