#!/usr/bin/env python3
"""Install the isolated user service and desktop switch, without migrating AI apps."""
import argparse
import base64
import getpass
import ipaddress
import json
import os
import platform
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit
import uuid
import warnings

import ai_switch_control as ctl

ROOT = Path(__file__).resolve().parent
APP_NAME = 'AI 连接开关.app'


def parse_vless(link, interface):
    u = urlsplit(link.strip())
    q = parse_qs(u.query, keep_blank_values=True, strict_parsing=True)
    if u.scheme != 'vless' or u.password is not None or u.path not in ('', '/') or any(len(v) != 1 for v in q.values()):
        raise ValueError()
    q = {k: v[0] for k, v in q.items()}
    if (q.get('security'), q.get('type', 'tcp'), q.get('flow'), q.get('encryption', 'none')) != ('reality', 'tcp', 'xtls-rprx-vision', 'none'):
        raise ValueError()
    if q.get('spx', '/') not in ('', '/') or q.get('headerType', 'none') != 'none' or q.keys() - {'security', 'type', 'flow', 'encryption', 'sni', 'pbk', 'sid', 'fp', 'spx', 'headerType'}:
        raise ValueError()
    address = str(ipaddress.IPv4Address(u.hostname))
    identity = str(uuid.UUID(u.username))
    if not u.port or not re.fullmatch(r'[a-zA-Z0-9.-]+', q['sni']):
        raise ValueError()
    key, sid = q['pbk'], q.get('sid', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', key) or len(base64.urlsafe_b64decode(key + '=')) != 32:
        raise ValueError()
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}){0,8}', sid):
        raise ValueError()
    return {'type': 'vless', 'tag': 'own-vless', 'server': address, 'server_port': u.port,
            'uuid': identity, 'flow': q['flow'], 'network': 'tcp', 'bind_interface': interface,
            'tls': {'enabled': True, 'server_name': q['sni'],
                    'utls': {'enabled': True, 'fingerprint': q.get('fp') or 'chrome'},
                    'reality': {'enabled': True, 'public_key': key, 'short_id': sid}}}


def make_config(node, secret, fallback, base, entry=ctl.ENTRY, check=ctl.CHECK, api=ctl.API):
    return {
        'log': {'level': 'error', 'timestamp': True},
        'inbounds': [
            {'type': 'http', 'tag': 'ai-local', 'listen': '127.0.0.1', 'listen_port': entry},
            {'type': 'http', 'tag': 'own-health', 'listen': '127.0.0.1', 'listen_port': check}],
        'outbounds': [
            {'type': 'selector', 'tag': 'ai-mode', 'outbounds': ['own-vless', 'shadowrocket-http'],
             'default': 'own-vless', 'interrupt_exist_connections': True},
            node, {'type': 'http', 'tag': 'shadowrocket-http', 'server': '127.0.0.1', 'server_port': fallback}],
        'route': {'rules': [{'inbound': ['own-health'], 'action': 'route', 'outbound': 'own-vless'}], 'final': 'ai-mode'},
        'experimental': {'clash_api': {'external_controller': f'127.0.0.1:{api}', 'secret': secret},
                         'cache_file': {'enabled': True, 'path': str(base / 'switch-cache.db')}}}


def command(args, failure, timeout=30):
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(failure)
    return p.stdout


def build_app(app):
    require_resources()
    exe = app / 'Contents/MacOS/AIConnectionSwitch'
    exe.parent.mkdir(parents=True)
    resources = app / 'Contents/Resources'
    resources.mkdir()
    shutil.copyfile(ROOT / 'assets/AppIcon.icns', resources / 'AppIcon.icns')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': ctl.LABEL, 'CFBundleName': 'AI 连接开关',
        'CFBundleExecutable': 'AIConnectionSwitch', 'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2',
        'CFBundleIconFile': 'AppIcon.icns', 'LSMinimumSystemVersion': '13.0',
        'NSHighResolutionCapable': True}))
    command([sys.executable, str(ROOT / 'memguard.py'), '--max-gb', '3', '--timeout', '150', '--',
             '/usr/bin/xcrun', 'swiftc', '-swift-version', '5', '-O',
             '-target', f'{os.uname().machine}-apple-macos13.0',
             '-framework', 'Cocoa', '-framework', 'SwiftUI',
             str(ROOT / 'AIConnectionSwitch.swift'), '-o', str(exe)],
            '无法编译桌面开关；请确认 Apple Command Line Tools 可用。', timeout=160)
    command(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], '无法签名桌面开关。')
    command(['/usr/bin/codesign', '--verify', '--strict', str(app)], '桌面开关签名验证失败。')


def require_resources():
    if os.getloadavg()[0] > 8:
        raise RuntimeError('1 分钟负载超过 8，等负载降低再运行。')
    from memguard import available_gb
    if available_gb() < 1.5:
        raise RuntimeError('可用内存不足 1.5 GB，等资源恢复再运行。')


def read_link(source):
    if source is None:
        if not sys.stdin.isatty():
            raise RuntimeError('请在 Terminal 私密输入节点链接，或指定权限为 600 的本机文件。')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                return getpass.getpass('粘贴自建 VPS 的 VLESS Reality 链接（输入隐藏）：')
            except getpass.GetPassWarning:
                raise RuntimeError('无法保证终端输入隐藏；请换用正常的 Terminal 窗口或本机私密文件。') from None
    source = source.expanduser()
    # No credentials from a clone, symlink, world-readable file, or shell argument.
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        st = os.fstat(f.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o077 or source.resolve().is_relative_to(ROOT)):
            raise RuntimeError('链接文件必须在仓库外、由当前用户拥有且权限为 600。')
        data = f.read(8193)
    if len(data) > 8192:
        raise RuntimeError('节点链接过长。')
    return data.decode()


def validate_ports(ports):
    sockets = []
    try:
        for port in ports:
            s = socket.socket()
            sockets.append(s)
            try:
                s.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'本机端口 {port} 已被占用；没有停止或覆盖现有服务。') from None
    finally:
        for s in sockets:
            s.close()


def install(args):
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise RuntimeError('请在 macOS 的已登录桌面用户下运行，勿用 sudo。')
    if sys.version_info < (3, 9):
        raise RuntimeError('需要 Python 3.9 或更新版本。')
    if int(platform.mac_ver()[0].split('.')[0]) < 13:
        raise RuntimeError('需要 macOS 13 或更新版本。')
    require_resources()
    if not re.fullmatch(r'en\d+', args.interface):
        raise RuntimeError('请使用实际联网的物理接口（如 en0），不能绑定 VPN 接口。')
    address = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', args.interface], capture_output=True)
    if address.returncode or not address.stdout.strip():
        raise RuntimeError('所选物理接口当前没有 IPv4 地址；请核对 Wi-Fi 或有线接口。')
    ports = (ctl.ENTRY, ctl.CHECK, ctl.API)
    if args.shadowrocket_port not in range(1, 65536) or args.shadowrocket_port in ports:
        raise RuntimeError('Shadowrocket HTTP 端口无效或和 AI 入口冲突。')
    validate_ports(ports)
    base, agent = ctl.BASE, ctl.AGENT
    app, desktop = ctl.HOME / 'Applications' / APP_NAME, ctl.HOME / 'Desktop' / APP_NAME
    if not desktop.parent.is_dir():
        raise RuntimeError('找不到当前用户的桌面文件夹。')
    if any(os.path.lexists(p) for p in (base, agent, app, desktop)):
        raise RuntimeError('检测到同名安装或文件；为保护现有连接，没有覆盖。')
    domain = f'gui/{os.getuid()}'
    command(['/bin/launchctl', 'print', domain], '需要登录到当前用户的 macOS 桌面。')
    if subprocess.run(['/bin/launchctl', 'print', f'{domain}/{ctl.LABEL}'], capture_output=True).returncode == 0:
        raise RuntimeError('同名后台服务已运行，未覆盖。')
    binary = args.sing_box or shutil.which('sing-box')
    if not binary or not Path(binary).expanduser().resolve().is_file():
        raise RuntimeError('找不到 sing-box；请按 README 安装，或通过 --sing-box 指定其可执行文件。')
    binary = Path(binary).expanduser().resolve()
    command([str(binary), 'version'], '无法运行 sing-box；请核对 CPU 架构及安装。')
    try:
        node = parse_vless(read_link(args.link_file), args.interface)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError('链接格式不受支持；需要 IPv4 VLESS + Reality + Vision/TCP 链接。') from None

    os.umask(0o077)
    owned = []
    bootstrapped = False
    try:
        base.parent.mkdir(parents=True, exist_ok=True)
        base.mkdir(mode=0o700)
        owned.append(base)
        secret = secrets.token_urlsafe(32)
        ctl.atomic(base / 'config.json', json.dumps(make_config(node, secret, args.shadowrocket_port, base)))
        ctl.atomic(base / 'control.json', json.dumps({'secret': secret, 'shadowrocket_port': args.shadowrocket_port}))
        for name in ('ai_switch_control.py', 'memguard.py', 'node_routes.py', 'Antigravity-CLI.command'):
            shutil.copyfile(ROOT / name, base / name)
        (base / 'Antigravity-CLI.command').chmod(0o700)
        # Keep the checked version independent of future Homebrew cleanup.
        shutil.copy2(binary, base / 'sing-box')
        command([str(base / 'sing-box'), 'check', '-c', str(base / 'config.json')],
                'sing-box 配置校验失败；请核对版本是否支持 Reality、接口绑定和 Clash API。')
        app.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ai-switch-build-', dir=app.parent) as temp:
            candidate = Path(temp) / APP_NAME
            build_app(candidate)
            if os.path.lexists(app):
                raise RuntimeError('应用目标已被占用。')
            candidate.rename(app)
        owned.append(app)
        agent.parent.mkdir(parents=True, exist_ok=True)
        with agent.open('xb') as f:
            owned.append(agent)
            plistlib.dump({
                'Label': ctl.LABEL,
                'ProgramArguments': [str(base / 'sing-box'), 'run', '-c', str(base / 'config.json')],
                'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
                'StandardErrorPath': str(base / 'service.log')}, f)
        command(['/bin/launchctl', 'bootstrap', domain, str(agent)], '无法启动 AI 专用后台服务。')
        bootstrapped = True
        for _ in range(20):
            try:
                if ctl.api()['now'] == 'own-vless':
                    break
            except (ValueError, OSError, KeyError):
                time.sleep(.25)
        else:
            raise RuntimeError('后台入口没有就绪。')
        checks = ctl.health(ctl.ENTRY)
        if not all(check['ok'] for check in checks):
            summary = '；'.join(f"{check['target']}: {check.get('http') or '未通过'}" for check in checks)
            raise RuntimeError(f'独立入口预检失败（{summary}）；未修改现有 AI 应用。')
        desktop.symlink_to(app, target_is_directory=True)
    except BaseException:
        if bootstrapped:
            stopped = subprocess.run(['/bin/launchctl', 'bootout', f'{domain}/{ctl.LABEL}'], capture_output=True)
            if stopped.returncode:
                raise RuntimeError('本安装的后台服务未能卸载；请先核对 README 中的回退步骤。') from None
        for path in reversed(owned):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        raise
    print('已安装桌面 AI 连接开关。Claude 和 OpenAI 的独立入口预检均通过；尚未改动现有 AI 应用。')
    print('打开开关，点“接入 AI 应用”，再在任务空闲时逐个重新打开。')


def update():
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise RuntimeError('请在已登录的 macOS 桌面用户下更新。')
    app = ctl.HOME / 'Applications' / APP_NAME
    info = app / 'Contents/Info.plist'
    helper = ctl.BASE / 'ai_switch_control.py'
    if (app.is_symlink() or not info.is_file() or
            plistlib.loads(info.read_bytes()).get('CFBundleIdentifier') != ctl.LABEL or
            not helper.is_file() or helper.is_symlink()):
        raise RuntimeError('没有找到本项目的旧版安装。请参照 README 安装，或保留已有的其他开关。')
    with (ctl.BASE / 'switch.lock').open('a') as lock:
        ctl.fcntl.flock(lock, ctl.fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix='ai-switch-update-', dir=app.parent) as temp:
            candidate = Path(temp) / APP_NAME
            old_app = Path(temp) / 'previous.app'
            build_app(candidate)
            app.rename(old_app)
            try:
                candidate.rename(app)
                for name in ('node_routes.py', 'Antigravity-CLI.command'):
                    ctl.atomic(ctl.BASE / name, (ROOT / name).read_bytes())
                (ctl.BASE / 'Antigravity-CLI.command').chmod(0o700)
                ctl.atomic(helper, (ROOT / 'ai_switch_control.py').read_bytes())
            except BaseException:
                if app.exists():
                    app.rename(candidate)
                old_app.rename(app)
                raise
    print('桌面开关已更新。若窗口已打开，退出开关后重新打开即可。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', help='实际联网的 Wi-Fi/有线接口，例如 en0')
    parser.add_argument('--sing-box', help='已安装的 sing-box 可执行文件路径')
    parser.add_argument('--shadowrocket-port', type=int, default=1082, help='本机 Shadowrocket HTTP 端口')
    parser.add_argument('--link-file', type=Path, help='可选，仓库外权限为 600 的私密链接文件')
    parser.add_argument('--update', action='store_true', help='更新已安装的开关和控制程序')
    args = parser.parse_args()
    if not args.update and not args.interface:
        parser.error('新安装需要 --interface')
    try:
        if args.update:
            update()
        else:
            install(args)
    except (RuntimeError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, RuntimeError) else '安装没有完成；请检查权限、依赖或超时。', file=sys.stderr)
        sys.exit(1)
