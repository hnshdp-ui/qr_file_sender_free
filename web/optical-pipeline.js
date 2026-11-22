export const CAMERA_CONSTRAINTS = Object.freeze({
  facingMode: { ideal: "environment" },
  width: { ideal: 1280, max: 1920 },
  height: { ideal: 720, max: 1080 },
  frameRate: { ideal: 24, max: 30 },
});

// Safari can scan from animation frames without video-frame callbacks.
export function startSafeVideoFrameLoop(video, onFrame) {
  let stopped = false;
  let handle = null;
  const tick = (timestamp) => {
    if (stopped) return;
    if (video.readyState >= 2) onFrame({ timestamp, mediaTime: Number(video.currentTime), source: "RAF_SAFE" });
    handle = requestAnimationFrame(tick);
  };
  handle = requestAnimationFrame(tick);
  return () => { stopped = true; if (handle != null) cancelAnimationFrame(handle); };
}
