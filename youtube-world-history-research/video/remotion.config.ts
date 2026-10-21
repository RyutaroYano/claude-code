// Remotion CLI config. See https://www.remotion.dev/docs/config
import { Config } from "@remotion/cli/config";
import fs from "node:fs";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setCodec("h264");

// Remotion normally downloads its own Chrome Headless Shell from remotion.media.
// In sandboxes where that download is blocked, fall back to a preinstalled one.
// Override with REMOTION_BROWSER_EXECUTABLE=/path/to/headless_shell.
const candidates = [
  process.env.REMOTION_BROWSER_EXECUTABLE,
  "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
].filter((p): p is string => Boolean(p));
const browser = candidates.find((p) => fs.existsSync(p));
if (browser) {
  Config.setBrowserExecutable(browser);
}
