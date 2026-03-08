import Foundation

@main
struct AppPlatformSelectionTest {
    static func main() throws {
        let repoRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let defs = try loadAppPlatforms(from: repoRoot.appendingPathComponent("platforms.json"))
        let selected = resolveSelectedPlatform(storedPlatformID: "feishu", available: defs)

        if selected.id != "feishu" {
            fatalError("selected platform mismatch")
        }

        let envText = """
        TELEGRAM_BOT_TOKEN=telegram-token
        FEISHU_APP_ID=
        FEISHU_APP_SECRET=secret
        """
        let missing = missingRequiredEnvKeys(in: envText, for: selected)
        if missing != ["FEISHU_APP_ID"] {
            fatalError("unexpected missing keys: \(missing)")
        }

        if !commandLineMatchesPlatformProcess(
            "/usr/bin/python3 /tmp/runtime/feishu_bot.py",
            botPath: "/tmp/runtime/feishu_bot.py"
        ) {
            fatalError("expected feishu command line to match bot path")
        }

        if commandLineMatchesPlatformProcess(
            "/usr/bin/python3 /usr/bin/other.py",
            botPath: "/tmp/runtime/feishu_bot.py"
        ) {
            fatalError("unexpected unrelated command line match")
        }

        if primaryBotActionTitle(isRunning: true) != "停止" {
            fatalError("unexpected running primary action title")
        }

        if primaryBotActionTitle(isRunning: false) != "启动" {
            fatalError("unexpected stopped primary action title")
        }

        if menuBotActionTitle(isRunning: true) != "停止机器人" {
            fatalError("unexpected running menu action title")
        }

        if menuBotActionTitle(isRunning: false) != "启动机器人" {
            fatalError("unexpected stopped menu action title")
        }

        print("selected-ok")
    }
}
