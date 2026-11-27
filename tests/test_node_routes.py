"""Exercise link conversion and local library operations with disposable credentials."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import node_routes as routes


class Routes(unittest.TestCase):
    def test_library(self):
        core = os.environ['SING_BOX']
        identity = '00000000-0000-4000-8000-000000000001'
        blob = base64.b64encode(f'none:{identity}@127.0.0.1:443'.encode()).decode()
        standard = f'vless://{identity}@127.0.0.1:443?security=tls&type=ws&host=example.org#Demo'
        legacy = f'vless://{blob}?remarks=Demo&tls=1&obfs=websocket&obfsParam=example.org'
        self.assertEqual(routes.parse(standard, 'lo0'), routes.parse(legacy, 'lo0'))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'sing-box').symlink_to(core)
            config = base / 'config.json'
            library = base / 'nodes.json'
            original = {'tag': routes.TAG, 'type': 'direct', 'bind_interface': 'lo0'}
            config.write_text(json.dumps({'outbounds': [original]}))
            with patch.multiple(routes, BASE=base, CONFIG=config, LIBRARY=library):
                first = routes.manage('list')
                for link in (standard, legacy, 'hy2://demo@127.0.0.1:443?obfs=none&downmbps=50#HY',
                             'trojan://demo@127.0.0.1:443#Trojan',
                             'ss://YWVzLTI1Ni1nY206ZGVtbw@127.0.0.1:443#SS'):
                    result = routes.manage('import', link)
                self.assertEqual(len(result['nodes']), 5)
                self.assertEqual(result['selected'], first['selected'])
                self.assertEqual(library.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(routes.NodeError):
                    routes.manage('import', standard.replace('#Demo', '&unknown=1'))
                def apply(data, previous):
                    self.assertEqual(config.read_bytes(), previous)
                    routes.write_private(config, data)
                with patch.object(routes, 'activate', side_effect=apply):
                    dest = result['nodes'][1]['id']
                    self.assertEqual(routes.manage('select', dest)['selected'], dest)
                    self.assertEqual(routes.manage('select', first['selected']), result)
                self.assertEqual(json.loads(config.read_text())['outbounds'], [original])


if __name__ == '__main__':
    unittest.main()
