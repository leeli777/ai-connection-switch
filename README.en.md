# AI Connection Switch for macOS

A desktop switch for routing Claude Desktop, Claude Code, Codex and Gemini through your own VLESS Reality server or an existing Shadowrocket HTTP proxy. It manages the AI apps' proxy settings and leaves system-wide network settings untouched. The desktop interface is in Simplified Chinese.

## Get started

1. Install Apple Command Line Tools and a [compatible sing-box build](https://sing-box.sagernet.org/installation/package-manager/). You need macOS 13+, Python 3.9+ and an IPv4 VLESS Reality link with XTLS Vision over TCP.
2. Identify the network interface currently online (`/usr/sbin/networksetup -listallhardwareports`) and the optional Shadowrocket local HTTP port.
3. Run the installer from Terminal. It prompts for the link with input hidden and tests API reachability before placing the app on the desktop.

   ```sh
   git clone https://github.com/leeli777/ai-connection-switch.git
   cd ai-connection-switch
   /usr/bin/python3 install.py --interface en0 --shadowrocket-port 1082
   ```

4. Open **AI 连接开关** (AI Connection Switch) and select **接入 AI 应用** (Connect AI apps). When your sessions are idle, use the respective restart buttons to reopen Claude Desktop and Codex. Reopen Claude Desktop from the switch after a full quit to keep its proxy launch arguments.
5. Send a short message in each app you use and click **刷新状态** (Refresh). Check for both a reply and an observed connection to the local proxy at port 1086.

**紧急恢复 Shadowrocket** sets a direct Shadowrocket fallback even when the standalone proxy is down. The fallback requires a working Shadowrocket HTTP port. For the original app settings and uninstall steps, see [the main README](README.md#回退与卸载). See [validation](VALIDATION.md) for the tested scope and [LICENSE](LICENSE) for licensing.

## Gemini Desktop and Antigravity

Use **重启并接入 Gemini…** (Restart and connect Gemini) when the app is idle. This launches the official macOS Gemini app with a proxy for the new process and its children. Open Antigravity inside Gemini as usual. Run a short task, then refresh the switch to see observed Gemini and Antigravity proxy connections separately.

To update an existing installation, pull the latest source, run `/usr/bin/python3 install.py --update` and reopen the switch.
