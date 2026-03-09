import Foundation

struct AppPlatformDefinition: Codable, Equatable {
    let id: String
    let displayName: String
    let entryScript: String
    let requiredEnvKeys: [String]
    let pidFile: String
    let launchLogFile: String
    let supportsImages: Bool
    let supportsCommands: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case entryScript = "entry_script"
        case requiredEnvKeys = "required_env_keys"
        case pidFile = "pid_file"
        case launchLogFile = "launch_log_file"
        case supportsImages = "supports_images"
        case supportsCommands = "supports_commands"
    }
}

private struct AppPlatformRegistryPayload: Codable {
    let platforms: [AppPlatformDefinition]
}

func defaultAppPlatforms() -> [AppPlatformDefinition] {
    [
        AppPlatformDefinition(
            id: "telegram",
            displayName: "Telegram",
            entryScript: "app/telegram/bot.py",
            requiredEnvKeys: ["TELEGRAM_BOT_TOKEN"],
            pidFile: "telegram.pid",
            launchLogFile: "telegram.launch.log",
            supportsImages: true,
            supportsCommands: true
        ),
        AppPlatformDefinition(
            id: "feishu",
            displayName: "Feishu",
            entryScript: "app/feishu/feishu_bot.py",
            requiredEnvKeys: ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
            pidFile: "feishu.pid",
            launchLogFile: "feishu.launch.log",
            supportsImages: true,
            supportsCommands: false
        ),
    ]
}

func loadAppPlatforms(from url: URL) throws -> [AppPlatformDefinition] {
    let data = try Data(contentsOf: url)
    let decoder = JSONDecoder()
    return try decoder.decode(AppPlatformRegistryPayload.self, from: data).platforms
}

func resolveSelectedPlatform(
    storedPlatformID: String?,
    available: [AppPlatformDefinition]
) -> AppPlatformDefinition {
    if let storedPlatformID,
       let matched = available.first(where: { $0.id == storedPlatformID }) {
        return matched
    }
    if let first = available.first {
        return first
    }
    return defaultAppPlatforms()[0]
}

func envValue(for key: String, in envText: String) -> String? {
    for line in envText.components(separatedBy: .newlines) {
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
        var rawValue = String(trimmed[trimmed.index(after: idx)...]).trimmingCharacters(
            in: .whitespaces
        )
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

func missingRequiredEnvKeys(
    in envText: String,
    for platform: AppPlatformDefinition
) -> [String] {
    platform.requiredEnvKeys.filter { key in
        let value = envValue(for: key, in: envText)?.trimmingCharacters(
            in: .whitespacesAndNewlines
        ) ?? ""
        return value.isEmpty
    }
}

func commandLineMatchesPlatformProcess(_ commandLine: String, botPath: String) -> Bool {
    let normalizedCommand = commandLine.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalizedBotPath = botPath.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalizedCommand.isEmpty, !normalizedBotPath.isEmpty else {
        return false
    }
    return normalizedCommand.contains(normalizedBotPath)
}

func primaryBotActionTitle(isRunning: Bool) -> String {
    isRunning ? "停止" : "启动"
}

func menuBotActionTitle(isRunning: Bool) -> String {
    isRunning ? "停止机器人" : "启动机器人"
}
