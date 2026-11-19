#!/usr/bin/env python3
"""Isolated smoke test: temporary files, loopback ports and a synthetic node only."""
import base64
import json
import plistlib
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_switch_control as ctl
import install
from install import build_app, make_config, parse_vless


def main(binary):
    with tempfile.TemporaryDirectory(prefix='ai-switch-smoke-') as temp:
        home = Path(temp)
        ctl.HOME = home
        ctl.BASE = home / 'service'
        ctl.CLAUDE = home / '.claude/settings.json'
        ctl.CODEX = home / '.codex/.env'
        ctl.BASE.mkdir(mode=0o700)
        sockets = [socket.socket() for _ in range(4)]
        try:
            for s in sockets:
                s.bind(('127.0.0.1', 0))
            ctl.ENTRY, ctl.CHECK, ctl.API, fallback = [s.getsockname()[1] for s in sockets]
        finally:
            for s in sockets:
                s.close()

        example = (f'vless://{uuid.uuid4()}@192.0.2.42:443?security=reality&type=tcp&flow=xtls-rprx-vision'
                   f'&sni=example.com&pbk={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")}&sid=12')
        node = parse_vless(example, 'en0')
        assert node['server'] == '192.0.2.42' and node['tls']['reality']['short_id'] == '12'
        for invalid in (example.replace('type=tcp', 'type=ws'), example.replace('192.0.2.42', 'example.com'), example + '&sid=34'):
            try:
                parse_vless(invalid, 'en0')
            except ValueError:
                pass
            else:
                raise AssertionError('unexpectedly accepted unsupported node')

        secret = secrets.token_urlsafe(32)
        config_path = ctl.BASE / 'config.json'
        config = make_config(node, secret, fallback, ctl.BASE, ctl.ENTRY, ctl.CHECK, ctl.API)
        ctl.atomic(config_path, json.dumps(config))
        ctl.atomic(ctl.BASE / 'control.json', json.dumps({'secret': secret, 'shadowrocket_port': fallback}))
        assert (config_path.stat().st_mode & 0o777) == 0o600
        subprocess.run([binary, 'check', '-c', str(config_path)], check=True, timeout=15)
        print('PASS: synthetic Reality link and real sing-box config validation', flush=True)

        ctl.atomic(ctl.CLAUDE, json.dumps({'theme': 'keep', 'env': {'HTTPS_PROXY': 'original', 'OTHER': 'keep'}}))
        ctl.atomic(ctl.CODEX, 'OTHER=keep\nhttps_proxy=original\n')
        ctl.health = lambda port: [{'ok': port in (ctl.CHECK, fallback)}]
        with subprocess.Popen([binary, 'run', '-c', str(config_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as core:
            try:
                for _ in range(24):
                    try:
                        assert ctl.api()['now'] == 'own-vless'
                        break
                    except OSError:
                        time.sleep(.25)
                else:
                    raise AssertionError('core not ready')
                assert ctl.status()['entry'] == 'other'
                assert ctl.switch('independent')['entry'] == 'shared'
                assert ctl.switch('shadowrocket')['mode'] == 'shadowrocket'
                assert ctl.switch('independent')['mode'] == 'independent'
            finally:
                core.terminate()
                core.wait(timeout=10)
        # Verify app-only fallback works without the helper core.
        assert ctl.emergency()['entry'] == 'emergency'
        assert ctl.settings()['env']['HTTPS_PROXY'] == ctl.proxy_url(fallback)
        d = ctl.settings()
        d['theme'] = 'keep changed'
        ctl.atomic(ctl.CLAUDE, json.dumps(d))
        assert ctl.restore()['entry'] == 'other'
        assert ctl.settings() == {'theme': 'keep changed', 'env': {'HTTPS_PROXY': 'original', 'OTHER': 'keep'}}
        assert ctl.CODEX.read_text() == 'OTHER=keep\nhttps_proxy=original\n'
        print('PASS: live selector transitions, offline fallback, targeted settings restore', flush=True)

        app = home / 'AI 连接开关.app'
        build_app(app)
        assert (app / 'Contents/Resources/AppIcon.icns').is_file()
        print('PASS: macOS app builds, icon included, signature verifies', flush=True)

        # Exercise the upgrade against an existing installation, reusing the signed build.
        installed_app = home / 'Applications' / install.APP_NAME
        info = installed_app / 'Contents/Info.plist'
        info.parent.mkdir(parents=True)
        info.write_bytes(plistlib.dumps({'CFBundleIdentifier': ctl.LABEL, 'CFBundleVersion': '1'}))
        shortcut = home / 'Desktop' / install.APP_NAME
        shortcut.parent.mkdir()
        shortcut.symlink_to(installed_app)
        helper = ctl.BASE / 'ai_switch_control.py'
        helper.write_text('previous helper')
        config_before = config_path.read_bytes()
        with patch.object(install, 'build_app', side_effect=lambda candidate: shutil.copytree(app, candidate)):
            install.update()
        assert plistlib.loads(info.read_bytes())['CFBundleVersion'] == '2'
        assert helper.read_bytes() == (install.ROOT / helper.name).read_bytes()
        assert shortcut.resolve() == installed_app.resolve()
        assert config_path.read_bytes() == config_before
        print('PASS: upgrade retains the existing proxy configuration and desktop shortcut', flush=True)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) == 2 else shutil.which('sing-box'))
