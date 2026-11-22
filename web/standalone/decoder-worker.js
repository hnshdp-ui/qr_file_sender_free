// Libraries and QFS_WASM_BASE64 are embedded by the single-file builder.
let primary = "JSQR", initializationError = "", noResultStreak = 0;
const initialization = (async () => {
  try {
    const binary = Uint8Array.from(atob(QFS_WASM_BASE64), (char) => char.charCodeAt(0));
    await ZXingWASM.prepareZXingModule({ fireImmediately: true, overrides: {
      wasmBinary: binary,
      // Emscripten resolves a filename even with wasmBinary supplied. This is
      // only a label; the bytes above prevent any fetch (CSP blocks it too).
      locateFile() { return "qfs-embedded-reader.wasm"; },
    } });
    primary = "ZXING-WASM";
  } catch (error) { initializationError = error.message || String(error); }
  self.postMessage({ ready: true, decoder: primary, fallbackReason: initializationError });
})();

function jsQr(pixels, width, height) {
  const qr = self.jsQR(pixels, width, height, { inversionAttempts: "attemptBoth" });
  return { binary: qr?.binaryData || null, location: qr?.location || null };
}

self.onmessage = async ({ data }) => {
  await initialization;
  const started = performance.now();
  let result = { binary: null, location: null }, decoder = primary, reason = initializationError;
  try {
    if (primary === "ZXING-WASM") {
      const robust = !data.tracking || noResultStreak >= 2;
      try {
        const [barcode] = await ZXingWASM.readBarcodes({ data: data.pixels, width: data.width, height: data.height }, {
          formats: ["QRCode"], tryHarder: robust, tryRotate: robust, tryInvert: robust,
          tryDownscale: robust, maxNumberOfSymbols: 1,
        });
        if (barcode?.bytes?.length) {
          const p = barcode.position;
          result = { binary: barcode.bytes, location: p ? {
            topLeftCorner: p.topLeft, topRightCorner: p.topRight,
            bottomLeftCorner: p.bottomLeft, bottomRightCorner: p.bottomRight,
          } : null };
          noResultStreak = 0;
        } else noResultStreak += 1;
      } catch (error) {
        reason = error.message || String(error);
        primary = "JSQR";
      }
      // An occasional jsQR assist retains compatibility with difficult frames.
      if (!result.binary && (primary === "JSQR" || noResultStreak >= 3)) {
        result = jsQr(data.pixels, data.width, data.height);
        decoder = primary === "JSQR" ? "JSQR (WASM fallback)" : "JSQR assist / ZXING-WASM";
        noResultStreak = 0;
      }
    } else result = jsQr(data.pixels, data.width, data.height);
    self.postMessage({ ...result, decoder, fallbackReason: reason, decodeMs: performance.now() - started });
  } catch (error) { self.postMessage({ error: error.message || String(error), decoder }); }
};
