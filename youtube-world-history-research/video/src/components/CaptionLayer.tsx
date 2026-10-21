import React from "react";
import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import type { Caption } from "../types";
import { CAPTION_FONT, ensureCaptionFont } from "../fonts";

ensureCaptionFont();

const CaptionText: React.FC<{ text: string }> = ({ text }) => {
  const { width } = useVideoConfig();
  const fontSize = Math.round(width * 0.03); // 58px @1920, 38px @1280
  const stroke = Math.max(2, Math.round(fontSize * 0.16));

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: Math.round(width * 0.035),
      }}
    >
      <div
        style={{
          maxWidth: "86%",
          fontFamily: `${CAPTION_FONT}, "Noto Sans JP", "Noto Sans CJK JP", "Hiragino Kaku Gothic ProN", "Yu Gothic", "IPAGothic", sans-serif`,
          fontWeight: 900,
          fontSize,
          lineHeight: 1.35,
          color: "white",
          textAlign: "center",
          whiteSpace: "pre-wrap",
          wordBreak: "keep-all",
          lineBreak: "strict",
          // Black outline drawn behind the fill.
          WebkitTextStroke: `${stroke}px black`,
          paintOrder: "stroke fill",
          textShadow: "0 0 6px rgba(0,0,0,0.6)",
          // Max 2 lines.
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          padding: `0 ${stroke}px`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

/** Shows each caption between startSec and endSec (relative to the parent Sequence). */
export const CaptionLayer: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {captions.map((c, i) => {
        const from = Math.round(c.startSec * fps);
        const dur = Math.max(1, Math.round((c.endSec - c.startSec) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`caption: ${c.text.slice(0, 12)}`}>
            <CaptionText text={c.text} />
          </Sequence>
        );
      })}
    </>
  );
};
