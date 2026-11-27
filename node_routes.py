"""Local node library. Share links enter on stdin and never appear in output."""
import base64
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import parse_qsl, unquote, urlsplit

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'config.json'
LIBRARY = BASE / 'nodes.json'
TAG = 'own-vless'


class NodeError(Exception):
    pass


def write_private(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def decode64(value):
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True).decode()


def parse(link, interface):
    u = urlsplit(link.strip())
    pairs = parse_qsl(u.query, keep_blank_values=True)
    q = dict(pairs)
    encoded = u.scheme in ('ss', 'vless', 'trojan') and '@' not in u.netloc
    if len(q) != len(pairs) or (not encoded and u.path not in ('', '/')):
        raise NodeError('链接含重复参数或不支持的路径。')
    kind = {'hy2': 'hysteria2', 'ss': 'shadowsocks'}.get(u.scheme, u.scheme)
    if kind not in ('vless', 'hysteria2', 'trojan', 'shadowsocks'):
        raise NodeError('请选择 VLESS、Hysteria2、Trojan 或 Shadowsocks 的单节点分享链接。')
    name = unquote(u.fragment) or q.pop('remarks', '') or kind
    q.pop('remarks', None)
    if encoded:
        auth, addr = decode64(u.netloc + u.path).rsplit('@', 1)
        u = urlsplit(u.scheme + '://' + addr)
        if kind == 'vless' and ':' in auth:
            cipher, auth = auth.split(':', 1)
            if cipher not in ('auto', 'none'):
                raise NodeError('不支持此 VLESS 加密方式。')
    else:
        auth = unquote(u.netloc.rsplit('@', 1)[0]) if '@' in u.netloc else ''
    if not auth or not u.hostname or not u.port:
        raise NodeError('缺少节点地址、端口或认证信息。')
    node = dict(type=kind, tag=TAG, server=u.hostname, server_port=u.port, bind_interface=interface)
    if kind in ('vless', 'trojan'):
        if 'tls' in q:
            flag = q.pop('tls')
            if flag not in ('0', '1'):
                raise NodeError('不支持此 TLS 设置。')
            q.setdefault('security', 'reality' if 'pbk' in q else ('tls' if flag == '1' else 'none'))
        if 'xtls' in q:
            q['flow'] = {'0': '', '2': 'xtls-rprx-vision'}[q.pop('xtls')]
        if 'obfs' in q:
            transport = q.pop('obfs')
            q['type'] = {'none': 'tcp', 'websocket': 'ws'}.get(transport, transport)
        if q.get('type') == 'grpc' and 'path' in q:
            q['serviceName'] = q.pop('path').lstrip('/')
        if 'obfsParam' in q:
            host = q.pop('obfsParam')
            if host:
                q['host'] = host
    if kind == 'shadowsocks':
        if ':' not in auth:
            auth = decode64(auth)
        node['method'], node['password'] = auth.split(':', 1)
    else:
        if kind == 'vless':
            node['uuid'] = str(uuid.UUID(auth))
            if q.pop('encryption', 'none') != 'none':
                raise NodeError('不支持此 VLESS 加密方式。')
            flow = q.pop('flow', '')
            if flow:
                node['flow'] = flow
        else:
            node['password'] = auth
        security = q.pop('security', 'none' if kind == 'vless' else 'tls')
        if security == 'none' and kind != 'vless' or security not in ('none', 'tls', 'reality'):
            raise NodeError('不支持此 TLS 设置。')
        if security != 'none':
            tls = {'enabled': True}
            for key in ('peer', 'sni'):
                if key in q:
                    tls['server_name'] = q.pop(key)
            if 'alpn' in q:
                tls['alpn'] = q.pop('alpn').split(',')
            fp = q.pop('fp', '')
            if fp:
                tls['utls'] = {'enabled': True, 'fingerprint': fp}
            if security == 'reality':
                tls['reality'] = {'enabled': True, 'public_key': q.pop('pbk'), 'short_id': q.pop('sid', '')}
                tls.setdefault('utls', {'enabled': True, 'fingerprint': 'chrome'})
                if q.pop('spx', '/') not in ('/', ''):
                    raise NodeError('不支持此 Reality 路径。')
            for key in ('insecure', 'allowInsecure'):
                if key in q:
                    value = q.pop(key).lower()
                    if value not in ('0', '1', 'true', 'false'):
                        raise NodeError('证书校验参数无效。')
                    tls['insecure'] = value in ('1', 'true')
            node['tls'] = tls
        if kind == 'hysteria2':
            for key in ('upmbps', 'downmbps'):
                if key in q:
                    node[key.replace('mbps', '_mbps')] = int(q.pop(key))
            obfs = q.pop('obfs', 'none')
            if obfs != 'none':
                node['obfs'] = {'type': obfs, 'password': q.pop('obfs-password')}
        else:
            transport = q.pop('type', 'tcp')
            if transport == 'ws':
                ws = {'type': 'ws', 'path': q.pop('path', '/')}
                if 'host' in q:
                    ws['headers'] = {'Host': q.pop('host')}
                node['transport'] = ws
            elif transport == 'grpc':
                node['transport'] = {'type': 'grpc', 'service_name': q.pop('serviceName', '')}
            elif transport != 'tcp':
                raise NodeError('不支持此传输方式。')
            if q.pop('headerType', 'none') != 'none':
                raise NodeError('不支持此 TCP 伪装。')
    if q:
        raise NodeError('链接含未支持的选项，未导入。')
    return name[:100], node


def activate(config, original):
    import ai_switch_control as ctl
    label = ctl.AGENT.stem
    job = f'gui/{os.getuid()}/{label}'
    check_port = next(item['listen_port'] for item in json.loads(config)['inbounds'] if item['tag'] == 'own-health')

    def reload(data):
        write_private(CONFIG, data)
        subprocess.run(['launchctl', 'kickstart', '-k', job], check=True, capture_output=True)
        for _ in range(30):
            try:
                ctl.api('/proxies/ai-mode')
                return
            except OSError:
                time.sleep(.2)
        raise NodeError('后台服务未就绪。')

    try:
        reload(config)
        probe = subprocess.run(['curl', '--silent', '--noproxy', '', '--proxy', f'http://127.0.0.1:{check_port}',
                                '--max-time', '15', '--output', '/dev/null', '--write-out', '%{http_code}',
                                'https://www.google.com/generate_204'], capture_output=True)
        if probe.returncode or probe.stdout != b'204':
            raise NodeError('新线路连接检查失败。')
    except Exception:
        try:
            reload(original)
        except Exception:
            raise NodeError('切换失败，原配置恢复时服务未就绪，请检查后台服务。')
        raise NodeError('切换失败，已恢复原配置。')


def manage(action, arg=''):
    with (BASE / 'switch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = CONFIG.read_bytes()
        cfg = json.loads(original)
        active = next(n for n in cfg['outbounds'] if n['tag'] == TAG)
        nodes = json.loads(LIBRARY.read_text()) if LIBRARY.exists() else []
        def add(name, node):
            if all(n['config'] != node for n in nodes):
                nodes.append(dict(id=uuid.uuid4().hex, name=name, config=node))
        add('原有独立线路', active)
        if action == 'import':
            name, node = parse(arg, active['bind_interface'])
            checked = subprocess.run([str(BASE / 'sing-box'), 'check', '-c', 'stdin'],
                                     input=json.dumps({'outbounds': [node]}).encode(), capture_output=True)
            if checked.returncode:
                raise NodeError('本机代理内核不支持该节点配置。')
            add(name, node)
        elif action == 'select':
            selected = next(n for n in nodes if n['id'] == arg)['config']
            if selected != active:
                cfg['outbounds'][cfg['outbounds'].index(active)] = selected
                activate(json.dumps(cfg).encode(), original)
                active = selected
        elif action != 'list':
            raise NodeError('未知操作。')
        data = json.dumps(nodes, ensure_ascii=False).encode()
        if not LIBRARY.exists() or LIBRARY.read_bytes() != data:
            write_private(LIBRARY, data)
        return {'ok': True, 'nodes': [{'id': n['id'], 'name': n['name']} for n in nodes],
                'selected': next(n['id'] for n in nodes if n['config'] == active)}


if __name__ == '__main__':
    try:
        result = manage(sys.argv[1], sys.stdin.read(16385).strip())
    except NodeError as e:
        result = {'ok': False, 'error': str(e)}
    except Exception:
        result = {'ok': False, 'error': '操作未完成，请检查节点格式、线路或后台服务。'}
    print(json.dumps(result))
