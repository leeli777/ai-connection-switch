#!/usr/bin/env python3
"""Manage only the two applications' proxy settings and the local selector."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

HOME = Path.home()
BASE = HOME / 'Library/Application Support/AIConnectionSwitch'
CLAUDE = HOME / '.claude/settings.json'
CODEX = HOME / '.codex/.env'
LABEL = 'local.ai-connection-switch'
AGENT = HOME / f'Library/LaunchAgents/{LABEL}.plist'
ENTRY, CHECK, API = 1086, 1087, 19090
MODES = {'independent': 'own-vless', 'shadowrocket': 'shadowrocket-http'}
KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')
PROXY_LINE = re.compile(r'^\s*(?:export\s+)?(?:https?_proxy|all_proxy|no_proxy)\s*=', re.I)
MARKER = '# AI connection switch: managed proxy entries'


def atomic(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data.encode() if isinstance(data, str) else data)
            f.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def read_json(path):
    return json.loads(path.read_text())


def settings():
    d = read_json(CLAUDE) if CLAUDE.exists() else {}
    if not isinstance(d, dict) or not isinstance(d.get('env', {}), dict):
        raise RuntimeError('Claude 设置格式无法安全修改。')
    return d


def control():
    return read_json(BASE / 'control.json')


def proxy_url(port):
    return f'http://127.0.0.1:{port}'


def api(path='/proxies/ai-mode', mode=None):
    req = urllib.request.Request(
        proxy_url(API) + path, method='GET' if mode is None else 'PUT',
        data=None if mode is None else json.dumps({'name': mode}).encode(),
        headers={'Authorization': 'Bearer ' + control()['secret'], 'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3) as r:
        body = r.read()
    return json.loads(body) if body else {}


def proxy_parts(d, env):
    return {'claude': {k: v for k, v in d.get('env', {}).items() if k.upper() in KEYS},
            'codex': [line for line in env.splitlines() if PROXY_LINE.match(line)]}


def write_proxy_parts(d, env, parts):
    # Preserve other keys and lines, including any unrelated edits made since setup.
    e = {k: v for k, v in d.get('env', {}).items() if k.upper() not in KEYS}
    e.update(parts['claude'])
    if e or 'env' in d:
        d['env'] = e
    lines = [line for line in env.splitlines() if not PROXY_LINE.match(line) and line.strip() != MARKER]
    lines += ([MARKER] if parts.get('managed') else []) + parts['codex']
    paths = (CLAUDE, CODEX)
    if any(path.is_symlink() for path in paths):
        raise RuntimeError('检测到应用设置文件是符号链接，请先核对实际设置文件。')
    previous = {p: p.read_bytes() if p.exists() else None for p in paths}
    written = []
    try:
        for p, value in zip(paths, (json.dumps(d, ensure_ascii=False, indent=2) + '\n', '\n'.join(lines) + ('\n' if lines else ''))):
            atomic(p, value)
            written.append(p)
    except Exception:
        for p in reversed(written):
            if previous[p] is None:
                p.unlink()
            else:
                atomic(p, previous[p])
        raise


def write_app_entries(port):
    d, env = settings(), CODEX.read_text() if CODEX.exists() else ''
    journal_path = BASE / 'app-settings-backup.json'
    before = proxy_parts(d, env)
    journal = read_json(journal_path) if journal_path.exists() else {'before': before}
    if 'last' in journal and before != journal['last']:
        raise RuntimeError('AI 代理设置已在外部修改；为保护这些修改，未覆盖。')
    values = dict.fromkeys(KEYS, proxy_url(port))
    values['NO_PROXY'] = 'localhost,127.0.0.1,::1'
    after = {'claude': values, 'codex': [f'{k}={v}' for k, v in values.items()]}
    # Journal the original values before changing either app.
    if not journal_path.exists():
        atomic(journal_path, json.dumps(journal, ensure_ascii=False))
    write_proxy_parts(d, env, {**after, 'managed': True})
    atomic(journal_path, json.dumps({**journal, 'last': after}, ensure_ascii=False))


def restore():
    journal_path = BASE / 'app-settings-backup.json'
    if not journal_path.exists():
        return status()
    journal = read_json(journal_path)
    d, env = settings(), CODEX.read_text() if CODEX.exists() else ''
    if proxy_parts(d, env) != journal.get('last', journal['before']):
        raise RuntimeError('AI 代理设置已在外部修改；请核对后手动回退。')
    write_proxy_parts(d, env, journal['before'])
    journal_path.unlink()
    return {**status(), 'notice': '已恢复接入前的代理设置。请在任务空闲时正常重启 AI 应用。'}


def status():
    result = {'serviceAvailable': False, 'mode': 'unavailable', 'entry': 'other',
              'codexRestartRequired': True, 'claudeDesktop': 'unknown', 'claudeCode': 'unknown'}
    fallback = control()['shadowrocket_port']
    try:
        current = api()['now']
        result.update(serviceAvailable=True, mode=next((k for k, v in MODES.items() if v == current), 'unknown'))
    except (ValueError, OSError, KeyError):
        pass
    port = ENTRY
    url = settings().get('env', {}).get('HTTPS_PROXY')
    env = CODEX.read_text() if CODEX.exists() else ''
    journal = BASE / 'app-settings-backup.json'
    if journal.exists() and url in (proxy_url(ENTRY), proxy_url(fallback)) and f'HTTPS_PROXY={url}' in env.splitlines():
        if url == proxy_url(fallback):
            result.update(entry='emergency', mode='emergency')
            port = fallback
        else:
            result['entry'] = 'shared'
    result['proxyPort'] = port
    if result['entry'] == 'other' and result['serviceAvailable']:
        result['mode'] = 'unattached'
    try:
        apps = {'codex': set(), 'claudeDesktop': set(), 'claudeCode': set()}
        for row in subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True).splitlines():
            fields = row.strip().split(None, 1)
            if len(fields) != 2:
                continue
            pid, name = fields
            if name.startswith('/Applications/Claude.app/Contents/'):
                apps['claudeDesktop'].add(pid)
            if '/claude.app/Contents/MacOS/claude' in name or name.endswith('/.local/bin/claude') or name.startswith(str(HOME / '.local/share/claude/versions') + '/'):
                apps['claudeCode'].add(pid)
            if re.match(r'^/Applications/(ChatGPT|Codex)\.app/Contents/', name) and name.endswith('/codex'):
                apps['codex'].add(pid)
        sockets = subprocess.run(
            ['/usr/sbin/lsof', '-nP', f'-iTCP:{ENTRY}', f'-iTCP:{fallback}', '-sTCP:ESTABLISHED', '-Fpn'],
            capture_output=True, text=True, timeout=5).stdout
        pid, connections = None, {}
        for line in sockets.splitlines():
            if line.startswith('p'):
                pid = line[1:]
            if line.startswith('n') and pid:
                m = re.search(r'->127\.0\.0\.1:(\d+)$', line)
                if m:
                    connections.setdefault(pid, set()).add(int(m[1]))
        for name, pids in apps.items():
            ports = {p for pid in pids for p in connections.get(pid, ()) if p in (ENTRY, fallback)}
            state = 'closed' if not pids else 'waiting' if not ports else 'legacy'
            if port in ports and result['entry'] != 'other':
                state = 'connected' if len(ports) == 1 else 'mixed'
            if name == 'codex':
                result['codexRestartRequired'] = state != 'connected'
                result['codexState'] = state
            else:
                result[name] = state
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def health(port):
    if os.getloadavg()[0] > 8:
        return [{'target': '系统负载较高，暂缓检测', 'ok': False}]
    checks = []
    guard = BASE / 'memguard.py'
    for name, url in (('Claude', 'https://api.anthropic.com/v1/models'),
                      ('OpenAI', 'https://api.openai.com/v1/models')):
        p = subprocess.run([sys.executable, str(guard), '--max-gb', '3', '--timeout', '12', '--',
                            '/usr/bin/curl', '-q', '--silent', '--show-error', '--noproxy', '',
                            '--proxy', proxy_url(port), '--connect-timeout', '4', '--max-time', '8',
                            '--output', '/dev/null', '--write-out', '%{http_code}', url],
                           capture_output=True, text=True, timeout=15)
        checks.append({'target': name, 'ok': p.returncode == 0 and p.stdout == '401', 'http': p.stdout[-3:]})
    return checks


def switch(mode):
    if mode == 'independent' and not all(check['ok'] for check in health(CHECK)):
        raise RuntimeError('独立线路检查未通过，保留原设置。')
    if mode == 'shadowrocket' and not all(check['ok'] for check in health(control()['shadowrocket_port'])):
        raise RuntimeError('Shadowrocket 入口检查未通过，保留原设置。')
    previous = api()['now']
    if previous != MODES[mode]:
        api(mode=MODES[mode])
    try:
        if api()['now'] != MODES[mode]:
            raise RuntimeError('未确认线路切换。')
        write_app_entries(ENTRY)
    except Exception:
        if previous != MODES[mode]:
            api(mode=previous)
        raise
    return status()


def emergency():
    # Deliberately works even if the independent service has failed.
    write_app_entries(control()['shadowrocket_port'])
    return {**status(), 'notice': '已设置直接通过 Shadowrocket。任务空闲后，重新打开已运行的 AI 应用使设置生效。'}


def cli():
    command = sys.argv[1] if len(sys.argv) == 2 else 'status'
    if command == 'status':
        return status()
    if command == 'check':
        return {'checks': health(status()['proxyPort'])}
    with (BASE / 'switch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if command in MODES:
            return switch(command)
        if command == 'emergency':
            return emergency()
        if command == 'restore':
            return restore()
    raise RuntimeError('未知操作')


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, **cli()}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print(json.dumps({'ok': False, 'error': '无法读取本机配置或连接入口；请检查安装与权限。'}, ensure_ascii=False))
        sys.exit(1)
    except RuntimeError as e:
        print(json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)
