import Cocoa
import SwiftUI

let connectionAppIcon: NSImage = {
    if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"), let image = NSImage(contentsOf: url) { return image }
    return NSImage(systemSymbolName: "arrow.triangle.2.circlepath.circle.fill", accessibilityDescription: "AI 连接开关") ?? NSImage(size: NSSize(width: 64, height: 64))
}()

enum AITarget {
    case codex, claude, gemini

    var title: String {
        switch self {
        case .codex: return "Codex"
        case .claude: return "Claude"
        case .gemini: return "Gemini"
        }
    }
    var paths: [String] {
        switch self {
        case .codex: return ["/Applications/Codex.app", "/Applications/ChatGPT.app"]
        case .claude: return ["/Applications/Claude.app"]
        case .gemini: return ["/Applications/Gemini.app"]
        }
    }
    var path: String? {
        let verified = paths.filter { Bundle(path: $0)?.bundleIdentifier == identifier }
        let active = NSRunningApplication.runningApplications(withBundleIdentifier: identifier)
        return verified.first { path in active.contains { $0.bundleURL?.standardizedFileURL.path == path } } ?? verified.first
    }
    var identifier: String {
        switch self {
        case .codex: return "com.openai.codex"
        case .claude: return "com.anthropic.claudefordesktop"
        case .gemini: return "com.google.GeminiMacOS"
        }
    }
    func running(at path: String) -> [NSRunningApplication] {
        NSRunningApplication.runningApplications(withBundleIdentifier: identifier).filter { $0.bundleURL?.standardizedFileURL.path == path }
    }
}

final class SwitchModel: ObservableObject {
    @Published var mode = "unavailable"
    @Published var busy = false
    @Published var message = "正在读取连接状态…"
    @Published var codexState = "unknown"
    @Published var proxyPort = 1086
    @Published var claudeDesktop = "unknown"
    @Published var claudeCode = "unknown"
    @Published var geminiDesktop = "unknown"
    @Published var antigravityAgent = "unknown"
    let helper = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/AIConnectionSwitch/ai_switch_control.py").path
    func run(_ action: String, notice: String? = nil) {
        guard !busy else { return }
        busy = true
        message = action == "status" ? "正在读取状态…" : "正在处理，请稍候…"
        DispatchQueue.global(qos: .userInitiated).async {
            let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            p.arguments = [self.helper, action]
            let pipe = Pipe(); p.standardOutput = pipe; p.standardError = Pipe()
            var result: [String: Any] = [:]
            do {
                try p.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
                result = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? ["ok": false, "error": "无法读取状态。可使用紧急恢复。"]
            } catch { result = ["ok": false, "error": "无法启动控制程序。"] }
            DispatchQueue.main.async {
                self.busy = false
                if result["ok"] as? Bool == true {
                    if let m = result["mode"] as? String { self.mode = m }
                    if let n = result["codexState"] as? String { self.codexState = n }
                    if let n = result["proxyPort"] as? Int { self.proxyPort = n }
                    if let n = result["claudeDesktop"] as? String { self.claudeDesktop = n }
                    if let n = result["claudeCode"] as? String { self.claudeCode = n }
                    if let n = result["geminiDesktop"] as? String { self.geminiDesktop = n }
                    if let n = result["antigravityAgent"] as? String { self.antigravityAgent = n }
                    if let checks = result["checks"] as? [[String: Any]] {
                        self.message = checks.map { ($0["target"] as? String ?? "AI") + (($0["ok"] as? Bool == true) ? "：可连接" : "：暂未通过") }.joined(separator: "   ")
                    } else {
                        self.message = notice ?? (result["notice"] as? String) ?? (action == "status" ? "已读取实际入口状态。" : "已切换。AI 会短暂重连，VPN 开关未改动。")
                    }
                } else { self.message = result["error"] as? String ?? "操作未完成。可使用紧急恢复。" }
            }
        }
    }
    var canOpenAIApps: Bool { ["independent", "shadowrocket", "emergency"].contains(mode) }

    func restartApp(_ target: AITarget) {
        guard canOpenAIApps else {
            message = "AI 入口未就绪。请先刷新状态，或使用紧急恢复。"; return
        }
        guard let path = target.path else {
            message = "未在 /Applications 找到可识别的 \(target.title) 客户端。"; return
        }
        let alert = NSAlert()
        alert.messageText = "重新打开 \(target.title)，使代理入口生效？"
        alert.informativeText = "这会暂停 \(target.title) 中正在运行的任务。请先保存工作，并确认会话已空闲。VPN 和另一个 AI 应用不会被关闭。"
        if target == .gemini {
            alert.informativeText = "请确认 Gemini 和 Antigravity 的任务已完成。重开后可在 Gemini 内继续使用 Antigravity。"
        }
        alert.addButton(withTitle: "重启并迁移")
        alert.addButton(withTitle: "暂不重启")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let port = proxyPort
        busy = true; message = "正在等待 \(target.title) 正常退出…"
        let apps = target.running(at: path)
        for app in apps { _ = app.terminate() }
        let start = Date()
        Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { timer in
            if !target.running(at: path).isEmpty {
                if Date().timeIntervalSince(start) > 25 {
                    timer.invalidate(); self.busy = false
                    self.message = "\(target.title) 尚未退出。请处理应用内提示后重试；没有强制结束任务。"
                }
                return
            }
            timer.invalidate()
            let config = NSWorkspace.OpenConfiguration()
            var env = ProcessInfo.processInfo.environment
            for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"] { env.removeValue(forKey: k) }
            let url = "http://127.0.0.1:\(port)"
            env["HTTP_PROXY"] = url; env["HTTPS_PROXY"] = url; env["ALL_PROXY"] = url
            env["NO_PROXY"] = "localhost,127.0.0.1,::1"
            if target == .gemini {
                env["http_proxy"] = url; env["https_proxy"] = url; env["all_proxy"] = url
                env["no_proxy"] = env["NO_PROXY"]
            } else {
                config.arguments = ["--proxy-server=\(url)"]
            }
            config.environment = env
            config.activates = true
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: path), configuration: config) { app, error in
                DispatchQueue.main.async {
                    self.busy = false
                    if error == nil, app?.bundleURL?.standardizedFileURL.path == path {
                        self.run("status", notice: "\(target.title) 已打开。请发一条消息，再点刷新确认实际通路。")
                    } else { self.message = "无法重新打开 \(target.title)。如有另一份同名应用，请先退出那一份再试。" }
                }
            }
        }
    }

}

struct SwitchView: View {
    @ObservedObject var model: SwitchModel
    var label: String {
        switch model.mode {
        case "independent": return "独立连接 · 自建 VPS"
        case "shadowrocket": return "通过 Shadowrocket"
        case "emergency": return "紧急回退 · Shadowrocket"
        case "unattached": return "已安装 · 尚未接入 AI 应用"
        default: return "入口暂不可用"
        }
    }
    func routeLabel(_ state: String) -> String {
        switch state {
        case "connected": return "已接入"
        case "legacy": return "仍走旧入口"
        case "external": return "有外部连接，未观察到代理"
        case "mixed": return "新旧入口混用"
        case "closed": return "未打开"
        case "waiting": return "等待发送消息验证"
        default: return "待检查"
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                Image(nsImage: connectionAppIcon).resizable().interpolation(.high).frame(width: 46, height: 46)
                VStack(alignment: .leading, spacing: 4) {
                    Text("AI 连接开关").font(.title2).bold()
                    Text("只控制 AI 代理，不操作 VPN 开关").foregroundColor(.secondary)
                }
            }
            Divider()
            Text("当前：\(label)").font(.headline)
            if model.mode == "unattached" {
                Button("接入 AI 应用") { model.run("independent") }.disabled(model.busy)
            } else {
                Toggle("AI 使用独立连接", isOn: Binding(get: { model.mode == "independent" }, set: { model.run($0 ? "independent" : "shadowrocket") }))
                    .toggleStyle(.switch).disabled(model.busy || model.mode == "unavailable")
            }
            Text("开启：直接连接你的 VPS。\n关闭：AI 经现有 Shadowrocket 转发。两种方式都不切换 VPN 节点。")
                .font(.callout).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("检查连接") { model.run("check") }
                Button("刷新状态") { model.run("status") }
                Spacer()
                if model.busy { ProgressView().controlSize(.small) }
            }.disabled(model.busy)
            Text(model.message).font(.callout).frame(minHeight: 36, alignment: .topLeading).fixedSize(horizontal: false, vertical: true)
            Divider()
            HStack {
                Button("紧急恢复 Shadowrocket") { model.run("emergency") }.disabled(model.busy)
                Spacer()
                Button("重启并接入 Codex…") { model.restartApp(.codex) }.disabled(model.busy || !model.canOpenAIApps)
                Button("重启并接入 Claude…") { model.restartApp(.claude) }.disabled(model.busy || !model.canOpenAIApps)
            }
            HStack {
                Button("重启并接入 Gemini…") { model.restartApp(.gemini) }
                Spacer()
            }.disabled(model.busy || !model.canOpenAIApps)
            Text("Gemini：\(routeLabel(model.geminiDesktop))   Antigravity：\(routeLabel(model.antigravityAgent))")
                .font(.caption).foregroundColor(.secondary)
            Text("Codex：\(routeLabel(model.codexState))   Claude 桌面：\(routeLabel(model.claudeDesktop))   Code：\(routeLabel(model.claudeCode))")
                .font(.caption).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(26).frame(width: 520)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let model = SwitchModel()
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.applicationIconImage = connectionAppIcon
        let menu = NSMenu(); let item = NSMenuItem(); menu.addItem(item)
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "退出 AI 连接开关", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        item.submenu = appMenu; NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 572, height: 547), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "AI 连接开关"
        window.contentView = NSHostingView(rootView: SwitchView(model: model))
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        model.run("status")
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
let app = NSApplication.shared
let delegate = AppDelegate(); app.delegate = delegate
app.run()
