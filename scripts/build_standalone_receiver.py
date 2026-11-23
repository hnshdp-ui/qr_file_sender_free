"""Build a self-contained, ad-free QFS1 receiver with no npm dependencies."""
import json
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline_module(path, namespace, names):
    source = (ROOT / path).read_text(encoding="utf-8")
    if re.search(r"^import\s", source, re.MULTILINE):
        raise ValueError(f"Bundle dependencies explicitly before adding imports: {path}")
    source = re.sub(r"^export (?=(?:const|function|class)\s)", "", source, flags=re.MULTILINE)
    return f"const {namespace} = (() => {{\n{source}\nreturn {{{names}}};\n}})();"


def build():
    decoder = (ROOT / "web/vendor/jsqr.js").read_text(encoding="utf-8")
    wasm = base64.b64encode((ROOT / "web/vendor/zxing_reader.wasm").read_bytes()).decode("ascii")
    worker = "const QFS_WASM_BASE64 = " + json.dumps(wasm) + ";\n"
    worker += decoder + "\n" + (ROOT / "web/vendor/zxing-wasm.js").read_text(encoding="utf-8")
    worker += "\n" + (ROOT / "web/standalone/decoder-worker.js").read_text(encoding="utf-8")
    scripts = [
        decoder,
        inline_module("web/protocol.js", "QFSProtocol", "SourceReceiver, parsePacket"),
        inline_module("web/optical-pipeline.js", "QFSCamera", "CAMERA_CONSTRAINTS, startSafeVideoFrameLoop"),
        inline_module("web/standalone/capture.js", "QFSCapture", "cameraFrameToken, shouldSkipCameraFrame, trackedQrRegion"),
        inline_module("web/standalone/repair.js", "QFSRepair", "repairSummary"),
        "const QFS_WORKER_SOURCE = " + json.dumps(worker) + ";",
        (ROOT / "web/standalone/receiver.js").read_text(encoding="utf-8"),
    ]
    # Escape closing tags even inside JS strings to keep the HTML parser in script mode.
    script = "\n".join(scripts).replace("</script", "<\\/script")
    template = (ROOT / "web/standalone/receiver.template.html").read_text(encoding="utf-8")
    licenses = [
        (ROOT / "LICENSE").read_text(encoding="utf-8"),
        "jsQR 1.4.0 (jsQR contributors) and ZXing-C++ reader: Apache-2.0.",
        (ROOT / "web/vendor/Apache-2.0.LICENSE").read_text(encoding="utf-8"),
        "zxing-wasm 3.1.2 JavaScript wrapper:",
        (ROOT / "web/vendor/zxing-wasm.LICENSE").read_text(encoding="utf-8"),
    ]
    notice = "\n".join(licenses).replace("-->", "--&gt;")
    template = template.replace("<!doctype html>", f"<!doctype html>\n<!--\n{notice}\n-->")
    output = ROOT / "receiver-standalone.html"
    output.write_text(template.replace("<!-- INLINE_RECEIVER -->", "<script>\n" + script + "\n</script>"),
                      encoding="utf-8", newline="\n")
    print(f"Built {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
