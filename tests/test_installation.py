import json
from pathlib import Path
import tempfile
import unittest
from sabz_edge.preflight import inspect

class InstallationTests(unittest.TestCase):
    def environment(self,root):
        return {'SABZ_CAMERA_TOKEN':'camera-secret-'+'a'*40,'SABZ_READER_TOKEN':'reader-secret-'+'b'*40,
                'SABZ_STATE_PATH':str(Path(root)/'edge.sqlite3')}

    def test_valid_installation_does_not_claim_physical_readiness(self):
        with tempfile.TemporaryDirectory() as root:
            env=self.environment(root)
            original=b'existing replay state must not be touched'
            Path(env['SABZ_STATE_PATH']).write_bytes(original)
            report=inspect(env)
            self.assertTrue(report['installation_ready'])
            self.assertFalse(report['field_ready'])
            self.assertEqual(Path(env['SABZ_STATE_PATH']).read_bytes(),original)
            self.assertEqual([p.name for p in Path(root).iterdir()],['edge.sqlite3'])
            self.assertNotIn(env['SABZ_CAMERA_TOKEN'],json.dumps(report))

    def test_bad_configuration_does_not_disclose_secrets(self):
        env={'SABZ_CAMERA_TOKEN':'private-invalid-secret','SABZ_READER_TOKEN':'private-invalid-secret'}
        report=inspect(env)
        self.assertFalse(report['installation_ready'])
        self.assertNotIn('private-invalid-secret',json.dumps(report))

    def test_missing_storage_directory_is_actionable(self):
        with tempfile.TemporaryDirectory() as root:
            env=self.environment(Path(root)/'missing')
            report=inspect(env)
            self.assertFalse(report['installation_ready'])
            self.assertFalse(Path(root,'missing').exists())

    def test_remote_binding_without_tls_fails(self):
        with tempfile.TemporaryDirectory() as root:
            env=dict(self.environment(root),SABZ_BIND='0.0.0.0')
            self.assertFalse(inspect(env)['installation_ready'])
