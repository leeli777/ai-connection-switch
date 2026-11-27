# 验证记录

在 Apple Silicon、macOS 26.5.2、系统 Python 3.9.6 和 sing-box 1.14.4 上验证：

- 在临时回环端口和测试设置目录中检查 VLESS 导入和 sing-box 配置，切换两种线路，关闭测试代理后执行紧急回退，再恢复原应用设置。无关设置保留。
- 编译桌面应用、检查图标资源及本机签名。用真实自建 VLESS 节点执行隔离安装，验证用户级后台服务、桌面快捷方式及两项 API 探测。两项 API 均返回预期的 HTTP 401，随后卸载测试后台服务。
- 测试覆盖安装和代理切换逻辑。公开版的实际应用接入仍需按 README 在目标机验收。其他 macOS 版本和 Intel 机型尚未实测。

用自己的 sing-box 路径重跑隔离测试。测试本身使用合成节点，无需真实凭据：

```sh
uptime
/usr/bin/python3 memguard.py --max-gb 3 --timeout 210 -- \
  /usr/bin/python3 tests/smoke.py /path/to/sing-box
```

## Gemini 桌面

本机确认 Antigravity 由 Gemini macOS 应用内的 `agy` 子进程运行。开关验证分别识别桌面应用和 Agent 的实际连接，并完成签名与隔离升级测试。检测时 Antigravity 有任务正在执行，已保留该会话，实际迁移留待任务空闲后验收。

## Antigravity and imported routes

Verified the signed desktop build and upgrade with the existing smoke test. The node-library regression test passed for VLESS (standard and Shadowrocket Base64), Hysteria2, Trojan and Shadowsocks, including duplicate imports and preserving the active node. A disposable launchd instance activated a working upstream, returned HTTP 204 through its dedicated listener, and restored the previous running configuration after a different upstream failed. The installed Antigravity desktop network helper and language server were observed connected to the dedicated listener. No chat content was used for validation.
