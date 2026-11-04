"""Optional TLS around the connection (spec 14.1): the application passes ssl.SSLContext objects; the frames inside
are unchanged. Certificates are made at test time with the openssl command line tool (skipped without it), so that
no key is ever stored in the repository."""

import asyncio
import os
import shutil
import ssl
import subprocess

import pytest

from rope_protocol.hub import Hub
from rope_protocol.source import Source
from test_transfer import FAST, SRC, _file, _until


def _openssl():
    found = shutil.which("openssl")
    if found:
        return found
    git = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "usr", "bin", "openssl.exe")
    return git if os.path.isfile(git) else None


def _run(*args, cwd):
    subprocess.run([_openssl()] + list(args), cwd=cwd, check=True, capture_output=True)


def _ca(d, name):
    _run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=%s" % name,
         "-keyout", name + ".key", "-out", name + ".pem", "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign", cwd=d)


def _leaf(d, ca, name, ext):
    _run("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=%s" % name, "-keyout", name + ".key",
         "-out", name + ".csr", cwd=d)
    with open(os.path.join(d, name + ".ext"), "w") as f:
        f.write(ext)
    _run("x509", "-req", "-in", name + ".csr", "-CA", ca + ".pem", "-CAkey", ca + ".key", "-CAcreateserial",
         "-days", "2", "-out", name + ".pem", "-extfile", name + ".ext", cwd=d)


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    if not _openssl():
        pytest.skip("openssl command line tool not available")
    d = str(tmp_path_factory.mktemp("certs"))
    _ca(d, "group-ca")
    _ca(d, "other-ca")
    _leaf(d, "group-ca", "hub", "subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n")
    _leaf(d, "group-ca", "source-1", "extendedKeyUsage=clientAuth\n")
    _leaf(d, "other-ca", "stranger", "extendedKeyUsage=clientAuth\n")
    return d


def server_context(d):
    """Mutual TLS: the hub proves itself and accepts only clients with a certificate of the group's CA."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(os.path.join(d, "hub.pem"), os.path.join(d, "hub.key"))
    ctx.load_verify_locations(os.path.join(d, "group-ca.pem"))
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def client_context(d, name, ca="group-ca"):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(os.path.join(d, ca + ".pem"))
    ctx.load_cert_chain(os.path.join(d, name + ".pem"), os.path.join(d, name + ".key"))
    return ctx


async def _hub(tmp, d):
    return await Hub(os.path.join(tmp, "hub"), {"source-1": "source"}, "op-1", port=0, ssl=server_context(d),
                     **FAST).start()


def test_stream_and_message_over_mutual_tls(tmp_path, certs):
    data = os.urandom(300_000)
    path = _file(str(tmp_path), "rec.bin", data)
    got = []

    async def run():
        hub = await _hub(str(tmp_path), certs)
        hub.on_message = lambda meta, body: got.append(body)
        src = Source("source-1", "op-1", "127.0.0.1", {"rec": path}, str(tmp_path / "src"), hub_port=hub.port,
                     ssl=client_context(certs, "source-1"), **SRC).start()
        try:
            src.complete("rec")
            src.send_message([hub.hub_id], "note", b"over tls")
            assert await src.wait_checked("rec", 20) == "ok"
            await _until(lambda: got)
            assert open(hub.store.get("source-1", "rec", 1).path, "rb").read() == data     # bit for bit
            assert got == [b"over tls"]
        finally:
            await src.stop()
            await hub.stop()
    asyncio.run(run())


@pytest.mark.parametrize("case", ["no_tls", "foreign_certificate", "unknown_hub"])
def test_connection_refused_without_the_right_certificates(tmp_path, certs, case):
    """A participant without TLS, with a certificate of another CA, or that does not trust the hub never gets a
    session; it keeps retrying with back-off (spec 9) and nothing is stored."""
    path = _file(str(tmp_path), "rec.bin", os.urandom(10_000))

    async def run():
        hub = await _hub(str(tmp_path), certs)
        ctx = {"no_tls": None,
               "foreign_certificate": client_context(certs, "stranger"),
               "unknown_hub": client_context(certs, "source-1", ca="other-ca")}[case]
        src = Source("source-1", "op-1", "127.0.0.1", {"rec": path}, str(tmp_path / "src"), hub_port=hub.port,
                     ssl=ctx, **SRC).start()
        try:
            await asyncio.sleep(1.5)
            assert not src.connected.is_set()
            assert hub.sessions_started == 0
            assert not [e for e in hub.store.entries() if e["participant"] == "source-1"]
        finally:
            await src.stop()
            await hub.stop()
    asyncio.run(run())
