// appctl hide|show <pid>: nasconde o riporta davanti un'app (la finestra Chrome dello studio)
// senza permessi di "controllo" (NSRunningApplication, non System Events).
// Build: swiftc -O studio/appctl.swift -o studio/appctl
import AppKit
let a = CommandLine.arguments
guard a.count == 3, let pid = Int32(a[2]), let app = NSRunningApplication(processIdentifier: pid) else {
    FileHandle.standardError.write("usage: appctl hide|show <pid>\n".data(using: .utf8)!); exit(2)
}
switch a[1] {
case "hide": exit(app.hide() ? 0 : 1)
case "show": app.unhide(); exit(app.activate(options: [.activateAllWindows]) ? 0 : 1)
default: exit(2)
}
