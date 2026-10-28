"""Optional TLS verification tests; cryptography generates disposable test keys."""
import datetime
import ipaddress
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    x509 = None

from sabz_edge.client import CameraClient
from sabz_edge.runtime import Runtime
from sabz_edge.server import Server, Settings
from sabz_edge.store import Store


@unittest.skipIf(x509 is None, "install the test extra for ephemeral certificate generation")
class TLSTests(unittest.TestCase):
    def test_verified_tls_sdk_and_untrusted_certificate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SABZ disposable test certificate")])
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - datetime.timedelta(minutes=1))
                    .not_valid_after(now + datetime.timedelta(hours=1))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                    .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                    .sign(key, hashes.SHA256()))
            cert_path, key_path = root / "cert.pem", root / "key.pem"
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            key_path.chmod(0o600)
            runtime = Runtime(Store(":memory:"))
            settings = Settings({"SABZ_CAMERA_TOKEN": "c" * 32, "SABZ_READER_TOKEN": "r" * 32,
                                 "SABZ_PORT": "0", "SABZ_TLS_CERT": str(cert_path), "SABZ_TLS_KEY": str(key_path)})
            server = Server(settings, runtime)
            runtime.start()
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
            thread.start()
            endpoint = f"https://127.0.0.1:{server.server_port}"
            trusted = CameraClient(endpoint, "c" * 32, str(root / "trusted.db"), ca_file=str(cert_path))
            untrusted = CameraClient(endpoint, "c" * 32, str(root / "untrusted.db"))
            try:
                result = trusted.send(dict.fromkeys("NSEW", 1))
                self.assertEqual(result["mode"], "bench")
                with self.assertRaises(urllib.error.URLError):
                    untrusted.send(dict.fromkeys("NSEW", 1))
            finally:
                trusted.close(); untrusted.close()
                server.shutdown(); server.server_close(); thread.join(); runtime.close()
