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
