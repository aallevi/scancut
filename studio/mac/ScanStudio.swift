// Scan Studio: l'app vera per il Dock. Una finestra WebKit senza cornice (la cornice Vista la
// disegna la pagina), il server dello studio come processo figlio, menu e Dock di macOS.
// Build: studio/mac/build.sh  (crea ~/Applications/Scan Studio.app, firmata ad hoc)

import AppKit
import WebKit

let home = FileManager.default.homeDirectoryForCurrentUser.path
let repo = home + "/Scans/.scancut"
let python = "/opt/miniconda3/bin/python3"
let port = 8765
let base = URL(string: "http://127.0.0.1:\(port)/")!

// la barra del titolo disegnata dalla pagina: qui sopra si trascina la finestra
// (lasciando scoperti a destra i pulsanti riduci/ingrandisci/chiudi della cornice Vista)
final class DragStrip: NSView {
    override var mouseDownCanMoveWindow: Bool { true }
    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 { window?.zoom(nil); return }
        window?.performDrag(with: e)
    }
}

final class App: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKUIDelegate, WKNavigationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var quitting = false

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        buildWindow()
        startServer { [weak self] ok in
            guard let self else { return }
            if ok { self.web.load(URLRequest(url: base)) }
            else { self.web.loadHTMLString(Self.errorPage, baseURL: nil) }
        }
    }

    // ------------------------------------------------------------ server
    func ping() -> Bool {
        var req = URLRequest(url: base.appendingPathComponent("api/ping"), timeoutInterval: 1)
        req.httpMethod = "GET"
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        URLSession.shared.dataTask(with: req) { _, r, _ in
            ok = (r as? HTTPURLResponse)?.statusCode == 200; sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 2)
        return ok
    }

    func startServer(done: @escaping (Bool) -> Void) {
        DispatchQueue.global().async {
            // gia' acceso (a mano o da un'altra finestra): si usa quello e non lo si spegne
            if !self.ping() {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: python)
                p.arguments = ["-I", repo + "/studio.py", "serve", "--port", "\(port)"]
                p.currentDirectoryURL = URL(fileURLWithPath: repo)
                let logDir = repo + "/studio-data"
                try? FileManager.default.createDirectory(atPath: logDir, withIntermediateDirectories: true)
                let log = logDir + "/server.log"
                if !FileManager.default.fileExists(atPath: log) { FileManager.default.createFile(atPath: log, contents: nil) }
                if let h = FileHandle(forWritingAtPath: log) { h.seekToEndOfFile(); p.standardOutput = h; p.standardError = h }
                do { try p.run(); self.server = p } catch { DispatchQueue.main.async { done(false) }; return }
            }
            for _ in 0..<120 {                       // fino a 30 s
                if self.ping() { DispatchQueue.main.async { done(true) }; return }
                Thread.sleep(forTimeInterval: 0.25)
            }
            DispatchQueue.main.async { done(false) }
        }
    }

    // ------------------------------------------------------------ finestra
    func buildWindow() {
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: "studio")
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        if #available(macOS 13.3, *) { web.isInspectable = true }
        web.setValue(false, forKey: "drawsBackground")       // niente lampo bianco all'avvio

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        for b in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] { window.standardWindowButton(b)?.isHidden = true }
        window.title = "Scan Studio"
        window.minSize = NSSize(width: 900, height: 600)
        window.backgroundColor = NSColor(red: 0.04, green: 0.2, blue: 0.29, alpha: 1)
        window.delegate = self
        window.isReleasedWhenClosed = false

        let content = NSView()
        web.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(web)
        let strip = DragStrip()
        strip.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(strip)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor), web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: content.topAnchor), web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            strip.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),     // icona a sinistra libera
            strip.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -110), // pulsanti Vista liberi
            strip.topAnchor.constraint(equalTo: content.topAnchor), strip.heightAnchor.constraint(equalToConstant: 28),
        ])
        window.contentView = content
        window.setFrameAutosaveName("ScanStudioMain")
        if !window.setFrameUsingName("ScanStudioMain") { window.center() }
        window.makeKeyAndOrderFront(nil)
        web.loadHTMLString(Self.loadingPage, baseURL: nil)
    }

    // dalla pagina: i pulsanti della cornice Vista
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let cmd = (m.body as? [String: Any])?["cmd"] as? String else { return }
        switch cmd {
        case "min": window.miniaturize(nil)
        case "max": window.zoom(nil)
        case "full": window.toggleFullScreen(nil)
        case "close": window.performClose(nil)
        default: break
        }
    }

    // chiudere: prima si salvano i ritocchi in sospeso, poi si esce
    func windowShouldClose(_ w: NSWindow) -> Bool {
        if quitting { return true }
        quitting = true
        web.callAsyncJavaScript("if (typeof flushSave === 'function') { await flushSave(); } return 1;",
                                arguments: [:], in: nil, in: .page) { _ in NSApp.terminate(nil) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { NSApp.terminate(nil) }   // al massimo 3 s
        return false
    }

    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if window.isMiniaturized { window.deminiaturize(nil) }
        window.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        quitting = true                                  // ⌘Q: salva e poi esci
        web.callAsyncJavaScript("if (typeof flushSave === 'function') { await flushSave(); } return 1;",
                                arguments: [:], in: nil, in: .page) { _ in s.reply(toApplicationShouldTerminate: true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { s.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }

    func applicationWillTerminate(_ n: Notification) {
        // solo il server partito da qui: SIGTERM, il processo di SAM esce da solo quando il server se ne va
        if let p = server, p.isRunning { p.terminate(); p.waitUntilExit() }
    }

    // confirm() e alert() della pagina, come finestre di macOS
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage msg: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = msg; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage msg: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = msg
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }
    // i collegamenti esterni (se mai) nel browser, non qui
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, let h = u.host, h != "127.0.0.1", h != "localhost", a.navigationType == .linkActivated {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    // ------------------------------------------------------------ menu
    func buildMenu() {
        let main = NSMenu()
        func sub(_ title: String, _ items: [NSMenuItem]) {
            let it = NSMenuItem(); let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }; it.submenu = m; main.addItem(it)
        }
        func item(_ t: String, _ a: Selector?, _ k: String = "", _ mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: a, keyEquivalent: k); i.keyEquivalentModifierMask = mods; return i
        }
        sub("Scan Studio", [
            item("About Scan Studio", #selector(NSApplication.orderFrontStandardAboutPanel(_:))),
            .separator(),
            item("Hide Scan Studio", #selector(NSApplication.hide(_:)), "h"),
            item("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Show All", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item("Quit Scan Studio", #selector(NSApplication.terminate(_:)), "q"),
        ])
        // la modifica del testo nei campi; ⌘Z/⇧⌘Z restano alla pagina (annulla dei ritocchi)
        sub("Edit", [
            item("Cut", #selector(NSText.cut(_:)), "x"), item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"), item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        sub("View", [
            item("Reload", #selector(App.reload), "r"),
            item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])
        sub("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Zoom", #selector(NSWindow.performZoom(_:))),
            .separator(),
            item("Bring All to Front", #selector(NSApplication.arrangeInFront(_:))),
        ])
        NSApp.mainMenu = main
        NSApp.windowsMenu = main.items.last?.submenu
    }

    @objc func reload() { web.reload() }

    static let loadingPage = """
    <html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0b3a52;
    font:13px 'Segoe UI',Tahoma,sans-serif;color:#cfe6f5">Starting Scan Studio…</body></html>
    """
    static let errorPage = """
    <html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0b3a52;
    font:13px 'Segoe UI',Tahoma,sans-serif;color:#fff;text-align:center">
    <div>Scan Studio could not start.<br><br>See ~/Scans/.scancut/studio-data/server.log</div></body></html>
    """
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
