import { continueRender, delayRender, staticFile } from "remotion";

export const CAPTION_FONT = "NotoSansJPBlack";

// Self-hosted font (download with scripts/fetch_font.sh) so rendering does not
// depend on fonts.gstatic.com. If the file is missing we log a warning and the
// CSS fallback (locally installed Japanese gothic fonts) is used instead.
let started = false;
export const ensureCaptionFont = () => {
  if (started || typeof window === "undefined") return;
  started = true;
  const handle = delayRender("Loading caption font");
  const face = new FontFace(CAPTION_FONT, `url(${staticFile("fonts/NotoSansJP-Black.ttf")})`, {
    weight: "900",
  });
  face
    .load()
    .then((loaded) => {
      document.fonts.add(loaded);
    })
    .catch((err) => {
      console.warn("Caption font not found, using fallback. Run scripts/fetch_font.sh", err);
    })
    .finally(() => continueRender(handle));
};
