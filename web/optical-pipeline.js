export const CAMERA_CONSTRAINTS = Object.freeze({
  facingMode: { ideal: "environment" },
  width: { ideal: 1280, max: 1920 },
  height: { ideal: 720, max: 1080 },
  frameRate: { ideal: 30, max: 30 },
});

export function startSafeVideoFrameLoop(video, onFrame) {
  let stopped = false;
  let animationFrame, videoFrame, watchdog;
  let usingVideoFrames = typeof video.requestVideoFrameCallback === "function";
  const tick = () => {
    if (stopped) return;
    if (video.readyState >= 2) onFrame("rAF");
    if (!stopped) animationFrame = requestAnimationFrame(tick);
  };
  const fallback = () => {
    usingVideoFrames = false;
    clearTimeout(watchdog);
    if (videoFrame != null) video.cancelVideoFrameCallback?.(videoFrame);
    animationFrame = requestAnimationFrame(tick);
  };
  const requestVideoFrame = () => {
    if (stopped) return;
    try {
      videoFrame = video.requestVideoFrameCallback((_now, metadata) => {
        if (stopped || !usingVideoFrames) return;
        clearTimeout(watchdog);
        onFrame("rVFC", metadata.presentedFrames);
        requestVideoFrame();
      });
      // Some camera streams expose the API without delivering callbacks.
      watchdog = setTimeout(fallback, 250);
    } catch (_) { fallback(); }
  };
  if (usingVideoFrames) requestVideoFrame();
  else fallback();
  return () => {
    stopped = true;
    clearTimeout(watchdog);
    if (videoFrame != null && usingVideoFrames) video.cancelVideoFrameCallback?.(videoFrame);
    if (animationFrame != null) cancelAnimationFrame(animationFrame);
  };
}
