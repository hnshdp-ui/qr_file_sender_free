"""Serve the standalone receiver over HTTPS. No pip setup required."""
from __future__ import annotations

import argparse
import hashlib
import socket
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


class ReceiverHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits multiple live processes to bind one port,
    # which can leave Safari talking to an older receiver after a restart.
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_handler(resources: dict[str, tuple[bytes, str]]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "QFSReceiver/1.0"
        sys_version = ""

        def do_GET(self):
            self.respond(body=True)

        def do_HEAD(self):
            self.respond(body=False)

        def respond(self, body: bool):
            resource = resources.get(urlsplit(self.path).path)
            if resource is None:
                self.send_error(404)
                return
            content, mime = resource
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if mime == "text/html; charset=utf-8":
                self.send_header("Permissions-Policy", "camera=(self), microphone=()")
            self.end_headers()
            if body:
                self.wfile.write(content)

        def log_message(self, _format, *_args):
            # No request URLs, filenames, QR bytes, or received files are logged.
            pass

    return Handler


def make_https_server(bind: str, port: int, page: Path, cert: Path, key: Path):
    content = page.read_bytes()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert, keyfile=key)
    resource = (content, "text/html; charset=utf-8")
    server = ReceiverHTTPServer((bind, port), make_handler({
        "/": resource, "/receive/": resource, "/receiver-standalone.html": resource,
    }))
    try:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    except Exception:
        server.server_close()
        raise
    return server


def make_ca_server(bind: str, port: int, ca: Path):
    content = ca.read_bytes()
    # Serve this public certificate only, never a filesystem directory or keys.
    return ReceiverHTTPServer((bind, port), make_handler({
        "/rootCA.cer": (content, "application/x-x509-ca-cert"),
    }))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0", help="IPv4 interface to listen on")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--no-terminal-qr", action="store_true", help="print receiver URLs without terminal QR codes")
    parser.add_argument("--cert", type=Path, default=ROOT / "certs/receiver.pem")
    parser.add_argument("--key", type=Path, default=ROOT / "certs/receiver-key.pem")
    parser.add_argument("--page", type=Path, default=ROOT / "receiver-standalone.html")
    parser.add_argument("--bootstrap-ca", action="store_true", help="also serve the public CA on HTTP for initial iPhone setup")
    parser.add_argument("--ca", type=Path, default=ROOT / "certs/rootCA.cer")
    parser.add_argument("--ca-port", type=int, default=8000)
    args = parser.parse_args(argv)
    https = bootstrap = None
    try:
        https = make_https_server(args.bind, args.port, args.page, args.cert, args.key)
        if args.bootstrap_ca:
            bootstrap = make_ca_server(args.bind, args.ca_port, args.ca)
            threading.Thread(target=bootstrap.serve_forever, daemon=True).start()
    except (OSError, ssl.SSLError) as error:
        if https:
            https.server_close()
        print(f"Cannot start receiver server: {error}", file=sys.stderr)
        print("Prepare certificates first; see docs/WIN10_RECEIVER_SERVER.md.", file=sys.stderr)
        return 1
    address_file = ROOT / "certs/server-address.txt"
    if address_file.exists():
        addresses = [address_file.read_text(encoding="utf-8-sig").strip()]
    else:
        try:
            addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        except OSError:
            addresses = ["SERVER_IP"]
    print("QFS ad-free receiver server (Ctrl+C to stop)")
    print("Use the LAN address included in your certificate:")
    for address in addresses:
        url = f"https://{address}:{https.server_port}/"
        print(f"  Receiver: {url}")
        if not args.no_terminal_qr:
            try:
                from receiver_terminal_qr import print_receiver_qr
                print_receiver_qr(url)
            except (ImportError, OSError, ValueError, UnicodeError) as error:
                print(f"Terminal QR unavailable: {error}. Open the Receiver URL above.")
        if bootstrap:
            print(f"  Install CA: http://{address}:{bootstrap.server_port}/rootCA.cer")
    if bootstrap:
        print("Public CA SHA-256:", hashlib.sha256(args.ca.read_bytes()).hexdigest())
        print("After the iPhone trusts this CA, restart without --bootstrap-ca.")
    print("This server serves the page only; file reconstruction and saving happen on the iPhone.", flush=True)
    try:
        https.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        https.server_close()
        if bootstrap:
            bootstrap.shutdown()
            bootstrap.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
