// Camera helpers have no browser globals so geometry and frame filtering can
// be tested independently of the phone's permissions and physical camera.
export function cameraFrameToken(video) {
  let count;
  try { count = video.getVideoPlaybackQuality?.()?.totalVideoFrames; } catch (_) { /* Use media time below. */ }
  if (Number.isFinite(count) && count > 0) {
    return `frame:${count}` + (Number.isFinite(video.currentTime) ? `|time:${video.currentTime}` : "");
  }
  return Number.isFinite(video.currentTime) ? `time:${video.currentTime}` : null;
}

export function shouldSkipCameraFrame(token, previous, elapsed) {
  // MediaStream counters/clocks are hints, not permission to stop scanning.
  // Probe the pixels again within 80 ms even when both hints are stalled.
  return token !== null && token === previous && elapsed < 80;
}

export function trackedQrRegion(location, captured) {
  if (!location || !captured?.imageWidth || !captured?.imageHeight) return null;
  const points = [location.topLeftCorner, location.topRightCorner, location.bottomLeftCorner, location.bottomRightCorner];
  if (points.some((point) => !Number.isFinite(point?.x) || !Number.isFinite(point?.y))) return null;
  const xs = points.map((p) => captured.x + p.x * captured.width / captured.imageWidth);
  const ys = points.map((p) => captured.y + p.y * captured.height / captured.imageHeight);
  const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
  if (right - left < 20 || bottom - top < 20) return null;
  // Include quiet zone, perspective changes and modest hand movement.
  const padX = Math.max(16, (right - left) * 0.2), padY = Math.max(16, (bottom - top) * 0.2);
  const x = Math.max(0, Math.floor(left - padX)), y = Math.max(0, Math.floor(top - padY));
  const endX = Math.min(captured.sourceWidth, Math.ceil(right + padX));
  const endY = Math.min(captured.sourceHeight, Math.ceil(bottom + padY));
  if (x >= endX || y >= endY) return null;
  return { x, y, width: endX - x, height: endY - y,
    sourceWidth: captured.sourceWidth, sourceHeight: captured.sourceHeight };
}
