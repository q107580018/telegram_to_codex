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

final class HoverButton: NSButton {
    private var trackingAreaRef: NSTrackingArea?
    private var isHovering = false
    private let gradientLayer = CAGradientLayer()

    var normalBackgroundColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }
    var hoverBackgroundColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }
    var pressedBackgroundColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }
    var normalTextColor: NSColor = .labelColor {
        didSet { refreshTitleColor() }
    }
    var normalBorderColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }
    var hoverBorderColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }
    var pressedBorderColor: NSColor = .clear {
        didSet { refreshAppearance() }
    }

    override var isHighlighted: Bool {
        didSet { refreshAppearance() }
    }

    override var title: String {
        didSet { refreshTitleColor() }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        isBordered = false
        focusRingType = .none
        font = NSFont.systemFont(ofSize: 13, weight: .medium)
        imagePosition = .imageLeading
        imageHugsTitle = true
        gradientLayer.startPoint = CGPoint(x: 0.5, y: 1.0)
        gradientLayer.endPoint = CGPoint(x: 0.5, y: 0.0)
        layer?.insertSublayer(gradientLayer, at: 0)
        refreshAppearance()
        refreshTitleColor()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingAreaRef {
            removeTrackingArea(trackingAreaRef)
        }
        let options: NSTrackingArea.Options = [.activeInKeyWindow, .inVisibleRect, .mouseEnteredAndExited]
        let newArea = NSTrackingArea(rect: .zero, options: options, owner: self, userInfo: nil)
        addTrackingArea(newArea)
        trackingAreaRef = newArea
    }

    override func mouseEntered(with event: NSEvent) {
        isHovering = true
        refreshAppearance()
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
        refreshAppearance()
    }

    override func layout() {
        super.layout()
        gradientLayer.frame = bounds
        gradientLayer.cornerRadius = 18
        gradientLayer.cornerCurve = .continuous
    }

    private func refreshAppearance() {
        guard let layer else { return }
        layer.cornerRadius = 18
        layer.cornerCurve = .continuous
        layer.borderWidth = 1.6
        layer.masksToBounds = false
        let baseColor: NSColor
        if isHighlighted {
            baseColor = pressedBackgroundColor
            layer.borderColor = pressedBorderColor.cgColor
            layer.shadowOpacity = 0.18
            layer.shadowRadius = 2.5
            layer.shadowOffset = CGSize(width: 0, height: -1)
            layer.transform = CATransform3DMakeTranslation(0, -1, 0)
        } else if isHovering {
            baseColor = hoverBackgroundColor
            layer.borderColor = hoverBorderColor.cgColor
            layer.shadowOpacity = 0.34
            layer.shadowRadius = 14
            layer.shadowOffset = CGSize(width: 0, height: -4)
            layer.transform = CATransform3DIdentity
        } else {
            baseColor = normalBackgroundColor
            layer.borderColor = normalBorderColor.cgColor
            layer.shadowOpacity = 0.28
            layer.shadowRadius = 12
            layer.shadowOffset = CGSize(width: 0, height: -3)
            layer.transform = CATransform3DIdentity
        }

        layer.backgroundColor = baseColor.blended(withFraction: 0.35, of: .black)?.cgColor
        gradientLayer.colors = [
            (baseColor.blended(withFraction: 0.22, of: .white) ?? baseColor).cgColor,
            baseColor.cgColor,
            (baseColor.blended(withFraction: 0.2, of: .black) ?? baseColor).cgColor,
        ]
    }

    private func refreshTitleColor() {
        let titleString = title
        attributedTitle = NSAttributedString(
            string: titleString,
            attributes: [
                .font: font ?? NSFont.systemFont(ofSize: 13, weight: .medium),
                .foregroundColor: normalTextColor,
            ]
        )
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let appName = "BotControl"
    private var didPromptFullDiskAccess = false
    private var shouldKeepBotRunning = false
    private var wasRunningBeforeSleep = false
    private var isWakeRecoveryInProgress = false
    private var workspaceObservers: [Any] = []

    private var window: NSWindow!
    private var logWindow: NSWindow?
    private var logRefreshTimer: Timer?
    private let statusDot = StatusDotView(frame: NSRect(x: 0, y: 0, width: 14, height: 14))
    private let statusLabel = NSTextField(labelWithString: "状态：准备中...")
    private let detailLabel = NSTextField(labelWithString: "")
    private let primaryButton = HoverButton(title: "启动", target: nil, action: nil)
    private let refreshButton = HoverButton(title: "刷新状态", target: nil, action: nil)
    private let logButton = HoverButton(title: "查看日志", target: nil, action: nil)
    private let configButton = HoverButton(title: "打开配置", target: nil, action: nil)

    private var runtimeDir: String {
        let support = NSSearchPathForDirectoriesInDomains(.applicationSupportDirectory, .userDomainMask, true).first!
        return support + "/" + appName + "/runtime"
    }

    private var pythonPath: String { runtimeDir + "/.venv/bin/python" }
    private var botPath: String { runtimeDir + "/bot.py" }
    private var pidPath: String { runtimeDir + "/bot.pid" }
    private var logPath: String { runtimeDir + "/bot.log" }
    private var launchLogPath: String { runtimeDir + "/bot.launch.log" }
    private var envPath: String { runtimeDir + "/.env" }
    private var envExamplePath: String { runtimeDir + "/.env.example" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupMainMenu()
        buildUI()
        setupPowerStateObservers()
        setPendingUI("初始化中...")
        promptForFullDiskAccessIfNeeded()

        DispatchQueue.global(qos: .userInitiated).async {
            let result = self.bootstrapRuntime()
            DispatchQueue.main.async {
                self.refreshStatus(message: result)
                self.shouldKeepBotRunning = self.isBotRunning()
            }
        }

        NSApp.activate(ignoringOtherApps: true)

        logRefreshTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            self?.refreshLogWindowIfVisible()
        }
    }

    private func hasFullDiskAccess() -> Bool {
        // 通过读取受保护目录做启发式检测：无权限时通常返回 NSCocoaErrorDomain Code=257。
        let probePaths = [
            NSHomeDirectory() + "/Library/Application Support/com.apple.TCC/TCC.db",
            NSHomeDirectory() + "/Library/Safari/Bookmarks.plist",
            NSHomeDirectory() + "/Library/Messages/chat.db",
        ]
        var hasExistingProbe = false
        for path in probePaths {
            if !FileManager.default.fileExists(atPath: path) {
                continue
            }
            hasExistingProbe = true
            do {
                _ = try Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe)
                return true
            } catch {
                continue
            }
        }
        return !hasExistingProbe
    }

    private func promptForFullDiskAccessIfNeeded() {
        if didPromptFullDiskAccess || hasFullDiskAccess() {
            return
        }
        didPromptFullDiskAccess = true

        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "建议开启“完全磁盘访问权限”"
        alert.informativeText = "未检测到完全磁盘访问权限，可能导致读取日志、运行时文件或其他本地资源失败。是否现在前往系统设置开启？"
        alert.addButton(withTitle: "前往开启")
        alert.addButton(withTitle: "稍后再说")
        alert.addButton(withTitle: "退出")
        let result = alert.runModal()

        if result == .alertFirstButtonReturn {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
                NSWorkspace.shared.open(url)
            }
        } else if result == .alertThirdButtonReturn {
            NSApp.terminate(nil)
        }
    }

    private func setupMainMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        let windowMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        mainMenu.addItem(windowMenuItem)

        let appMenu = NSMenu(title: appName)
        let quitTitle = "退出 \(appName)"
        let quitItem = NSMenuItem(
            title: quitTitle,
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        quitItem.keyEquivalentModifierMask = [.command]
        let closeItem = NSMenuItem(
            title: "关闭窗口",
            action: #selector(NSWindow.performClose(_:)),
            keyEquivalent: "w"
        )
        closeItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(closeItem)
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(quitItem)

        appMenuItem.submenu = appMenu

        let windowMenu = NSMenu(title: "窗口")
        let minimizeItem = NSMenuItem(
            title: "最小化",
            action: #selector(NSWindow.performMiniaturize(_:)),
            keyEquivalent: "m"
        )
        minimizeItem.keyEquivalentModifierMask = [.command]
        let zoomItem = NSMenuItem(
            title: "缩放",
            action: #selector(NSWindow.performZoom(_:)),
            keyEquivalent: ""
        )
        let closeWindowItem = NSMenuItem(
            title: "关闭",
            action: #selector(NSWindow.performClose(_:)),
            keyEquivalent: "w"
        )
        closeWindowItem.keyEquivalentModifierMask = [.command]
        windowMenu.addItem(minimizeItem)
        windowMenu.addItem(zoomItem)
        windowMenu.addItem(NSMenuItem.separator())
        windowMenu.addItem(closeWindowItem)
        windowMenuItem.submenu = windowMenu
        NSApp.windowsMenu = windowMenu

        NSApp.mainMenu = mainMenu
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        logRefreshTimer?.invalidate()
        logRefreshTimer = nil
        for observer in workspaceObservers {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
        }
        workspaceObservers.removeAll()
        _ = stopBotCommand()
    }

    private func setupPowerStateObservers() {
        let center = NSWorkspace.shared.notificationCenter
        let willSleepObserver = center.addObserver(
            forName: NSWorkspace.willSleepNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.handleWillSleep()
        }
        let didWakeObserver = center.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.handleDidWake()
        }
        workspaceObservers.append(willSleepObserver)
        workspaceObservers.append(didWakeObserver)
    }

    private func handleWillSleep() {
        wasRunningBeforeSleep = shouldKeepBotRunning || isBotRunning()
    }

    private func handleDidWake() {
        guard wasRunningBeforeSleep else {
            return
        }
        recoverBotAfterWake()
    }

    private func recoverBotAfterWake() {
        if isWakeRecoveryInProgress {
            return
        }
        isWakeRecoveryInProgress = true
        primaryButton.isEnabled = false
        setPendingUI("唤醒恢复中...")

        DispatchQueue.global(qos: .userInitiated).async {
            _ = self.stopBotCommand()
            let startOut = self.startBotCommand()
            DispatchQueue.main.async {
                self.isWakeRecoveryInProgress = false
                self.primaryButton.isEnabled = true
                self.shouldKeepBotRunning = self.isBotRunning()
                self.refreshStatus(message: "唤醒恢复：\(startOut)")
            }
        }
    }

    private func buildUI() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 980, height: 480),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "BotControl"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor.windowBackgroundColor
        window.minSize = NSSize(width: 900, height: 430)
        window.center()
        window.isReleasedWhenClosed = false

        let background = NSVisualEffectView(frame: window.contentView!.bounds)
        background.autoresizingMask = [.width, .height]
        background.material = .underWindowBackground
        background.blendingMode = .behindWindow
        background.state = .active
        window.contentView = background

        let card = NSVisualEffectView()
        card.translatesAutoresizingMaskIntoConstraints = false
        card.material = .sidebar
        card.blendingMode = .withinWindow
        card.state = .active
        card.wantsLayer = true
        card.layer?.cornerRadius = 18
        card.layer?.masksToBounds = true
        background.addSubview(card)

        NSLayoutConstraint.activate([
            card.topAnchor.constraint(equalTo: background.topAnchor, constant: 28),
            card.leadingAnchor.constraint(equalTo: background.leadingAnchor, constant: 24),
            card.trailingAnchor.constraint(equalTo: background.trailingAnchor, constant: -24),
            card.bottomAnchor.constraint(equalTo: background.bottomAnchor, constant: -24),
        ])

        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(content)

        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: card.topAnchor, constant: 28),
            content.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 26),
            content.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -26),
            content.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -24),
        ])

        let title = NSTextField(labelWithString: "Telegram Bot 控制器")
        title.translatesAutoresizingMaskIntoConstraints = false
        title.font = NSFont.systemFont(ofSize: 30, weight: .bold)
        title.textColor = .labelColor
        content.addSubview(title)

        let subtitle = NSTextField(labelWithString: "本地 Codex Runtime · Telegram 控制面板")
        subtitle.translatesAutoresizingMaskIntoConstraints = false
        subtitle.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        subtitle.textColor = .secondaryLabelColor
        content.addSubview(subtitle)

        statusDot.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(statusDot)

        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.font = NSFont.systemFont(ofSize: 17, weight: .semibold)
        content.addSubview(statusLabel)

        detailLabel.translatesAutoresizingMaskIntoConstraints = false
        detailLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.lineBreakMode = .byTruncatingMiddle
        detailLabel.stringValue = "运行环境：App 内置"
        content.addSubview(detailLabel)

        primaryButton.title = "启动"
        primaryButton.target = self
        primaryButton.action = #selector(primaryTapped)
        stylePrimaryButton(primaryButton)

        refreshButton.title = "刷新状态"
        refreshButton.target = self
        refreshButton.action = #selector(refreshMenuTapped)
        styleSecondaryButton(refreshButton, symbolName: "arrow.clockwise")

        logButton.title = "查看日志"
        logButton.target = self
        logButton.action = #selector(openLogTapped)
        styleSecondaryButton(logButton, symbolName: "doc.text.magnifyingglass")

        configButton.title = "打开配置"
        configButton.target = self
        configButton.action = #selector(openConfigTapped)
        styleSecondaryButton(configButton, symbolName: "slider.horizontal.3")

        let buttonRow = NSStackView(views: [primaryButton, refreshButton, logButton, configButton])
        buttonRow.translatesAutoresizingMaskIntoConstraints = false
        buttonRow.orientation = .horizontal
        buttonRow.spacing = 16
        buttonRow.distribution = .fillEqually
        buttonRow.alignment = .centerY
        content.addSubview(buttonRow)

        primaryButton.translatesAutoresizingMaskIntoConstraints = false
        refreshButton.translatesAutoresizingMaskIntoConstraints = false
        logButton.translatesAutoresizingMaskIntoConstraints = false
        configButton.translatesAutoresizingMaskIntoConstraints = false

        NSLayoutConstraint.activate([
            primaryButton.heightAnchor.constraint(equalToConstant: 90),
            refreshButton.heightAnchor.constraint(equalTo: primaryButton.heightAnchor),
            logButton.heightAnchor.constraint(equalTo: primaryButton.heightAnchor),
            configButton.heightAnchor.constraint(equalTo: primaryButton.heightAnchor),
        ])

        let hint = NSTextField(labelWithString: "关闭窗口会自动停止 bot")
        hint.translatesAutoresizingMaskIntoConstraints = false
        hint.font = NSFont.systemFont(ofSize: 12)
        hint.textColor = .secondaryLabelColor
        content.addSubview(hint)

        NSLayoutConstraint.activate([
            title.topAnchor.constraint(equalTo: content.topAnchor),
            title.leadingAnchor.constraint(equalTo: content.leadingAnchor),

            subtitle.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 4),
            subtitle.leadingAnchor.constraint(equalTo: title.leadingAnchor),

            statusDot.topAnchor.constraint(equalTo: subtitle.bottomAnchor, constant: 22),
            statusDot.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 2),
            statusDot.widthAnchor.constraint(equalToConstant: 14),
            statusDot.heightAnchor.constraint(equalToConstant: 14),

            statusLabel.centerYAnchor.constraint(equalTo: statusDot.centerYAnchor),
            statusLabel.leadingAnchor.constraint(equalTo: statusDot.trailingAnchor, constant: 10),
            statusLabel.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor),

            detailLabel.topAnchor.constraint(equalTo: statusDot.bottomAnchor, constant: 14),
            detailLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            detailLabel.trailingAnchor.constraint(equalTo: content.trailingAnchor),

            buttonRow.topAnchor.constraint(equalTo: detailLabel.bottomAnchor, constant: 26),
            buttonRow.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            buttonRow.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            buttonRow.heightAnchor.constraint(equalToConstant: 90),

            hint.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            hint.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])

        window.makeKeyAndOrderFront(nil)
    }

    private func stylePrimaryButton(_ button: HoverButton) {
        button.font = NSFont.systemFont(ofSize: 16, weight: .bold)
        button.contentTintColor = .white
        button.normalBackgroundColor = NSColor.systemBlue
        button.hoverBackgroundColor = NSColor.systemBlue.blended(withFraction: 0.2, of: .black) ?? NSColor.systemBlue
        button.pressedBackgroundColor = NSColor.systemBlue.blended(withFraction: 0.35, of: .black) ?? NSColor.systemBlue
        button.normalBorderColor = NSColor.systemBlue.blended(withFraction: 0.25, of: .black) ?? NSColor.systemBlue
        button.hoverBorderColor = NSColor.systemBlue.blended(withFraction: 0.4, of: .black) ?? NSColor.systemBlue
        button.pressedBorderColor = NSColor.systemBlue.blended(withFraction: 0.5, of: .black) ?? NSColor.systemBlue
        button.normalTextColor = .white
    }

    private func styleSecondaryButton(_ button: HoverButton, symbolName: String) {
        button.font = NSFont.systemFont(ofSize: 15, weight: .semibold)
        button.image = NSImage(systemSymbolName: symbolName, accessibilityDescription: nil)
        button.imagePosition = .imageLeading
        button.imageHugsTitle = true
        button.contentTintColor = .labelColor
        button.normalBackgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.45)
        button.hoverBackgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.18)
        button.pressedBackgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.28)
        button.normalBorderColor = NSColor.separatorColor.withAlphaComponent(0.35)
        button.hoverBorderColor = NSColor.controlAccentColor.withAlphaComponent(0.45)
        button.pressedBorderColor = NSColor.controlAccentColor.withAlphaComponent(0.6)
        button.normalTextColor = .labelColor
    }

    @objc private func primaryTapped() {
        if isWakeRecoveryInProgress {
            return
        }
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
                self.shouldKeepBotRunning = self.isBotRunning()
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
                self.shouldKeepBotRunning = false
                self.primaryButton.isEnabled = true
            }
        }
    }

    @objc private func refreshMenuTapped() {
        refreshStatus()
    }

    @objc private func openLogTapped() {
        showLogWindow()
    }

    @objc private func openConfigTapped() {
        let fm = FileManager.default
        if !fm.fileExists(atPath: envPath) {
            do {
                if !fm.fileExists(atPath: runtimeDir) {
                    try fm.createDirectory(atPath: runtimeDir, withIntermediateDirectories: true)
                }
                guard fm.fileExists(atPath: envExamplePath) else {
                    showAlert(
                        title: "打开配置失败",
                        text: "未找到 .env.example，请先启动一次应用完成运行时初始化。"
                    )
                    return
                }
                try fm.copyItem(atPath: envExamplePath, toPath: envPath)
            } catch {
                showAlert(
                    title: "打开配置失败",
                    text: "创建 .env 失败：\(error.localizedDescription)"
                )
                return
            }
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: envPath))
    }

    private func showAlert(title: String, text: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = text
        alert.addButton(withTitle: "好")
        alert.runModal()
    }

    private func showLogWindow() {
        if logWindow == nil {
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 760, height: 460),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false
            )
            win.title = "Bot 日志"
            win.isReleasedWhenClosed = false
            win.center()

            let scrollView = NSScrollView(frame: win.contentView!.bounds)
            scrollView.autoresizingMask = [.width, .height]
            scrollView.hasVerticalScroller = true
            scrollView.hasHorizontalScroller = true

            let textView = NSTextView(frame: scrollView.bounds)
            textView.isEditable = false
            textView.isRichText = false
            textView.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
            scrollView.documentView = textView

            win.contentView?.addSubview(scrollView)
            logWindow = win
        }

        guard let win = logWindow,
              let scrollView = win.contentView?.subviews.first as? NSScrollView,
              let textView = scrollView.documentView as? NSTextView else {
            return
        }

        updateLogTextView(textView)
        win.makeKeyAndOrderFront(nil)
        textView.scrollToEndOfDocument(nil)
    }

    private func refreshLogWindowIfVisible() {
        guard let win = logWindow,
              win.isVisible,
              let scrollView = win.contentView?.subviews.first as? NSScrollView,
              let textView = scrollView.documentView as? NSTextView else {
            return
        }
        updateLogTextView(textView)
    }

    private func updateLogTextView(_ textView: NSTextView) {
        let logText: String
        if FileManager.default.fileExists(atPath: logPath),
           let content = try? String(contentsOfFile: logPath, encoding: .utf8) {
            logText = content
        } else {
            logText = "暂无日志"
        }

        if textView.string == logText {
            return
        }

        let wasNearBottom: Bool
        if let scrollView = textView.enclosingScrollView {
            let visibleMaxY = scrollView.contentView.bounds.maxY
            let documentHeight = textView.bounds.height
            wasNearBottom = visibleMaxY >= documentHeight - 40
        } else {
            wasNearBottom = true
        }

        textView.string = logText
        if wasNearBottom {
            textView.scrollToEndOfDocument(nil)
        }
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

    private func extractEnvKey(from line: String, includeCommented: Bool) -> String? {
        var candidate = line.trimmingCharacters(in: .whitespaces)
        if candidate.isEmpty {
            return nil
        }
        if candidate.hasPrefix("#") {
            guard includeCommented else { return nil }
            candidate = String(candidate.dropFirst()).trimmingCharacters(in: .whitespaces)
        }
        guard !candidate.isEmpty, let idx = candidate.firstIndex(of: "=") else {
            return nil
        }
        let rawKey = String(candidate[..<idx]).trimmingCharacters(in: .whitespaces)
        guard !rawKey.isEmpty else {
            return nil
        }
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
        if rawKey.rangeOfCharacter(from: allowed.inverted) != nil {
            return nil
        }
        return rawKey
    }

    private func isDescriptionCommentLine(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty {
            return true
        }
        guard trimmed.hasPrefix("#") else {
            return false
        }
        let body = String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)
        return !body.contains("=")
    }

    private func syncMissingEnvKeysFromTemplate() -> Int {
        let fm = FileManager.default
        guard fm.fileExists(atPath: envPath), fm.fileExists(atPath: envExamplePath) else {
            return 0
        }

        let runtimeText: String
        let templateText: String
        do {
            runtimeText = try String(contentsOfFile: envPath, encoding: .utf8)
            templateText = try String(contentsOfFile: envExamplePath, encoding: .utf8)
        } catch {
            return 0
        }

        let runtimeLines = runtimeText.components(separatedBy: .newlines)
        let templateLines = templateText.components(separatedBy: .newlines)

        var existingKeys = Set<String>()
        for line in runtimeLines {
            if let key = extractEnvKey(from: line, includeCommented: true) {
                existingKeys.insert(key)
            }
        }

        var missingLines: [String] = []
        var addedKeys = Set<String>()
        for (idx, line) in templateLines.enumerated() {
            guard let key = extractEnvKey(from: line, includeCommented: true) else {
                continue
            }
            if existingKeys.contains(key) || addedKeys.contains(key) {
                continue
            }

            // 把该配置项上方的“说明注释”一并带过去（只带纯说明，不带其他 key 行）。
            var commentStart = idx
            var cursor = idx - 1
            while cursor >= 0 {
                let prevLine = templateLines[cursor]
                if isDescriptionCommentLine(prevLine) {
                    commentStart = cursor
                    cursor -= 1
                    continue
                }
                break
            }
            if commentStart < idx {
                for infoLine in templateLines[commentStart..<idx] {
                    if missingLines.last != infoLine {
                        missingLines.append(infoLine)
                    }
                }
            }
            missingLines.append(line)
            addedKeys.insert(key)
        }

        if missingLines.isEmpty {
            return 0
        }

        let ts = Int(Date().timeIntervalSince1970)
        let backupPath = envPath + ".bak.\(ts)"
        do {
            try fm.copyItem(atPath: envPath, toPath: backupPath)
        } catch {
            return 0
        }

        var newText = runtimeText
        if !newText.hasSuffix("\n") {
            newText += "\n"
        }
        newText += "\n"
        newText += missingLines.joined(separator: "\n")
        newText += "\n"

        do {
            try newText.write(toFile: envPath, atomically: true, encoding: .utf8)
            pruneEnvBackups(keepLatest: 6)
            return missingLines.count
        } catch {
            return 0
        }
    }

    private func pruneEnvBackups(keepLatest: Int) {
        let fm = FileManager.default
        guard keepLatest >= 0 else { return }

        let dirURL = URL(fileURLWithPath: runtimeDir, isDirectory: true)
        guard let items = try? fm.contentsOfDirectory(
            at: dirURL,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: []
        ) else {
            return
        }

        let backupURLs = items.filter { $0.lastPathComponent.hasPrefix(".env.bak.") }
        if backupURLs.count <= keepLatest {
            return
        }

        let sorted = backupURLs.sorted { lhs, rhs in
            let ldate = (try? lhs.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let rdate = (try? rhs.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return ldate > rdate
        }

        for url in sorted.dropFirst(keepLatest) {
            try? fm.removeItem(at: url)
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
            "env_store.py",
            "chat_store.py",
            "handlers.py",
            "codex_client.py",
            "project_service.py",
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

        let addedCount = syncMissingEnvKeysFromTemplate()
        if addedCount > 0 {
            return "运行环境已就绪（已补全 \(addedCount) 个新配置项）"
        }
        return "运行环境已就绪"
    }

    private func startBotCommand() -> String {
        let cmd = "cd \(q(runtimeDir)) && if [ -f bot.pid ]; then oldpid=$(cat bot.pid 2>/dev/null || true); if [ -n \"$oldpid\" ] && ps -p \"$oldpid\" >/dev/null 2>&1; then echo already_running; exit 0; fi; fi; if pgrep -f \(q(botPath)) >/dev/null 2>&1; then echo already_running; exit 0; fi; BOT_LOG_TO_STDOUT=0 nohup \(q(pythonPath)) \(q(botPath)) > \(q(launchLogPath)) 2>&1 & newpid=$!; echo $newpid > \(q(pidPath)); sleep 1; if ps -p \"$newpid\" >/dev/null 2>&1; then echo started; else echo failed; fi"
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
