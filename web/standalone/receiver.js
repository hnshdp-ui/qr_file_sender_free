(() => {
  "use strict";
  const { SourceReceiver, parsePacket } = QFSProtocol;
  const { CAMERA_CONSTRAINTS, startSafeVideoFrameLoop } = QFSCamera;
  const { cameraFrameToken, shouldSkipCameraFrame, trackedQrRegion } = QFSCapture;
  const el = (id) => document.getElementById(id);
  const video = el("camera"), canvas = el("frame"), start = el("start"), stop = el("stop");
  let receiver, stream = null, worker = null, stopLoop = null, busy = false, starting = false;
  let generation = 0, objectUrl = null, completedFile = null, frames = 0, decoded = 0;
  let metricTimer = null, workerTimer = null, workerUrl = null, workerReady = false;
  let attempts = 0, qrFound = 0, busySince = 0, lastScan = -Infinity, cameraStarted = 0;
  let decoderState = "未启动", lastError = "";
  let taskStarted = null, taskEnded = null, finishedAt = null, taskTimer = null;
  let decodeMs = 0, attemptBaseline = 0;
  let region = null, regionMisses = 0, capturedRegion = null, frameToken = null, skippedVideoFrames = 0;
  let captureMs = 0, workerRoundTripMs = 0, forcedCaptures = 0, recentAttempts = [];
  let captureSource = null;
  let fallbackFrameToken = null, fallbackFrameChanged = 0;
  let loopCalls = 0, busySkips = 0, intervalSkips = 0, lastDiagnosticSample = -Infinity, diagnosticUrl = null;
  const diagnostics = [], diagnosticStarted = performance.now();
  function log(event, detail = {}) {
    diagnostics.push({ ms: Math.round(performance.now() - diagnosticStarted), event, ...detail });
    if (diagnostics.length > 6000) diagnostics.splice(0, diagnostics.length - 6000);
  }
  function cameraSettings() {
    try {
      const settings = stream?.getVideoTracks?.()[0]?.getSettings?.() || {};
      return { width: settings.width, height: settings.height, frameRate: settings.frameRate, facingMode: settings.facingMode };
    } catch (_) { return {}; }
  }
  const status = (message) => { el("status").textContent = message; };

  function duration(milliseconds) {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    const parts = [Math.floor(seconds / 60), seconds % 60];
    if (seconds >= 3600) parts.splice(0, 1, Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60);
    return parts.map((part) => String(part).padStart(2, "0")).join(":");
  }
  function taskElapsed() { return taskStarted === null ? 0 : (taskEnded ?? performance.now()) - taskStarted; }
  function refreshTask() {
    el("task-time").textContent = `任务耗时 ${duration(taskElapsed())}` +
      (finishedAt ? ` · 完成时间 ${finishedAt.toLocaleString("zh-CN", { hour12: false })}` :
        taskStarted === null ? "（收到首个任务元数据后开始计时）" : "（含暂停时间）");
  }
  function releaseWorkerUrl() {
    if (workerUrl) URL.revokeObjectURL(workerUrl);
    workerUrl = null;
  }
  function dropWorker(reason = "主线程") {
    clearTimeout(workerTimer); workerTimer = null;
    worker?.terminate(); worker = null; workerReady = false; busy = false;
    releaseWorkerUrl(); decoderState = reason;
  }
  function refreshMetrics() {
    const current = receiver;
    const now = performance.now();
    recentAttempts = recentAttempts.filter((time) => now - time < 3000);
    const recentRate = recentAttempts.length / Math.max(0.001, Math.min(3, (now - cameraStarted) / 1000));
    el("metrics").textContent = `扫描 ${frames} 帧 · 解码 ${attempts} 次 · QR ${qrFound} 个 · QFS ${decoded} 帧` +
      (current?.meta ? ` · 有效数据 ${current.usefulSymbols}/${current.meta.sourceCount}` : "") +
      (current?.meta ? `\n独立 DATA ${current.usefulSymbols} · 重复 DATA ${current.duplicateCount}` : "") +
      `\n解码速度 ${((attempts - attemptBaseline) / Math.max(0.001, (now - cameraStarted) / 1000)).toFixed(1)} 次/秒 · 最近3秒 ${recentRate.toFixed(1)} 次/秒 · 最近解码 ${decodeMs.toFixed(0)} ms` +
      (current?.meta && taskStarted !== null ? ` · 有效吞吐 ${(Math.min(current.meta.fileSize, current.usefulSymbols * current.meta.symbolSize) / 1024 / Math.max(0.001, taskElapsed() / 1000)).toFixed(1)} KiB/s` : "") +
      `\n画面 ${video.videoWidth || 0}×${video.videoHeight || 0} · readyState ${video.readyState || 0} · ${captureSource || "等待视频帧"} · ${decoderState}` +
      `\n区域 ${region ? "QR 跟踪" : "全画面"} · 解码输入 ${capturedRegion?.imageWidth || 0}×${capturedRegion?.imageHeight || 0} · 跳过重复视频帧 ${skippedVideoFrames}` +
      `\n取图 ${captureMs.toFixed(0)} ms · Worker 往返 ${workerRoundTripMs.toFixed(0)} ms · 相机报告 ${cameraSettings().frameRate ?? "未知"} FPS · 保底重采 ${forcedCaptures}` +
      (lastError ? `\n最近错误：${lastError}` : "");
    if (now - lastDiagnosticSample >= 1000) {
      lastDiagnosticSample = now;
      log("sample", { frames, attempts, qrFound, decoded, useful: current?.usefulSymbols || 0,
        sourceCount: current?.meta?.sourceCount, symbolSize: current?.meta?.symbolSize,
        recentRate, decodeMs, captureMs, workerRoundTripMs, captureSource,
        loopCalls, busySkips, intervalSkips, skippedVideoFrames, forcedCaptures,
        token: frameToken, mediaTime: video.currentTime, readyState: video.readyState,
        input: capturedRegion, camera: cameraSettings(), decoder: decoderState, cameraActive: Boolean(stream) });
    }
    const missing = el("missing-sources");
    const repair = QFSRepair.repairSummary(current);
    missing.textContent = repair.message;
    el("missing-numbers").value = repair.numbers;
    el("copy-missing").disabled = !repair.numbers;
    if (stream && !frames && performance.now() - cameraStarted > 3000) {
      status("摄像头已授权，但尚未取得可解码画面。请确认预览在变化，并保持 Safari 在前台。");
    }
  }
  function pause() {
    log("pause");
    generation += 1;
    stopLoop?.(); stopLoop = null;
    stream?.getTracks().forEach((track) => track.stop()); stream = null;
    clearInterval(metricTimer); metricTimer = null;
    dropWorker(); starting = false;
    video.srcObject = null; video.hidden = true; stop.hidden = true;
    start.disabled = Boolean(completedFile);
  }
  function update(current) {
    if (current !== receiver) return;
    el("progress").hidden = !current.meta;
    el("progress").value = current.progress;
    refreshMetrics();
    if (completedFile) return;
    if (current.completed) {
      pause();
      taskEnded = performance.now();
      clearInterval(taskTimer); taskTimer = null;
      refreshTask();
      if (!current.completed.verified) { status("SHA-256 校验失败。请点击“重新接收”再试，未提供文件下载。"); return; }
      finishedAt = new Date(); refreshTask();
      completedFile = new File([current.completed.archive], current.completed.filename, { type: "application/zip" });
      objectUrl = URL.createObjectURL(completedFile);
      el("download").href = objectUrl; el("download").download = completedFile.name;
      el("verified").textContent = `✓ SHA-256 校验通过 · ${completedFile.name} · ${completedFile.size.toLocaleString()} 字节`;
      el("result").hidden = false;
      try { el("share").hidden = !navigator.canShare?.({ files: [completedFile] }); } catch (_) { el("share").hidden = true; }
      start.disabled = true;
      status(`接收完成，用时 ${duration(taskElapsed())}，可以直接保存文件。`);
    } else if (current.finishing) status("文件已还原，正在进行 SHA-256 校验…");
    else if (current.meta) status(`正在接收 ${Math.round(current.progress * 100)}%：请保持二维码完整、清晰。`);
  }
  function reset() {
    pause();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null; completedFile = null; frames = 0; decoded = 0;
    attempts = 0; qrFound = 0; lastError = ""; lastScan = -Infinity; decoderState = "未启动";
    clearInterval(taskTimer); taskTimer = null;
    taskStarted = null; taskEnded = null; finishedAt = null;
    decodeMs = 0; attemptBaseline = 0;
    region = null; regionMisses = 0; capturedRegion = null; frameToken = null; skippedVideoFrames = 0;
    captureMs = 0; workerRoundTripMs = 0; forcedCaptures = 0; recentAttempts = [];
    captureSource = null;
    loopCalls = 0; busySkips = 0; intervalSkips = 0;
    log("reset");
    el("result").hidden = true; el("download").removeAttribute("href");
    receiver = new SourceReceiver(update); start.disabled = false;
    update(receiver); refreshTask(); status("点击“开始接收”，对准电脑动态二维码。");
  }
  function accept(binary) {
    if (!binary || completedFile) return false;
    qrFound += 1;
    try {
      const bytes = Uint8Array.from(binary), parsed = parsePacket(bytes);
      // Lock onto the first META session until the user explicitly resets.
      if (receiver.sessionKey && parsed.sessionKey !== receiver.sessionKey) return false;
      if (taskStarted === null && parsed.meta) {
        taskStarted = performance.now();
        taskTimer = setInterval(refreshTask, 500); refreshTask();
      }
      decoded += 1;
      const before = receiver.usefulSymbols;
      const accepted = receiver.feed(bytes);
      log("packet", { accepted, type: parsed.meta ? "META" : "DATA", session: parsed.sessionKey.slice(0, 8),
        sourceNumber: parsed.meta ? 0 : parsed.data && receiver.meta && parsed.data.symbolIndex < parsed.data.sourceCount
          ? parsed.data.blockId * receiver.meta.blockSize + parsed.data.symbolIndex + 1 : null,
        block: parsed.data?.blockId, symbol: parsed.data?.symbolIndex, useful: receiver.usefulSymbols,
        recovered: receiver.usefulSymbols - before });
    } catch (error) { log("packet-error", { message: error.message }); return false; }
    return true;
  }
  function decodedResult(data) {
    const valid = accept(data.binary);
    if (valid && data.location) {
      region = trackedQrRegion(data.location, capturedRegion);
      regionMisses = 0;
    } else if (region && ++regionMisses >= 3) {
      region = null; regionMisses = 0;
    }
  }
  function frame(source, presentedFrames) {
    const now = performance.now();
    loopCalls += 1;
    if (!stream || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return;
    if (busy && now - busySince > 2500) dropWorker("主线程（Worker 响应超时）");
    if (busy || (worker && !workerReady)) { busySkips += 1; return; }
    let token = source === "rVFC" ? `presented:${presentedFrames}` : cameraFrameToken(video);
    if (source === "rAF") {
      const elapsed = now - lastScan;
      if (token?.startsWith("frame:")) {
        if (token !== fallbackFrameToken) {
          fallbackFrameToken = token;
          fallbackFrameChanged = now;
        } else if (now - fallbackFrameChanged >= 80 && Number.isFinite(video.currentTime)) {
          token = `time:${video.currentTime}`;
        }
      }
      // Without a frame counter, currentTime can advance at the display rate.
      if (!token?.startsWith("frame:") && elapsed < 25) { intervalSkips += 1; return; }
      if (shouldSkipCameraFrame(token, frameToken, elapsed)) { skippedVideoFrames += 1; return; }
      if (token !== null && token === frameToken) forcedCaptures += 1;
    }
    captureSource = source;
    frameToken = token;
    lastScan = now;
    if (region?.sourceWidth !== video.videoWidth || region?.sourceHeight !== video.videoHeight) region = null;
    const crop = region || { x: 0, y: 0, width: video.videoWidth, height: video.videoHeight };
    const scale = Math.min(1, 1280 / Math.max(crop.width, crop.height));
    const width = Math.round(crop.width * scale), height = Math.round(crop.height * scale);
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    capturedRegion = { ...crop, imageWidth: width, imageHeight: height,
      sourceWidth: video.videoWidth, sourceHeight: video.videoHeight };
    try {
      const captureStarted = performance.now();
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) throw new Error("Canvas 2D 不可用");
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(video, crop.x, crop.y, crop.width, crop.height, 0, 0, width, height);
      const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
      captureMs = performance.now() - captureStarted;
      frames += 1; attempts += 1;
      recentAttempts.push(performance.now());
      if (worker) {
        busy = true; busySince = performance.now();
        worker.postMessage({ pixels: image.data, width: image.width, height: image.height, tracking: Boolean(region) }, [image.data.buffer]);
      } else {
        const decodeStarted = performance.now();
        const qr = globalThis.jsQR(image.data, image.width, image.height, { inversionAttempts: "attemptBoth" });
        decodeMs = performance.now() - decodeStarted;
        decodedResult({ binary: qr?.binaryData, location: qr?.location });
      }
    } catch (error) {
      lastError = error.message || String(error); log("capture-error", { message: lastError });
      if (worker) dropWorker("主线程（Worker 不可用）");
      status(`画面读取或解码失败：${lastError}`);
    }
  }
  function initWorker() {
    try {
      workerUrl = URL.createObjectURL(new Blob([QFS_WORKER_SOURCE], { type: "text/javascript" }));
      worker = new Worker(workerUrl); decoderState = "Worker 启动中";
      const activeWorker = worker;
      workerTimer = setTimeout(() => dropWorker("主线程（Worker 启动超时）"), 8000);
      worker.onmessage = ({ data }) => {
        if (worker !== activeWorker) return;
        if (data.ready) {
          workerReady = true; decoderState = data.decoder || "Worker";
          if (data.fallbackReason) lastError = data.fallbackReason;
          log("worker-ready", { decoder: decoderState, reason: data.fallbackReason });
          clearTimeout(workerTimer); workerTimer = null; releaseWorkerUrl(); return;
        }
        if (busy) workerRoundTripMs = performance.now() - busySince;
        busy = false;
        if (data.decoder) decoderState = data.decoder;
        if (data.fallbackReason) lastError = data.fallbackReason;
        if (Number.isFinite(data.decodeMs)) decodeMs = data.decodeMs;
        if (data.error) { lastError = data.error; dropWorker("主线程（Worker 解码失败）"); return; }
        decodedResult(data);
      };
      worker.onerror = (error) => { lastError = error.message || "Worker 加载失败"; dropWorker("主线程（Worker 加载失败）"); };
    } catch (error) { lastError = error.message || String(error); dropWorker("主线程"); }
  }
  async function begin() {
    if (starting || stream || completedFile) return;
    if (!navigator.mediaDevices?.getUserMedia || !globalThis.crypto?.subtle) {
      status("当前环境无法使用摄像头或 SHA-256。离线使用请在手机本机启动服务，再用 Safari 打开 http://127.0.0.1:8000/receiver-standalone.html；也支持可信 HTTPS 来源。附件预览可能不支持。"); return;
    }
    starting = true; start.disabled = true;
    const ticket = ++generation;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ video: CAMERA_CONSTRAINTS, audio: false });
      if (ticket !== generation) { acquired.getTracks().forEach((track) => track.stop()); return; }
      stream = acquired; video.muted = true; video.playsInline = true;
      log("camera-start", { settings: cameraSettings() });
      video.srcObject = stream; video.hidden = false;
      await video.play();
      if (ticket !== generation) return;
      initWorker(); stop.hidden = false;
      cameraStarted = performance.now(); lastScan = -Infinity;
      frameToken = null; captureSource = null; fallbackFrameToken = null; region = null; regionMisses = 0;
      attemptBaseline = attempts;
      recentAttempts = [];
      status("摄像头已开启，正在等待 QFS1 二维码…");
      stopLoop = startSafeVideoFrameLoop(video, frame);
      metricTimer = setInterval(refreshMetrics, 500);
      refreshMetrics();
    } catch (error) {
      if (ticket === generation) { pause(); status(`无法开启摄像头：${error.message}。请检查 Safari 摄像头权限，并通过手机本机 127.0.0.1 或可信 HTTPS 来源打开。`); }
    } finally { if (ticket === generation) { starting = false; start.disabled = false; } }
  }
  start.addEventListener("click", begin);
  stop.addEventListener("click", () => { pause(); status("摄像头已暂停，接收进度保留。点击“开始接收”继续。"); });
  el("reset").addEventListener("click", reset);
  el("export-log").addEventListener("click", () => {
    log("export");
    if (diagnosticUrl) URL.revokeObjectURL(diagnosticUrl);
    const report = { version: "v20261122.1", exportedAt: new Date().toISOString(),
      userAgent: navigator.userAgent || "", maxEntries: 6000, events: diagnostics.slice() };
    diagnosticUrl = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    el("export-log").href = diagnosticUrl;
  });
  el("copy-missing").addEventListener("click", async () => {
    const field = el("missing-numbers");
    try {
      await navigator.clipboard.writeText(field.value);
      el("copy-status").textContent = "已复制。请手工输入断网 PC，或在可用的本地方式中保存这些编号。";
    } catch (_) {
      field.focus(); field.select();
      el("copy-status").textContent = "请长按编号复制，或直接照着输入 PC。";
    }
  });
  el("share").addEventListener("click", async () => {
    if (!completedFile) return;
    try { await navigator.share({ files: [completedFile], title: completedFile.name }); }
    catch (error) { if (error.name !== "AbortError") status("系统分享不可用，请点击“下载 ZIP”保存。"); }
  });
  globalThis.addEventListener("pagehide", pause);
  globalThis.addEventListener("unhandledrejection", () => { pause(); status("接收或校验出现异常，请重新接收。尚未提供未经校验的文件。"); });
  reset();
  if (location.protocol === "file:" || !globalThis.isSecureContext) {
    el("environment").hidden = false;
    el("environment").textContent = "当前为本地文件或非安全来源。iPhone 附件预览可能无法调用摄像头；离线使用请在手机本机启动服务，通过 Safari 打开 http://127.0.0.1:8000/receiver-standalone.html。";
  }
})();
