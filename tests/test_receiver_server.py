import http.client
import shutil
import ssl
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from receiver_server import main, make_ca_server, make_https_server


@pytest.fixture
def tls_files(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell 7+ is required to create the test TLS certificate")
    subprocess.run([pwsh, "-NoProfile", "-File",
                    str(Path(__file__).with_name("make_test_tls_certificate.ps1")),
                    "-OutputDirectory", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_https_serves_only_receiver_and_rejects_uploads(tls_files):
    root = Path(__file__).parents[1]
    server = make_https_server("127.0.0.1", 0, root / "receiver-standalone.html",
                               tls_files / "cert.pem", tls_files / "key.pem")
    context = ssl.create_default_context(cafile=str(tls_files / "cert.pem"))
    with running(server) as port:
        for route in ["/", "/receive/", "/receiver-standalone.html?debug=1"]:
            connection = http.client.HTTPSConnection("127.0.0.1", port, context=context)
            connection.request("GET", route)
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader("Cache-Control") == "no-store"
            assert response.getheader("Permissions-Policy") == "camera=(self), microphone=()"
            assert response.read() == (root / "receiver-standalone.html").read_bytes()
            connection.close()
        for method, route, status in [
            ("GET", "/certs/receiver-key.pem", 404),
            ("GET", "/../receiver_server.py", 404),
            ("GET", "/rootCA-key.pem", 404),
            ("POST", "/", 501),
        ]:
            connection = http.client.HTTPSConnection("127.0.0.1", port, context=context)
            connection.request(method, route)
            response = connection.getresponse()
            assert response.status == status
            response.read()
            connection.close()
        connection = http.client.HTTPSConnection("127.0.0.1", port, context=context)
        connection.request("HEAD", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert int(response.getheader("Content-Length")) == (root / "receiver-standalone.html").stat().st_size
        assert response.read() == b""
        connection.close()


def test_bootstrap_serves_only_public_ca(tls_files):
    with running(make_ca_server("127.0.0.1", 0, tls_files / "ca.cer")) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port)
        connection.request("GET", "/rootCA.cer")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/x-x509-ca-cert"
        assert response.read() == (tls_files / "ca.cer").read_bytes()
        connection.close()
        for route in ["/", "/receiver-standalone.html", "/key.pem", "/rootCA-key.pem"]:
            connection = http.client.HTTPConnection("127.0.0.1", port)
            connection.request("GET", route)
            response = connection.getresponse()
            assert response.status == 404
            response.read()
            connection.close()


def test_receiver_port_cannot_be_shared_by_a_second_server(tls_files):
    page = Path(__file__).parents[1] / "receiver-standalone.html"
    with running(make_https_server("127.0.0.1", 0, page, tls_files / "cert.pem", tls_files / "key.pem")) as port:
        with pytest.raises(OSError):
            make_https_server("127.0.0.1", port, page, tls_files / "cert.pem", tls_files / "key.pem")


def test_missing_certificate_reports_setup_error(tmp_path, capsys):
    assert main(["--cert", str(tmp_path / "missing.pem"), "--key", str(tmp_path / "missing-key.pem")]) == 1
    assert "Prepare certificates first" in capsys.readouterr().err
