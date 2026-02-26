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

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let appName = "BotControl"

    private var window: NSWindow!
    private let statusDot = StatusDotView(frame: NSRect(x: 0, y: 0, width: 14, height: 14))
    private let statusLabel = NSTextField(labelWithString: "状态：准备中...")
    private let detailLabel = NSTextField(labelWithString: "")
    private let primaryButton = NSButton(title: "启动", target: nil, action: nil)

    private var runtimeDir: String {
        let support = NSSearchPathForDirectoriesInDomains(.applicationSupportDirectory, .userDomainMask, true).first!
        return support + "/" + appName + "/runtime"
    }

    private var pythonPath: String { runtimeDir + "/.venv/bin/python" }
    private var botPath: String { runtimeDir + "/bot.py" }
    private var pidPath: String { runtimeDir + "/bot.pid" }
    private var logPath: String { runtimeDir + "/bot.log" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupMainMenu()
        buildUI()
        setPendingUI("初始化中...")

        DispatchQueue.global(qos: .userInitiated).async {
            let result = self.bootstrapRuntime()
            DispatchQueue.main.async {
                self.refreshStatus(message: result)
            }
        }

        NSApp.activate(ignoringOtherApps: true)
    }

    private func setupMainMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)

        let appMenu = NSMenu(title: appName)
        let quitTitle = "退出 \(appName)"
        let quitItem = NSMenuItem(
            title: quitTitle,
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        quitItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(quitItem)

        appMenuItem.submenu = appMenu
        NSApp.mainMenu = mainMenu
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        _ = stopBotCommand()
    }

    private func buildUI() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 300),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Telegram Bot 控制器"
        window.center()
        window.isReleasedWhenClosed = false

        let content = NSView(frame: window.contentView!.bounds)
        content.autoresizingMask = [.width, .height]
        window.contentView = content

        let title = NSTextField(labelWithString: "Telegram Bot 控制器")
        title.font = NSFont.systemFont(ofSize: 22, weight: .semibold)
        title.frame = NSRect(x: 24, y: 245, width: 320, height: 30)
        content.addSubview(title)

        statusDot.frame = NSRect(x: 26, y: 212, width: 14, height: 14)
        content.addSubview(statusDot)

        statusLabel.font = NSFont.systemFont(ofSize: 16, weight: .medium)
        statusLabel.frame = NSRect(x: 48, y: 206, width: 320, height: 24)
        content.addSubview(statusLabel)

        detailLabel.font = NSFont.systemFont(ofSize: 12)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.frame = NSRect(x: 24, y: 182, width: 510, height: 18)
        detailLabel.lineBreakMode = .byTruncatingMiddle
        detailLabel.stringValue = "运行环境：App 内置"
        content.addSubview(detailLabel)

        primaryButton.title = "启动"
        primaryButton.target = self
        primaryButton.action = #selector(primaryTapped)
        primaryButton.bezelStyle = .rounded
        primaryButton.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        primaryButton.frame = NSRect(x: 24, y: 125, width: 120, height: 36)
        content.addSubview(primaryButton)

        let opBtn = makeButton(title: "操作", action: #selector(opTapped))
        opBtn.frame = NSRect(x: 156, y: 125, width: 120, height: 36)
        content.addSubview(opBtn)

        let hint = NSTextField(labelWithString: "关闭窗口会自动停止 bot")
        hint.font = NSFont.systemFont(ofSize: 12)
        hint.textColor = .secondaryLabelColor
        hint.frame = NSRect(x: 24, y: 28, width: 240, height: 16)
        content.addSubview(hint)

        window.makeKeyAndOrderFront(nil)
    }

    private func makeButton(title: String, action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.bezelStyle = .rounded
        button.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        return button
    }

    @objc private func primaryTapped() {
        if isBotRunning() {
            stopTapped()
        } else {
            startTapped()
        }
    }

    private func startTapped() {
        primaryButton.isEnabled = false
        setPendingUI("启动中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let out = self.startBotCommand()
            DispatchQueue.main.async {
                self.refreshStatus(message: out)
                self.primaryButton.isEnabled = true
            }
        }
    }

    private func stopTapped() {
        primaryButton.isEnabled = false
        setPendingUI("停止中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let out = self.stopBotCommand()
            DispatchQueue.main.async {
                self.refreshStatus(message: out)
                self.primaryButton.isEnabled = true
            }
        }
    }

    @objc private func opTapped() {
        let menu = NSMenu()
        menu.addItem(withTitle: "刷新状态", action: #selector(refreshMenuTapped), keyEquivalent: "")
        menu.addItem(withTitle: "查看日志", action: #selector(openLogTapped), keyEquivalent: "")
        menu.popUp(positioning: nil, at: NSPoint(x: 156, y: 120), in: window.contentView)
    }

    @objc private func refreshMenuTapped() {
        refreshStatus()
    }

    @objc private func openLogTapped() {
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
            primaryButton.title = "停止"
        } else {
            statusDot.setColor(.systemRed)
            statusLabel.stringValue = "状态：已停止"
            primaryButton.title = "启动"
        }

        if let message, !message.isEmpty {
            detailLabel.stringValue = message
        } else {
            detailLabel.stringValue = "运行环境：App 内置"
        }
    }

    private func bootstrapRuntime() -> String {
        let fm = FileManager.default
        do {
            try fm.createDirectory(atPath: runtimeDir, withIntermediateDirectories: true)
        } catch {
            return "初始化失败：\(error.localizedDescription)"
        }

        guard let resourceURL = Bundle.main.resourceURL else {
            return "初始化失败：读取资源目录失败"
        }
        let bundleRuntime = resourceURL.appendingPathComponent("BotRuntime")
        let runtimeFiles = [
            "bot.py",
            "requirements.txt",
            ".env",
            ".env.example",
            "config.py",
            "codex_client.py",
            "telegram_io.py",
            "skills.py",
        ]

        for name in runtimeFiles {
            let src = bundleRuntime.appendingPathComponent(name).path
            let dst = runtimeDir + "/" + name
            if !fm.fileExists(atPath: src) {
                return "初始化失败：缺少资源 \(name)"
            }
            do {
                if name == ".env" && fm.fileExists(atPath: dst) {
                    // 保留用户已有配置
                } else {
                    if fm.fileExists(atPath: dst) {
                        try fm.removeItem(atPath: dst)
                    }
                    try fm.copyItem(atPath: src, toPath: dst)
                }
            } catch {
                return "初始化失败：复制 \(name) 失败"
            }
        }

        let setupCmd = "cd \(q(runtimeDir)) && if [ ! -x .venv/bin/python ]; then uv venv .venv; fi && uv pip install -r requirements.txt >/dev/null"
        let out = runShell(setupCmd)
        if !FileManager.default.fileExists(atPath: pythonPath) {
            return "初始化失败：Python 环境未就绪 \(out.trimmingCharacters(in: .whitespacesAndNewlines))"
        }

        return "运行环境已就绪"
    }

    private func startBotCommand() -> String {
        let cmd = "cd \(q(runtimeDir)) && if [ -f bot.pid ]; then oldpid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$oldpid\" ] && ps -p \"$oldpid\" >/dev/null 2>&1; then echo already_running; exit 0; fi; fi; nohup \(q(pythonPath)) \(q(botPath)) >> \(q(logPath)) 2>&1 & newpid=$!; echo $newpid > \(q(pidPath)); sleep 1; if ps -p \"$newpid\" >/dev/null 2>&1; then echo started; else echo failed; fi"
        return runShell(cmd).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func stopBotCommand() -> String {
        let cmd = "cd \(q(runtimeDir)) && if [ -f bot.pid ]; then pid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then kill \"$pid\" >/dev/null 2>&1 || true; fi; fi; pkill -f \(q(botPath)) >/dev/null 2>&1 || true; rm -f \(q(pidPath)); echo stopped"
        return runShell(cmd).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func isBotRunning() -> Bool {
        let cmd = "cd \(q(runtimeDir)) && if [ -f bot.pid ]; then pid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then echo running; exit 0; fi; fi; if pgrep -f \(q(botPath)) >/dev/null 2>&1; then echo running; else echo stopped; fi"
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
        return out + err
    }

    private func q(_ s: String) -> String {
        "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
