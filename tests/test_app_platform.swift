import Foundation

@main
struct AppPlatformSmokeTest {
    static func main() throws {
        let repoRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let defs = try loadAppPlatforms(from: repoRoot.appendingPathComponent("platforms.json"))

        guard defs.contains(where: { $0.id == "telegram" }) else {
            fatalError("missing telegram")
        }
        guard defs.contains(where: { $0.id == "feishu" }) else {
            fatalError("missing feishu")
        }
        guard let feishu = defs.first(where: { $0.id == "feishu" }) else {
            fatalError("missing feishu definition")
        }
        if feishu.requiredEnvKeys != ["FEISHU_APP_ID", "FEISHU_APP_SECRET"] {
            fatalError("unexpected feishu required env keys")
        }

        print("ok")
    }
}
