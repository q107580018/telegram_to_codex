import AppKit

final class StatusDotView: NSView {
    private let circle = NSView()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        circle.wantsLayer = true
        circle.layer?.cornerRadius = 7
        addSubview(circle)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layout() {
        super.layout()
        circle.frame = NSRect(x: 0, y: 0, width: 14, height: 14)
    }

    func setColor(_ color: NSColor) {
        circle.layer?.backgroundColor = color.cgColor
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let projectPath = "/Users/mac/Documents/test"

    private var window: NSWindow!
    private let statusDot = StatusDotView(frame: NSRect(x: 0, y: 0, width: 14, height: 14))
    private let statusLabel = NSTextField(labelWithString: "状态：检查中...")
    private let detailLabel = NSTextField(labelWithString: "")

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildUI()
        refreshStatus()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        _ = runShell("cd \(q(projectPath)) && ./stop.sh >/dev/null 2>&1 || true")
    }

    private func buildUI() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 300),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Telegram Bot 控制器"
        window.center()
        window.isReleasedWhenClosed = false
        window.delegate = self

        let content = NSView(frame: window.contentView!.bounds)
        content.autoresizingMask = [.width, .height]
        window.contentView = content

        let title = NSTextField(labelWithString: "Telegram Bot 控制器")
        title.font = NSFont.systemFont(ofSize: 22, weight: .semibold)
        title.frame = NSRect(x: 24, y: 245, width: 300, height: 30)
        content.addSubview(title)

        statusDot.frame = NSRect(x: 26, y: 212, width: 14, height: 14)
        content.addSubview(statusDot)

        statusLabel.font = NSFont.systemFont(ofSize: 16, weight: .medium)
        statusLabel.frame = NSRect(x: 48, y: 206, width: 320, height: 24)
        content.addSubview(statusLabel)

        detailLabel.font = NSFont.systemFont(ofSize: 12)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.frame = NSRect(x: 24, y: 182, width: 470, height: 18)
        detailLabel.lineBreakMode = .byTruncatingMiddle
        detailLabel.stringValue = "项目路径：\(projectPath)"
        content.addSubview(detailLabel)

        let startBtn = makeButton(title: "启动", action: #selector(startTapped))
        startBtn.frame = NSRect(x: 24, y: 125, width: 120, height: 36)
        content.addSubview(startBtn)

        let stopBtn = makeButton(title: "停止", action: #selector(stopTapped))
        stopBtn.frame = NSRect(x: 156, y: 125, width: 120, height: 36)
        content.addSubview(stopBtn)

        let opBtn = makeButton(title: "操作", action: #selector(opTapped))
        opBtn.frame = NSRect(x: 288, y: 125, width: 120, height: 36)
        content.addSubview(opBtn)

        let hint = NSTextField(labelWithString: "关闭窗口会自动停止 bot")
        hint.font = NSFont.systemFont(ofSize: 12)
        hint.textColor = .secondaryLabelColor
        hint.frame = NSRect(x: 24, y: 28, width: 220, height: 16)
        content.addSubview(hint)

        window.makeKeyAndOrderFront(nil)
    }

    private func makeButton(title: String, action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.bezelStyle = .rounded
        button.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        return button
    }

    @objc private func startTapped() {
        setPendingUI("启动中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let cmd = "cd \(self.q(self.projectPath)) && if [ -f bot.pid ]; then oldpid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$oldpid\" ] && ps -p \"$oldpid\" >/dev/null 2>&1; then echo already_running; exit 0; fi; fi; nohup \(self.q(self.projectPath + "/.venv/bin/python")) \(self.q(self.projectPath + "/bot.py")) >> bot.log 2>&1 & newpid=$!; echo $newpid > bot.pid; sleep 1; if ps -p \"$newpid\" >/dev/null 2>&1; then echo started; else echo failed; fi"
            let out = self.runShell(cmd)
            DispatchQueue.main.async {
                self.refreshStatus(message: "启动结果：\(out.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }
    }

    @objc private func stopTapped() {
        setPendingUI("停止中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let out = self.runShell("cd \(self.q(self.projectPath)) && ./stop.sh 2>&1 || true")
            DispatchQueue.main.async {
                self.refreshStatus(message: out.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }
    }

    @objc private func opTapped() {
        let menu = NSMenu()
        menu.addItem(withTitle: "刷新状态", action: #selector(refreshMenuTapped), keyEquivalent: "")
        menu.addItem(withTitle: "查看日志", action: #selector(openLogTapped), keyEquivalent: "")

        let button = NSApp.keyWindow?.firstResponder as? NSButton
        let point = NSPoint(x: 288, y: 120)
        menu.popUp(positioning: nil, at: point, in: window.contentView)
        _ = button
    }

    @objc private func refreshMenuTapped() {
        refreshStatus()
    }

    @objc private func openLogTapped() {
        let logPath = projectPath + "/bot.log"
        NSWorkspace.shared.open(URL(fileURLWithPath: logPath))
    }

    private func setPendingUI(_ text: String) {
        statusDot.setColor(.systemOrange)
        statusLabel.stringValue = "状态：\(text)"
    }

    private func refreshStatus(message: String? = nil) {
        let running = isBotRunning()
        if running {
            statusDot.setColor(.systemGreen)
            statusLabel.stringValue = "状态：运行中"
        } else {
            statusDot.setColor(.systemRed)
            statusLabel.stringValue = "状态：已停止"
        }
        if let message, !message.isEmpty {
            detailLabel.stringValue = message
        } else {
            detailLabel.stringValue = "项目路径：\(projectPath)"
        }
    }

    private func isBotRunning() -> Bool {
        let cmd = "cd \(q(projectPath)) && if [ -f bot.pid ]; then pid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then echo running; exit 0; fi; fi; if pgrep -f \(q(projectPath + "/bot.py")) >/dev/null 2>&1; then echo running; else echo stopped; fi"
        let out = runShell(cmd).trimmingCharacters(in: .whitespacesAndNewlines)
        return out == "running"
    }

    private func runShell(_ cmd: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", cmd]

        var env = ProcessInfo.processInfo.environment
        let path = env["PATH"] ?? ""
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + path
        process.environment = env

        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return "shell run error: \(error.localizedDescription)"
        }

        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        let out = String(data: outData, encoding: .utf8) ?? ""
        let err = String(data: errData, encoding: .utf8) ?? ""
        return (out + err)
    }

    private func q(_ s: String) -> String {
        return "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
