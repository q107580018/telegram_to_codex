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

    override var isEnabled: Bool {
        didSet {
            refreshAppearance()
            refreshTitleColor()
        }
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

        if !isEnabled {
            let disabledBackground = NSColor.controlBackgroundColor.withAlphaComponent(0.35)
            layer.backgroundColor = disabledBackground.cgColor
            gradientLayer.colors = [
                disabledBackground.cgColor,
                disabledBackground.cgColor,
            ]
            layer.borderColor = NSColor.separatorColor.withAlphaComponent(0.2).cgColor
            layer.shadowOpacity = 0
            layer.transform = CATransform3DIdentity
            return
        }

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
        let titleColor = isEnabled ? normalTextColor : NSColor.disabledControlTextColor
        attributedTitle = NSAttributedString(
            string: titleString,
            attributes: [
                .font: font ?? NSFont.systemFont(ofSize: 13, weight: .medium),
                .foregroundColor: titleColor,
            ]
        )
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let appName = "CodexBridge"
    private let selectedPlatformDefaultsKey = "SelectedPlatformID"
    private var didPromptFullDiskAccess = false
    private var didPromptCodexInstall = false
    private var shouldKeepBotRunning = false
    private var wasRunningBeforeSleep = false
    private var isWakeRecoveryInProgress = false
    private var workspaceObservers: [Any] = []
    private let defaultWindowSize = NSSize(width: 720, height: 420)
    private let minimumWindowSize = NSSize(width: 620, height: 360)
    private var availablePlatforms: [AppPlatformDefinition] = defaultAppPlatforms()
    private var currentPlatform: AppPlatformDefinition = defaultAppPlatforms()[0]

    private var window: NSWindow!
    private var logWindow: NSWindow?
    private var logRefreshTimer: Timer?
    private var autoStatusTimer: Timer?
    private var statusItem: NSStatusItem?
    private let statusSummaryMenuItem = NSMenuItem(title: "状态：准备中...", action: nil, keyEquivalent: "")
    private var toggleWindowMenuItem: NSMenuItem?
    private var toggleBotMenuItem: NSMenuItem?
    private let titleLabel = NSTextField(labelWithString: "CodexBridge 控制器")
    private let subtitleLabel = NSTextField(labelWithString: "")
    private let platformSelector = NSPopUpButton(frame: .zero, pullsDown: false)
    private let statusDot = StatusDotView(frame: NSRect(x: 0, y: 0, width: 14, height: 14))
    private let statusLabel = NSTextField(labelWithString: "状态：准备中...")
    private let detailLabel = NSTextField(labelWithString: "")
    private let projectPathLabel = NSTextField(labelWithString: "项目目录：读取中...")
    private let envPathLabel = NSTextField(labelWithString: "配置文件：读取中...")
    private let primaryButton = HoverButton(title: "启动", target: nil, action: nil)
    private let logButton = HoverButton(title: "查看日志", target: nil, action: nil)
    private let configButton = HoverButton(title: "打开配置", target: nil, action: nil)

    private var runtimeDir: String {
        let support = NSSearchPathForDirectoriesInDomains(.applicationSupportDirectory, .userDomainMask, true).first!
        return support + "/" + appName + "/runtime"
    }
    private var legacyRuntimeDir: String {
        let support = NSSearchPathForDirectoriesInDomains(.applicationSupportDirectory, .userDomainMask, true).first!
        return support + "/BotControl/runtime"
    }

    private var pythonPath: String { runtimeDir + "/.venv/bin/python" }
    private var logPath: String { runtimeDir + "/bot.log" }
    private var envPath: String { runtimeDir + "/.env" }
    private var runtimeEnvExamplePath: String { runtimeDir + "/.env.example" }
    private var runtimePlatformsPath: String { runtimeDir + "/platforms.json" }
    private var bundledEnvExamplePath: String? {
        guard let resourceURL = Bundle.main.resourceURL else {
            return nil
        }
        return resourceURL
            .appendingPathComponent("BotRuntime")
            .appendingPathComponent(".env.example")
            .path
    }
    private var bundledPlatformsPath: String? {
        guard let resourceURL = Bundle.main.resourceURL else {
            return nil
        }
        return resourceURL
            .appendingPathComponent("BotRuntime")
            .appendingPathComponent("platforms.json")
            .path
    }
    private var currentBotPath: String { botPath(for: currentPlatform) }
    private var currentPidPath: String { pidPath(for: currentPlatform) }
    private var currentLaunchLogPath: String { launchLogPath(for: currentPlatform) }

    private func resolvedEnvExamplePath() -> String? {
        let fm = FileManager.default
        if let bundledPath = bundledEnvExamplePath, fm.fileExists(atPath: bundledPath) {
            return bundledPath
        }
        if fm.fileExists(atPath: runtimeEnvExamplePath) {
            return runtimeEnvExamplePath
        }
        return nil
    }

    private func loadAvailablePlatforms() -> [AppPlatformDefinition] {
        let fm = FileManager.default
        let candidates = [
            runtimePlatformsPath,
            bundledPlatformsPath,
            FileManager.default.currentDirectoryPath + "/platforms.json",
        ].compactMap { $0 }

        for path in candidates where fm.fileExists(atPath: path) {
            if let loaded = try? loadAppPlatforms(from: URL(fileURLWithPath: path)), !loaded.isEmpty {
                return loaded
            }
        }
        return defaultAppPlatforms()
    }

    private func restoreSelectedPlatform() {
        availablePlatforms = loadAvailablePlatforms()
        currentPlatform = resolveSelectedPlatform(
            storedPlatformID: UserDefaults.standard.string(forKey: selectedPlatformDefaultsKey),
            available: availablePlatforms
        )
    }

    private func persistSelectedPlatform() {
        UserDefaults.standard.set(currentPlatform.id, forKey: selectedPlatformDefaultsKey)
    }

    private func botPath(for platform: AppPlatformDefinition) -> String {
        runtimeDir + "/" + platform.entryScript
    }

    private func pidPath(for platform: AppPlatformDefinition) -> String {
        runtimeDir + "/" + platform.pidFile
    }

    private func launchLogPath(for platform: AppPlatformDefinition) -> String {
        runtimeDir + "/" + platform.launchLogFile
    }

    private func currentEnvText() -> String {
        (try? String(contentsOfFile: envPath, encoding: .utf8)) ?? ""
    }

    private func missingCurrentPlatformEnvKeys() -> [String] {
        missingRequiredEnvKeys(in: currentEnvText(), for: currentPlatform)
    }

    private func refreshPlatformSelectorItems() {
        platformSelector.removeAllItems()
        platformSelector.addItems(withTitles: availablePlatforms.map(\.displayName))
        if let index = availablePlatforms.firstIndex(where: { $0.id == currentPlatform.id }) {
            platformSelector.selectItem(at: index)
        }
    }

    private func refreshPlatformUI(shouldRefreshStatus: Bool = true) {
        titleLabel.stringValue = "CodexBridge 控制器"
        subtitleLabel.stringValue = "本地 Codex Runtime · \(currentPlatform.displayName) 控制面板"
        window?.title = "CodexBridge · \(currentPlatform.displayName)"
        primaryButton.setAccessibilityLabel("启动或停止 \(currentPlatform.displayName) 机器人")
        if let button = statusItem?.button {
            button.toolTip = "CodexBridge 菜单 · \(currentPlatform.displayName)"
        }
        if let logWindow {
            logWindow.title = "\(currentPlatform.displayName) 日志"
        }
        updatePathLabels()
        if shouldRefreshStatus {
            refreshStatus()
        } else {
            refreshStatusMenuItems()
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        restoreSelectedPlatform()
        setupMainMenu()
        setupStatusItem()
        buildUI()
        setupPowerStateObservers()
        setControlButtonsEnabled(false)
        setPendingUI("初始化中...")
        promptForFullDiskAccessIfNeeded()

        DispatchQueue.global(qos: .userInitiated).async {
            let result = self.bootstrapRuntime()
            DispatchQueue.main.async {
                self.restoreSelectedPlatform()
                self.refreshPlatformSelectorItems()
                self.refreshStatus(message: result)
                let missingCodex = result.hasPrefix("初始化失败：未检测到 codex 命令")
                if missingCodex {
                    self.primaryButton.isEnabled = false
                    self.promptForCodexInstallIfNeeded()
                } else {
                    self.setControlButtonsEnabled(true)
                }
                self.shouldKeepBotRunning = self.isBotRunning()
            }
        }

        NSApp.activate(ignoringOtherApps: true)

        logRefreshTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            self?.refreshLogWindowIfVisible()
        }
        autoStatusTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            self?.autoRefreshStatusIfNeeded()
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

    private func promptForCodexInstallIfNeeded() {
        if didPromptCodexInstall {
            return
        }
        didPromptCodexInstall = true

        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "未检测到 codex 命令"
        alert.informativeText = "当前设备未找到可执行的 codex，机器人无法启动。\n请先安装：brew install --cask codex\n安装后重启 CodexBridge。"
        alert.addButton(withTitle: "前往安装文档")
        alert.addButton(withTitle: "稍后再说")
        alert.addButton(withTitle: "退出")
        let result = alert.runModal()

        if result == .alertFirstButtonReturn {
            if let url = URL(string: "https://developers.openai.com/codex/cli/") {
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
        false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            showMainWindow()
        }
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        logRefreshTimer?.invalidate()
        logRefreshTimer = nil
        autoStatusTimer?.invalidate()
        autoStatusTimer = nil
        for observer in workspaceObservers {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
        }
        workspaceObservers.removeAll()
        stopAllKnownBots()
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
        setControlButtonsEnabled(false)
        setPendingUI("唤醒恢复中...")

        DispatchQueue.global(qos: .userInitiated).async {
            _ = self.stopBotCommand()
            let startOut = self.startBotCommand()
            DispatchQueue.main.async {
                self.isWakeRecoveryInProgress = false
                self.setControlButtonsEnabled(true)
                self.shouldKeepBotRunning = self.isBotRunning()
                self.refreshStatus(message: "唤醒恢复：\(startOut)")
            }
        }
    }

    private func buildUI() {
        window = NSWindow(
            contentRect: NSRect(
                x: 0,
                y: 0,
                width: defaultWindowSize.width,
                height: defaultWindowSize.height
            ),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "CodexBridge"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor.windowBackgroundColor
        window.minSize = minimumWindowSize
        window.center()
        window.isReleasedWhenClosed = false
        window.delegate = self

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
        card.layer?.cornerRadius = 20
        card.layer?.cornerCurve = .continuous
        card.layer?.borderWidth = 1
        card.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.2).cgColor
        card.layer?.masksToBounds = true
        background.addSubview(card)

        NSLayoutConstraint.activate([
            card.topAnchor.constraint(equalTo: background.topAnchor, constant: 28),
            card.leadingAnchor.constraint(equalTo: background.leadingAnchor, constant: 24),
            card.trailingAnchor.constraint(equalTo: background.trailingAnchor, constant: -24),
            card.bottomAnchor.constraint(equalTo: background.bottomAnchor, constant: -24),
        ])

        let rootStack = NSStackView()
        rootStack.translatesAutoresizingMaskIntoConstraints = false
        rootStack.orientation = .vertical
        rootStack.spacing = 16
        rootStack.alignment = .leading
        rootStack.edgeInsets = NSEdgeInsets(top: 26, left: 24, bottom: 22, right: 24)
        card.addSubview(rootStack)

        NSLayoutConstraint.activate([
            rootStack.topAnchor.constraint(equalTo: card.topAnchor),
            rootStack.leadingAnchor.constraint(equalTo: card.leadingAnchor),
            rootStack.trailingAnchor.constraint(equalTo: card.trailingAnchor),
            rootStack.bottomAnchor.constraint(equalTo: card.bottomAnchor),
        ])

        titleLabel.font = NSFont.systemFont(ofSize: 31, weight: .bold)
        titleLabel.textColor = .labelColor

        subtitleLabel.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        subtitleLabel.textColor = .secondaryLabelColor
        let titleStack = NSStackView(views: [titleLabel, subtitleLabel])
        titleStack.orientation = .vertical
        titleStack.spacing = 4
        titleStack.alignment = .leading
        let titleRow = NSStackView()
        titleRow.orientation = .horizontal
        titleRow.alignment = .top
        titleRow.distribution = .fill
        titleRow.spacing = 18
        titleRow.translatesAutoresizingMaskIntoConstraints = false
        titleRow.addArrangedSubview(titleStack)

        let platformPanel = NSStackView()
        platformPanel.orientation = .vertical
        platformPanel.alignment = .leading
        platformPanel.spacing = 6

        let platformCaption = NSTextField(labelWithString: "当前平台")
        platformCaption.font = NSFont.systemFont(ofSize: 11, weight: .semibold)
        platformCaption.textColor = .tertiaryLabelColor
        platformPanel.addArrangedSubview(platformCaption)

        platformSelector.translatesAutoresizingMaskIntoConstraints = false
        platformSelector.target = self
        platformSelector.action = #selector(platformSelectionChanged)
        refreshPlatformSelectorItems()
        platformSelector.setContentCompressionResistancePriority(.required, for: .horizontal)
        platformPanel.addArrangedSubview(platformSelector)
        NSLayoutConstraint.activate([
            platformSelector.widthAnchor.constraint(equalToConstant: 160),
        ])

        titleRow.addArrangedSubview(platformPanel)
        rootStack.addArrangedSubview(titleRow)
        titleRow.widthAnchor.constraint(equalTo: rootStack.widthAnchor, constant: -48).isActive = true

        let statusPanel = makePanel()
        let statusStack = NSStackView()
        statusStack.translatesAutoresizingMaskIntoConstraints = false
        statusStack.orientation = .vertical
        statusStack.alignment = .leading
        statusStack.spacing = 9
        statusPanel.addSubview(statusStack)
        NSLayoutConstraint.activate([
            statusStack.topAnchor.constraint(equalTo: statusPanel.topAnchor, constant: 14),
            statusStack.leadingAnchor.constraint(equalTo: statusPanel.leadingAnchor, constant: 16),
            statusStack.trailingAnchor.constraint(equalTo: statusPanel.trailingAnchor, constant: -16),
            statusStack.bottomAnchor.constraint(equalTo: statusPanel.bottomAnchor, constant: -14),
        ])

        statusDot.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.font = NSFont.systemFont(ofSize: 18, weight: .semibold)
        statusLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let statusRow = NSStackView(views: [statusDot, statusLabel])
        statusRow.orientation = .horizontal
        statusRow.alignment = .centerY
        statusRow.spacing = 10
        NSLayoutConstraint.activate([
            statusDot.widthAnchor.constraint(equalToConstant: 14),
            statusDot.heightAnchor.constraint(equalToConstant: 14),
        ])
        statusStack.addArrangedSubview(statusRow)

        detailLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.lineBreakMode = .byTruncatingMiddle
        detailLabel.stringValue = "运行环境：App 内置"
        detailLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        statusStack.addArrangedSubview(detailLabel)

        let projectCaption = NSTextField(labelWithString: "项目目录")
        projectCaption.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        projectCaption.textColor = .tertiaryLabelColor
        statusStack.addArrangedSubview(projectCaption)

        projectPathLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        projectPathLabel.textColor = .secondaryLabelColor
        projectPathLabel.lineBreakMode = .byTruncatingMiddle
        projectPathLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        statusStack.addArrangedSubview(projectPathLabel)

        let envCaption = NSTextField(labelWithString: "配置文件")
        envCaption.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        envCaption.textColor = .tertiaryLabelColor
        statusStack.addArrangedSubview(envCaption)

        envPathLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        envPathLabel.textColor = .secondaryLabelColor
        envPathLabel.lineBreakMode = .byTruncatingMiddle
        envPathLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        statusStack.addArrangedSubview(envPathLabel)

        rootStack.addArrangedSubview(statusPanel)
        statusPanel.widthAnchor.constraint(equalTo: rootStack.widthAnchor, constant: -48).isActive = true

        primaryButton.title = "启动"
        primaryButton.target = self
        primaryButton.action = #selector(primaryTapped)
        stylePrimaryButton(primaryButton)
        primaryButton.keyEquivalent = "\r"
        primaryButton.keyEquivalentModifierMask = []
        primaryButton.setAccessibilityLabel("启动或停止机器人")

        logButton.title = "查看日志"
        logButton.target = self
        logButton.action = #selector(openLogTapped)
        styleSecondaryButton(logButton, symbolName: "doc.text.magnifyingglass")
        logButton.keyEquivalent = "l"
        logButton.keyEquivalentModifierMask = [.command]
        logButton.setAccessibilityLabel("打开机器人日志窗口")

        configButton.title = "打开配置"
        configButton.target = self
        configButton.action = #selector(openConfigTapped)
        styleSecondaryButton(configButton, symbolName: "slider.horizontal.3")
        configButton.keyEquivalent = ","
        configButton.keyEquivalentModifierMask = [.command]
        configButton.setAccessibilityLabel("打开运行时配置文件")

        let actionPanel = makePanel()
        let actionStack = NSStackView()
        actionStack.translatesAutoresizingMaskIntoConstraints = false
        actionStack.orientation = .vertical
        actionStack.spacing = 10
        actionPanel.addSubview(actionStack)
        NSLayoutConstraint.activate([
            actionStack.topAnchor.constraint(equalTo: actionPanel.topAnchor, constant: 14),
            actionStack.leadingAnchor.constraint(equalTo: actionPanel.leadingAnchor, constant: 16),
            actionStack.trailingAnchor.constraint(equalTo: actionPanel.trailingAnchor, constant: -16),
            actionStack.bottomAnchor.constraint(equalTo: actionPanel.bottomAnchor, constant: -14),
        ])

        let buttonRow = NSStackView(views: [primaryButton, logButton, configButton])
        buttonRow.orientation = .horizontal
        buttonRow.spacing = 12
        buttonRow.distribution = .fillEqually
        buttonRow.alignment = .centerY
        actionStack.addArrangedSubview(buttonRow)
        NSLayoutConstraint.activate([
            primaryButton.heightAnchor.constraint(equalToConstant: 58),
            logButton.heightAnchor.constraint(equalTo: primaryButton.heightAnchor),
            configButton.heightAnchor.constraint(equalTo: primaryButton.heightAnchor),
        ])

        let actionHint = NSTextField(
            labelWithString: "状态自动刷新（3 秒）· 快捷键：⌘L 查看日志 · ⌘, 打开配置 · Enter 启动/停止"
        )
        actionHint.font = NSFont.systemFont(ofSize: 11, weight: .regular)
        actionHint.textColor = .tertiaryLabelColor
        actionHint.lineBreakMode = .byTruncatingTail
        actionStack.addArrangedSubview(actionHint)

        rootStack.addArrangedSubview(actionPanel)
        actionPanel.widthAnchor.constraint(equalTo: rootStack.widthAnchor, constant: -48).isActive = true

        let footer = NSTextField(labelWithString: "提示：关闭窗口会隐藏到菜单栏；退出应用才会停止 bot。唤醒后若之前在运行会自动恢复。")
        footer.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        footer.textColor = .secondaryLabelColor
        footer.lineBreakMode = .byTruncatingTail
        rootStack.addArrangedSubview(footer)

        refreshPlatformUI(shouldRefreshStatus: false)
        statusDot.setAccessibilityLabel("机器人状态指示")

        window.makeKeyAndOrderFront(nil)
        refreshStatusMenuItems()
    }

    private func setupStatusItem() {
        let newStatusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = newStatusItem.button {
            if let icon = NSImage(systemSymbolName: "paperplane.circle.fill", accessibilityDescription: appName) {
                icon.isTemplate = true
                button.image = icon
            } else {
                button.title = "BC"
            }
            button.toolTip = "CodexBridge 菜单"
        }

        let menu = NSMenu()
        statusSummaryMenuItem.isEnabled = false
        menu.addItem(statusSummaryMenuItem)
        menu.addItem(NSMenuItem.separator())

        let windowItem = NSMenuItem(title: "隐藏主窗口", action: #selector(toggleMainWindowFromMenuBar), keyEquivalent: "")
        windowItem.target = self
        menu.addItem(windowItem)
        toggleWindowMenuItem = windowItem

        let botItem = NSMenuItem(title: "启动机器人", action: #selector(toggleBotFromMenuBar), keyEquivalent: "")
        botItem.target = self
        menu.addItem(botItem)
        toggleBotMenuItem = botItem

        let refreshItem = NSMenuItem(title: "刷新状态", action: #selector(refreshFromMenuBar), keyEquivalent: "")
        refreshItem.target = self
        menu.addItem(refreshItem)
        menu.addItem(NSMenuItem.separator())

        let logItem = NSMenuItem(title: "查看日志", action: #selector(openLogTapped), keyEquivalent: "")
        logItem.target = self
        menu.addItem(logItem)

        let configItem = NSMenuItem(title: "打开配置", action: #selector(openConfigTapped), keyEquivalent: "")
        configItem.target = self
        menu.addItem(configItem)
        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(
            title: "退出 \(appName)",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: ""
        )
        quitItem.target = NSApp
        menu.addItem(quitItem)

        newStatusItem.menu = menu
        statusItem = newStatusItem
        refreshStatusMenuItems()
    }

    private var isMainWindowVisible: Bool {
        guard window != nil else {
            return false
        }
        return window.isVisible && !window.isMiniaturized
    }

    private func showMainWindow() {
        if window.isMiniaturized {
            window.deminiaturize(nil)
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        refreshStatusMenuItems()
    }

    private func hideMainWindowToMenuBar() {
        window.orderOut(nil)
        refreshStatusMenuItems()
    }

    private func refreshStatusMenuItems(
        statusTextOverride: String? = nil,
        runningOverride: Bool? = nil
    ) {
        let running = runningOverride ?? isBotRunning()
        if let statusTextOverride, !statusTextOverride.isEmpty {
            statusSummaryMenuItem.title = "\(currentPlatform.displayName)：\(statusTextOverride)"
        } else {
            statusSummaryMenuItem.title = running
                ? "\(currentPlatform.displayName)：运行中"
                : "\(currentPlatform.displayName)：已停止"
        }
        toggleBotMenuItem?.title = menuBotActionTitle(isRunning: running)
        toggleWindowMenuItem?.title = isMainWindowVisible ? "隐藏主窗口" : "显示主窗口"
    }

    @objc private func toggleMainWindowFromMenuBar() {
        if isMainWindowVisible {
            hideMainWindowToMenuBar()
        } else {
            showMainWindow()
        }
    }

    @objc private func platformSelectionChanged() {
        let index = platformSelector.indexOfSelectedItem
        guard availablePlatforms.indices.contains(index) else {
            return
        }
        currentPlatform = availablePlatforms[index]
        persistSelectedPlatform()
        refreshPlatformUI()
    }

    @objc private func toggleBotFromMenuBar() {
        if isWakeRecoveryInProgress || !primaryButton.isEnabled {
            return
        }
        if isBotRunning() {
            stopTapped()
        } else {
            startTapped()
        }
    }

    @objc private func refreshFromMenuBar() {
        if isWakeRecoveryInProgress || !primaryButton.isEnabled {
            return
        }
        refreshStatus()
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard sender == window else {
            return true
        }
        hideMainWindowToMenuBar()
        return false
    }

    func windowDidMiniaturize(_ notification: Notification) {
        refreshStatusMenuItems()
    }

    func windowDidDeminiaturize(_ notification: Notification) {
        refreshStatusMenuItems()
    }

    private func makePanel() -> NSVisualEffectView {
        let panel = NSVisualEffectView()
        panel.translatesAutoresizingMaskIntoConstraints = false
        panel.material = .menu
        panel.blendingMode = .withinWindow
        panel.state = .active
        panel.wantsLayer = true
        panel.layer?.cornerRadius = 14
        panel.layer?.cornerCurve = .continuous
        panel.layer?.borderWidth = 1
        panel.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.25).cgColor
        return panel
    }

    private func updatePathLabels() {
        let currentProject = readEnvValue(for: "CODEX_PROJECT_DIR")
        if let currentProject, !currentProject.isEmpty {
            projectPathLabel.stringValue = currentProject
        } else {
            projectPathLabel.stringValue = "未设置（默认使用 runtime 目录）"
        }
        envPathLabel.stringValue = envPath
    }

    private func readEnvValue(for key: String) -> String? {
        guard let text = try? String(contentsOfFile: envPath, encoding: .utf8) else {
            return nil
        }
        for line in text.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") {
                continue
            }
            guard let idx = trimmed.firstIndex(of: "=") else {
                continue
            }
            let candidateKey = String(trimmed[..<idx]).trimmingCharacters(in: .whitespaces)
            if candidateKey != key {
                continue
            }
            var rawValue = String(trimmed[trimmed.index(after: idx)...]).trimmingCharacters(in: .whitespaces)
            if rawValue.hasPrefix("\""), rawValue.hasSuffix("\""), rawValue.count >= 2 {
                rawValue.removeFirst()
                rawValue.removeLast()
            } else if rawValue.hasPrefix("'"), rawValue.hasSuffix("'"), rawValue.count >= 2 {
                rawValue.removeFirst()
                rawValue.removeLast()
            }
            return rawValue
        }
        return nil
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
        button.normalBackgroundColor = NSColor.controlBackgroundColor.withAlphaComponent(0.58)
        button.hoverBackgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.18)
        button.pressedBackgroundColor = NSColor.controlAccentColor.withAlphaComponent(0.28)
        button.normalBorderColor = NSColor.separatorColor.withAlphaComponent(0.35)
        button.hoverBorderColor = NSColor.controlAccentColor.withAlphaComponent(0.45)
        button.pressedBorderColor = NSColor.controlAccentColor.withAlphaComponent(0.6)
        button.normalTextColor = .labelColor
    }

    private func setControlButtonsEnabled(_ isEnabled: Bool) {
        primaryButton.isEnabled = isEnabled
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
        setControlButtonsEnabled(false)
        setPendingUI("启动中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let out = self.startBotCommand()
            let message = self.messageForStartCommandOutput(out)
            let output = out.trimmingCharacters(in: .whitespacesAndNewlines)
            DispatchQueue.main.async {
                let running = self.isBotRunning()
                self.refreshStatus(runningOverride: running, message: message)
                self.shouldKeepBotRunning = running || output == "started" || output == "already_running"
                self.setControlButtonsEnabled(true)
            }
        }
    }

    private func stopTapped() {
        setControlButtonsEnabled(false)
        setPendingUI("停止中...")
        DispatchQueue.global(qos: .userInitiated).async {
            let out = self.stopBotCommand()
            DispatchQueue.main.async {
                self.refreshStatus(message: out)
                self.shouldKeepBotRunning = false
                self.setControlButtonsEnabled(true)
            }
        }
    }

    @objc private func openLogTapped() {
        showLogWindow()
    }

    private func autoRefreshStatusIfNeeded() {
        if isWakeRecoveryInProgress || !primaryButton.isEnabled {
            return
        }
        updatePathLabels()
        let running = isBotRunning()
        let uiRunning = primaryButton.title.hasPrefix("停止")
        if running == uiRunning {
            return
        }
        shouldKeepBotRunning = running
        if running {
            refreshStatus(runningOverride: true, message: "状态自动刷新：运行中")
        } else {
            refreshStatus(
                runningOverride: false,
                message: "状态自动刷新：已停止（\(friendlyStartFailureReason())）"
            )
        }
    }

    @objc private func openConfigTapped() {
        let fm = FileManager.default
        if !fm.fileExists(atPath: envPath) {
            do {
                if !fm.fileExists(atPath: runtimeDir) {
                    try fm.createDirectory(atPath: runtimeDir, withIntermediateDirectories: true)
                }
                guard let templatePath = resolvedEnvExamplePath() else {
                    showAlert(
                        title: "打开配置失败",
                        text: "未找到 .env.example（App 内置与 runtime 均不存在）。"
                    )
                    return
                }
                try fm.copyItem(atPath: templatePath, toPath: envPath)
            } catch {
                showAlert(
                    title: "打开配置失败",
                    text: "创建 .env 失败：\(error.localizedDescription)"
                )
                return
            }
        }
        updatePathLabels()
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
            win.title = "\(currentPlatform.displayName) 日志"
            win.isReleasedWhenClosed = false
            win.center()

            let scrollView = NSScrollView(frame: win.contentView!.bounds)
            scrollView.autoresizingMask = [.width, .height]
            scrollView.hasVerticalScroller = true
            scrollView.hasHorizontalScroller = true
            scrollView.borderType = .noBorder

            let textView = NSTextView(frame: scrollView.bounds)
            textView.isEditable = false
            textView.isRichText = true
            textView.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
            textView.usesAdaptiveColorMappingForDarkAppearance = true
            textView.drawsBackground = true
            textView.backgroundColor = NSColor.textBackgroundColor
            textView.insertionPointColor = NSColor.clear
            textView.textContainerInset = NSSize(width: 12, height: 10)
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
        let logText = readLogTextForDisplay()

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

        let attributedLog = buildLogAttributedText(logText)
        if let textStorage = textView.textStorage {
            textStorage.setAttributedString(attributedLog)
        } else {
            textView.string = logText
        }
        if wasNearBottom {
            textView.scrollToEndOfDocument(nil)
        }
    }

    private func buildLogAttributedText(_ logText: String) -> NSAttributedString {
        let lines = logText.components(separatedBy: .newlines)
        let attributed = NSMutableAttributedString()
        for (idx, line) in lines.enumerated() {
            let attrs = logLineAttributes(for: line)
            attributed.append(NSAttributedString(string: line, attributes: attrs))
            if idx < lines.count - 1 {
                attributed.append(NSAttributedString(string: "\n", attributes: attrs))
            }
        }
        return attributed
    }

    private func logLineAttributes(for line: String) -> [NSAttributedString.Key: Any] {
        let lowered = line.lowercased()
        let baseFont = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        var color = NSColor.textColor
        if lowered.contains("error") || lowered.contains("traceback") || lowered.contains("exception") || lowered.contains("failed") {
            color = .systemRed
        } else if lowered.contains("warn") {
            color = .systemOrange
        } else if lowered.contains("started") || lowered.contains("running") || lowered.contains("ready") || lowered.contains("success") {
            color = .systemGreen
        } else if lowered.contains("stop") || lowered.contains("stopped") {
            color = NSColor.systemPink.blended(withFraction: 0.25, of: .labelColor) ?? .systemPink
        }
        return [
            .font: baseFont,
            .foregroundColor: color,
        ]
    }

    private func setPendingUI(_ text: String) {
        statusDot.setColor(.systemOrange)
        statusLabel.stringValue = "状态：\(currentPlatform.displayName) \(text)"
        detailLabel.stringValue = "\(currentPlatform.displayName) · \(text)"
        updatePathLabels()
        refreshStatusMenuItems(statusTextOverride: text)
    }

    private func refreshStatus(runningOverride: Bool? = nil, message: String? = nil) {
        let running = runningOverride ?? isBotRunning()
        shouldKeepBotRunning = running
        if running {
            statusDot.setColor(.systemGreen)
            statusLabel.stringValue = "状态：\(currentPlatform.displayName) 运行中"
            primaryButton.title = primaryBotActionTitle(isRunning: true)
        } else {
            statusDot.setColor(.systemRed)
            statusLabel.stringValue = "状态：\(currentPlatform.displayName) 已停止"
            primaryButton.title = primaryBotActionTitle(isRunning: false)
        }

        if let message, !message.isEmpty {
            detailLabel.stringValue = message
        } else {
            detailLabel.stringValue = "运行环境：App 内置 · 当前平台：\(currentPlatform.displayName)"
        }
        updatePathLabels()
        refreshStatusMenuItems(runningOverride: running)
    }

    private func messageForStartCommandOutput(_ rawOutput: String) -> String {
        let output = rawOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        if output.hasPrefix("failed:") {
            let reasonRaw = String(output.dropFirst("failed:".count))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if reasonRaw.isEmpty {
                return "启动失败：\(friendlyStartFailureReason())"
            }
            return "启动失败：\(mapTechnicalStartErrorToFriendly(reasonRaw))"
        }
        if output == "failed" {
            return "启动失败：\(friendlyStartFailureReason())"
        }
        return output
    }

    private func friendlyStartFailureReason() -> String {
        let missingKeys = missingCurrentPlatformEnvKeys()
        if !missingKeys.isEmpty {
            let joined = missingKeys.joined(separator: "、")
            return "缺少 \(currentPlatform.displayName) 配置（\(joined)），请先在配置中填写。"
        }

        guard let raw = readLastLaunchErrorLine(), !raw.isEmpty else {
            return "请查看启动日志（\(currentPlatform.launchLogFile)）。"
        }
        return mapTechnicalStartErrorToFriendly(raw)
    }

    private func mapTechnicalStartErrorToFriendly(_ raw: String) -> String {
        let lowered = raw.lowercased()
        if lowered.contains("__bc_bot_exit__") {
            return "bot 进程启动后立即退出（\(raw)），请查看启动日志定位根因。"
        }
        if currentPlatform.id == "telegram" {
            if lowered.contains("missing telegram_bot_token") {
                return "缺少 Telegram Bot Token（TELEGRAM_BOT_TOKEN）。"
            }
            if lowered.contains("invalidtoken") || lowered.contains("unauthorized") {
                return "Telegram Bot Token 无效，请检查是否填错。"
            }
            if lowered.contains("conflict: terminated by other getupdates request") {
                return "检测到同一 Token 有其他机器人实例在轮询，请先关闭其它实例。"
            }
            if lowered.contains("ssl_error_syscall")
                || lowered.contains("remoteprotocolerror")
                || lowered.contains("connecterror")
                || lowered.contains("proxyerror")
            {
                return "网络或代理连接失败，请检查代理配置（TELEGRAM_PROXY_URL）和代理软件状态。"
            }
        } else if currentPlatform.id == "feishu" {
            if lowered.contains("feishu_app_id") || lowered.contains("feishu_app_secret") {
                return "缺少飞书应用凭证（FEISHU_APP_ID / FEISHU_APP_SECRET）。"
            }
            if lowered.contains("websocket")
                || lowered.contains("handshake")
                || lowered.contains("connection")
                || lowered.contains("timeout")
            {
                return "飞书长连接初始化失败，请检查网络和应用配置。"
            }
            if lowered.contains("image upload") || lowered.contains("image_key") {
                return "飞书图片上传失败，请检查图片格式、权限与网络。"
            }
        }
        if lowered.contains("no such file or directory") && lowered.contains("codex") {
            return "找不到 codex 命令，请安装 codex 或修正 CODEX_BIN。"
        }
        if lowered.contains("unsupported operand type(s) for |")
            && lowered.contains("nonetype")
        {
            return "当前 Python 版本过低（不兼容类型注解语法），请升级到 Python 3.10+。"
        }
        if lowered.contains("no running event loop") {
            return "初始化网络轮询时发生事件循环异常，常见于代理/网络瞬断；请重试并检查 TELEGRAM_PROXY_URL。"
        }
        return raw
    }

    private func readLastLaunchErrorLine() -> String? {
        guard let content = try? String(contentsOfFile: currentLaunchLogPath, encoding: .utf8) else {
            return nil
        }
        let lines = content.components(separatedBy: .newlines)
        for line in lines.reversed() {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            return trimmed
        }
        return nil
    }

    private func readLogTextForDisplay() -> String {
        let botText = (try? String(contentsOfFile: logPath, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let launchText = (try? String(contentsOfFile: currentLaunchLogPath, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let launchLogName = currentPlatform.launchLogFile

        if !botText.isEmpty, !launchText.isEmpty {
            return "[运行日志 bot.log]\n\(botText)\n\n[启动日志 \(launchLogName)]\n\(launchText)\n"
        }
        if !botText.isEmpty {
            return botText + "\n"
        }
        if !launchText.isEmpty {
            return "[启动日志 \(launchLogName)]\n\(launchText)\n"
        }
        return "暂无日志（尚未启动）\n日志路径：\(logPath)\n启动日志路径：\(currentLaunchLogPath)"
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
        guard
            fm.fileExists(atPath: envPath),
            let templatePath = resolvedEnvExamplePath()
        else {
            return 0
        }

        let runtimeText: String
        let templateText: String
        do {
            runtimeText = try String(contentsOfFile: envPath, encoding: .utf8)
            templateText = try String(contentsOfFile: templatePath, encoding: .utf8)
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
        migrateLegacyRuntimeIfNeeded()
        do {
            try fm.createDirectory(atPath: runtimeDir, withIntermediateDirectories: true)
        } catch {
            return "初始化失败：\(error.localizedDescription)"
        }
        ensureRuntimeLogFiles()

        guard let resourceURL = Bundle.main.resourceURL else {
            return "初始化失败：读取资源目录失败"
        }
        let bundleRuntime = resourceURL.appendingPathComponent("BotRuntime")
        let requiredRuntimeFiles = [
            "bot.py",
            "feishu_bot.py",
            "requirements.txt",
            ".env.example",
            "config.py",
            "env_store.py",
            "chat_store.py",
            "handlers.py",
            "polling_health.py",
            "codex_client.py",
            "project_service.py",
            "bridge_core.py",
            "platform_messages.py",
            "platform_registry.py",
            "platforms.json",
            "telegram_io.py",
            "telegram_adapter.py",
            "feishu_io.py",
            "feishu_adapter.py",
            "skills.py",
        ]
        let optionalRuntimeFiles = [
            ".env",
        ]

        for name in requiredRuntimeFiles {
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

        for name in optionalRuntimeFiles {
            let src = bundleRuntime.appendingPathComponent(name).path
            let dst = runtimeDir + "/" + name
            if !fm.fileExists(atPath: src) {
                continue
            }
            do {
                if fm.fileExists(atPath: dst) {
                    continue
                }
                try fm.copyItem(atPath: src, toPath: dst)
            } catch {
                return "初始化失败：复制 \(name) 失败"
            }
        }

        if !fm.fileExists(atPath: envPath) {
            guard let templatePath = resolvedEnvExamplePath() else {
                return "初始化失败：缺少资源 .env.example"
            }
            do {
                try fm.copyItem(atPath: templatePath, toPath: envPath)
            } catch {
                return "初始化失败：创建 .env 失败"
            }
        }

        guard let codexPath = resolveCodexBinaryPath() else {
            return "初始化失败：未检测到 codex 命令（请先安装）"
        }

        let setupCmd = "cd \(q(runtimeDir)) && " +
            "if ! command -v uv >/dev/null 2>&1; then echo __BC_MISSING_UV__; exit 0; fi; " +
            "if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then " +
            "rm -rf .venv; " +
            "uv venv --python 3.12 .venv >/dev/null 2>&1 || " +
            "uv venv --python 3.11 .venv >/dev/null 2>&1 || " +
            "uv venv --python 3.10 .venv >/dev/null 2>&1 || " +
            "uv venv .venv >/dev/null 2>&1; " +
            "fi; " +
            "if [ ! -x .venv/bin/python ]; then echo __BC_PY_MISSING__; exit 0; fi; " +
            "if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then echo __BC_PY_TOO_OLD__; exit 0; fi; " +
            "if uv pip install -r requirements.txt >/dev/null 2>&1; then echo __BC_SETUP_OK__; else echo __BC_SETUP_FAILED__; fi"
        let out = runShell(setupCmd)
        if out.contains("__BC_MISSING_UV__") {
            return "初始化失败：未检测到 uv（请先安装 uv）"
        }
        if out.contains("__BC_PY_TOO_OLD__") {
            return "初始化失败：Python 版本过低（需要 Python 3.10+）"
        }
        if out.contains("__BC_PY_MISSING__") {
            return "初始化失败：Python 环境创建失败（.venv 不可用）"
        }
        if out.contains("__BC_SETUP_FAILED__") || !out.contains("__BC_SETUP_OK__") {
            return "初始化失败：Python 依赖安装失败 \(out.trimmingCharacters(in: .whitespacesAndNewlines))"
        }

        let addedCount = syncMissingEnvKeysFromTemplate()
        if addedCount > 0 {
            return "运行环境已就绪（codex: \(codexPath)，已补全 \(addedCount) 个新配置项）"
        }
        return "运行环境已就绪（codex: \(codexPath)）"
    }

    private func migrateLegacyRuntimeIfNeeded() {
        let fm = FileManager.default
        guard legacyRuntimeDir != runtimeDir else {
            return
        }
        guard fm.fileExists(atPath: legacyRuntimeDir), !fm.fileExists(atPath: runtimeDir) else {
            return
        }
        let targetParent = (runtimeDir as NSString).deletingLastPathComponent
        do {
            try fm.createDirectory(atPath: targetParent, withIntermediateDirectories: true)
            try fm.moveItem(atPath: legacyRuntimeDir, toPath: runtimeDir)
        } catch {
            // Ignore migration errors and continue with fresh runtime setup.
        }
    }

    private func ensureRuntimeLogFiles() {
        let fm = FileManager.default
        let launchLogs = availablePlatforms.map { launchLogPath(for: $0) }
        for path in [logPath] + launchLogs {
            if fm.fileExists(atPath: path) {
                continue
            }
            fm.createFile(atPath: path, contents: Data(), attributes: nil)
        }
    }

    private func resolveCodexBinaryPath() -> String? {
        let fm = FileManager.default

        if let rawValue = readEnvValue(for: "CODEX_BIN")?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !rawValue.isEmpty {
            let expanded = NSString(string: rawValue).expandingTildeInPath
            if expanded.hasPrefix("/") {
                if fm.isExecutableFile(atPath: expanded) {
                    return expanded
                }
            } else {
                let resolved = runShell("command -v \(q(expanded))")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !resolved.isEmpty {
                    return resolved
                }
            }
        }

        let pathResolved = runShell("command -v codex")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !pathResolved.isEmpty {
            return pathResolved
        }

        for candidate in ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"] {
            if fm.isExecutableFile(atPath: candidate) {
                return candidate
            }
        }
        return nil
    }

    private func startBotCommand() -> String {
        stopAllKnownBots(except: currentPlatform.id)
        return startBotCommand(for: currentPlatform)
    }

    private func startBotCommand(for platform: AppPlatformDefinition) -> String {
        let botPath = botPath(for: platform)
        let pidPath = pidPath(for: platform)
        let launchLogPath = launchLogPath(for: platform)
        let runner = "cd \(q(runtimeDir)); env -u ALL_PROXY -u all_proxy BOT_LOG_TO_STDOUT=0 \(q(pythonPath)) \(q(botPath)) >> \(q(launchLogPath)) 2>&1; code=$?; ts=$(date '+%Y-%m-%d %H:%M:%S'); echo \"__BC_BOT_EXIT__ code=$code ts=$ts\" >> \(q(launchLogPath))"
        let cmd = "cd \(q(runtimeDir)) && : > \(q(launchLogPath)); ts=$(date '+%Y-%m-%d %H:%M:%S'); echo \"[bc-start] ts=$ts python=\(pythonPath) bot=\(botPath) platform=\(platform.id)\" >> \(q(launchLogPath)); if [ -f \(q(pidPath)) ]; then oldpid=$(cat \(q(pidPath)) 2>/dev/null || true); if [ -n \"$oldpid\" ] && ps -p \"$oldpid\" >/dev/null 2>&1; then echo already_running; exit 0; fi; fi; if pgrep -f \(q(botPath)) >/dev/null 2>&1; then echo already_running; exit 0; fi; if [ ! -x \(q(pythonPath)) ]; then echo \"Python runtime missing: \(pythonPath)\" >> \(q(launchLogPath)); echo failed:python_runtime_missing; exit 0; fi; nohup /bin/zsh -lc \(q(runner)) >/dev/null 2>&1 & newpid=$!; echo $newpid > \(q(pidPath)); started=0; for _ in 1 2 3 4 5 6 7 8 9 10; do if ps -p \"$newpid\" >/dev/null 2>&1; then started=1; break; fi; sleep 0.1; done; if [ \"$started\" = \"1\" ]; then echo started; else rm -f \(q(pidPath)); reason=$(tail -n 20 \(q(launchLogPath)) 2>/dev/null | tr -d '\\r' | awk 'NF{line=$0} END{print line}' || true); if [ -z \"$reason\" ]; then reason=$(tail -n 20 \(q(logPath)) 2>/dev/null | tr -d '\\r' | awk 'NF{line=$0} END{print line}' || true); fi; if [ -z \"$reason\" ]; then reason=process_exited_immediately_without_log; fi; echo failed:\"$reason\"; fi"
        return runShell(cmd).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func stopBotCommand() -> String {
        stopBotCommand(for: currentPlatform)
    }

    private func stopBotCommand(for platform: AppPlatformDefinition) -> String {
        let botPath = botPath(for: platform)
        let pidPath = pidPath(for: platform)
        let launchLogPath = launchLogPath(for: platform)
        let cmd = "cd \(q(runtimeDir)) && ts=$(date '+%Y-%m-%d %H:%M:%S'); echo \"[bc-stop] ts=$ts platform=\(platform.id)\" >> \(q(launchLogPath)); if [ -f \(q(pidPath)) ]; then pid=$(cat \(q(pidPath)) 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then kill \"$pid\" >/dev/null 2>&1 || true; fi; fi; pkill -TERM -f \(q(botPath)) >/dev/null 2>&1 || true; for _ in 1 2 3 4 5 6 7 8 9 10; do if ! pgrep -f \(q(botPath)) >/dev/null 2>&1; then break; fi; sleep 0.1; done; if pgrep -f \(q(botPath)) >/dev/null 2>&1; then pkill -9 -f \(q(botPath)) >/dev/null 2>&1 || true; echo \"[bc-stop] forced_kill=1\" >> \(q(launchLogPath)); else echo \"[bc-stop] forced_kill=0\" >> \(q(launchLogPath)); fi; rm -f \(q(pidPath)); echo stopped"
        return runShell(cmd).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func stopAllKnownBots(except platformID: String? = nil) {
        for platform in availablePlatforms where platform.id != platformID {
            _ = stopBotCommand(for: platform)
        }
    }

    private func isBotRunning() -> Bool {
        isBotRunning(for: currentPlatform)
    }

    private func isBotRunning(for platform: AppPlatformDefinition) -> Bool {
        let botPath = botPath(for: platform)
        let pidPath = pidPath(for: platform)
        let pidCheckCmd = "cd \(q(runtimeDir)) && if [ -f \(q(pidPath)) ]; then pid=$(cat \(q(pidPath)) 2>/dev/null || true); if [ -n \"$pid\" ] && ps -p \"$pid\" >/dev/null 2>&1; then ps -p \"$pid\" -o command= 2>/dev/null || true; fi; fi"
        let pidCommand = runShell(pidCheckCmd).trimmingCharacters(in: .whitespacesAndNewlines)
        if commandLineMatchesPlatformProcess(pidCommand, botPath: botPath) {
            return true
        }

        let out = runShell("pgrep -f \(q(botPath)) >/dev/null 2>&1 && echo running || echo stopped")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
