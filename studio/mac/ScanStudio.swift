// Scan Studio: l'app vera per il Dock. Una finestra WebKit senza cornice (la cornice Vista la
// disegna la pagina), il server dello studio come processo figlio, menu e Dock di macOS.
// Build: studio/mac/build.sh  (crea ~/Applications/Scan Studio.app, firmata ad hoc)

import AppKit
import WebKit

let home = FileManager.default.homeDirectoryForCurrentUser.path
// dove stanno il codice, il Python e le scansioni: li scrive build.sh nell'Info.plist
func conf(_ key: String, _ fallback: String) -> String {
    (Bundle.main.object(forInfoDictionaryKey: key) as? String).flatMap { $0.isEmpty ? nil : $0 } ?? fallback
}
let repo = conf("ScanStudioRepo", home + "/Scans/.scancut")
let python = conf("ScanStudioPython", "/usr/bin/python3")
let scansRoot = conf("ScanStudioRoot", home + "/Scans")
let logDir = scansRoot + "/.scancut/studio-data"
let port = Int(conf("ScanStudioPort", "8765")) ?? 8765          // una seconda app (anteprima) usa un'altra porta
let base = URL(string: "http://127.0.0.1:\(port)/")!

// la barra del titolo disegnata dalla pagina: qui sopra si trascina la finestra
// (lasciando scoperti a destra i pulsanti riduci/ingrandisci/chiudi della cornice Vista)
final class DragStrip: NSView {
    // le schede della pagina stanno a sinistra nella barra del titolo: li' i clic vanno alla pagina
    var tabsWidth: CGFloat = 0
    override var mouseDownCanMoveWindow: Bool { true }
    override func hitTest(_ p: NSPoint) -> NSView? {
        let q = convert(p, from: superview)
        return q.x < tabsWidth ? nil : super.hitTest(p)
    }
    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 { (window as? StudioWindow)?.toggleMax(); return }
        window?.performDrag(with: e)
    }
}

// la finestra ha la forma della cornice Vista: niente bordo di macOS (che arrotonda tutti e
// quattro gli angoli), angoli tondi solo in alto, il vetro sfoca davvero cio' che c'e' dietro
final class StudioWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
    var restore: NSRect?
    // ingrandisci come in Vista: tutto lo schermo utile, e di nuovo com'era
    func toggleMax() {
        guard let vis = screen?.visibleFrame else { return }
        if let r = restore, frame.equalTo(vis) { setFrame(r, display: true, animate: true); restore = nil }
        else { restore = frame; setFrame(vis, display: true, animate: true) }
    }
}

let useLiquidGlass = false     // vedi buildWindow
let RADIUS: CGFloat = 10       // come la cornice disegnata dalla pagina (vista.css html.native .window)

func frameMask(_ size: NSSize) -> NSImage {
    // rettangolo con gli angoli in alto arrotondati (coordinate di AppKit: l'alto e' maxY)
    let img = NSImage(size: size, flipped: false) { r in
        NSColor.black.setFill(); NSBezierPath(roundedRect: r, xRadius: RADIUS, yRadius: RADIUS).fill(); return true
    }
    img.capInsets = NSEdgeInsets(top: RADIUS + 1, left: RADIUS + 1, bottom: RADIUS + 1, right: RADIUS + 1)
    img.resizingMode = .stretch
    return img
}

// bordi per ridimensionare (una finestra senza bordo di macOS non li ha da sola)
final class ResizeEdge: NSView {
    enum Side { case left, right, bottom, bottomLeft, bottomRight }
    let side: Side
    var start = NSRect.zero, startMouse = NSPoint.zero
    init(_ side: Side) { self.side = side; super.init(frame: .zero) }
    required init?(coder: NSCoder) { fatalError() }
    override func resetCursorRects() {
        let c: NSCursor
        switch side {
        case .left, .right: c = .resizeLeftRight
        case .bottom: c = .resizeUpDown
        case .bottomLeft, .bottomRight:
            if #available(macOS 15.0, *) { c = NSCursor.frameResize(position: side == .bottomLeft ? .bottomLeft : .bottomRight, directions: .all) }
            else { c = .crosshair }
        }
        addCursorRect(bounds, cursor: c)
    }
    override func mouseDown(with e: NSEvent) { start = window!.frame; startMouse = NSEvent.mouseLocation }
    override func mouseDragged(with e: NSEvent) {
        guard let w = window else { return }
        let m = NSEvent.mouseLocation, dx = m.x - startMouse.x, dy = m.y - startMouse.y
        var f = start
        if side == .right || side == .bottomRight { f.size.width = max(w.minSize.width, start.width + dx) }
        if side == .left || side == .bottomLeft {
            let nw = max(w.minSize.width, start.width - dx); f.origin.x = start.maxX - nw; f.size.width = nw
        }
        if side == .bottom || side == .bottomLeft || side == .bottomRight {
            let nh = max(w.minSize.height, start.height - dy); f.origin.y = start.maxY - nh; f.size.height = nh
        }
        w.setFrame(f, display: true)
    }
}

final class App: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKUIDelegate, WKNavigationDelegate, NSWindowDelegate, NSUserInterfaceItemSearching {
    var window: NSWindow!
    var web: WKWebView!
    var strip: DragStrip!
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
                p.arguments = ["-I", repo + "/studio.py", "serve", "--port", "\(port)", "--root", scansRoot] + (conf("ScanStudioDev", "") == "1" ? ["--dev"] : [])
                p.currentDirectoryURL = URL(fileURLWithPath: repo)
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
        // la pagina sa di essere nell'app (finestra trasparente, cornice per il vetro) prima di disegnarsi
        cfg.userContentController.addUserScript(WKUserScript(
            source: "document.documentElement.classList.add('native'); window.__scanStudioApp = true;",
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        if #available(macOS 13.3, *) { web.isInspectable = true }
        web.setValue(false, forKey: "drawsBackground")       // niente lampo bianco all'avvio

        window = StudioWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 900),
                              styleMask: [.borderless, .resizable, .miniaturizable],
                              backing: .buffered, defer: false)
        window.title = "Scan Studio"
        window.minSize = NSSize(width: 900, height: 600)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        // (niente collectionBehavior: con .fullScreenPrimary il vetro disegna una riga squadrata agli angoli)
        window.delegate = self
        window.isReleasedWhenClosed = false

        // il vetro: Liquid Glass di macOS (26+) tinto d'azzurro Vista, sotto la pagina; la pagina ci
        // disegna sopra la cornice semitrasparente. Sui macOS piu' vecchi la sfocatura di prima
        let content = NSView()
        // niente ritaglio dei livelli: dentro il vetro un livello ritagliato fa comparire una riga scura
        // squadrata fuori dagli angoli; la forma la danno il vetro e la cornice disegnata dalla pagina
        content.wantsLayer = true
        content.layer?.backgroundColor = .clear
        web.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(web)
        strip = DragStrip()
        strip.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(strip)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor), web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: content.topAnchor), web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            strip.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),     // icona a sinistra libera
            strip.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -110), // pulsanti Vista liberi
            strip.topAnchor.constraint(equalTo: content.topAnchor), strip.heightAnchor.constraint(equalToConstant: 28),
        ])
        let edge: CGFloat = 6, corner: CGFloat = 14
        for (side, l, r, b, wdt, hgt) in [
            (ResizeEdge.Side.left, true, false, false, edge, CGFloat(-1)), (.right, false, true, false, edge, -1),
            (.bottom, false, false, true, -1, edge), (.bottomLeft, true, false, true, corner, corner), (.bottomRight, false, true, true, corner, corner)] {
            let v = ResizeEdge(side); v.translatesAutoresizingMaskIntoConstraints = false; content.addSubview(v)
            var cs: [NSLayoutConstraint] = []
            if l { cs.append(v.leadingAnchor.constraint(equalTo: content.leadingAnchor)) }
            if r { cs.append(v.trailingAnchor.constraint(equalTo: content.trailingAnchor)) }
            if b { cs.append(v.bottomAnchor.constraint(equalTo: content.bottomAnchor)) }
            if wdt > 0 { cs.append(v.widthAnchor.constraint(equalToConstant: wdt)) }
            else { cs += [v.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: corner), v.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -corner)] }
            if hgt > 0 { cs.append(v.heightAnchor.constraint(equalToConstant: hgt)) }
            else { cs += [v.topAnchor.constraint(equalTo: content.topAnchor, constant: 30), v.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -corner)] }
            NSLayoutConstraint.activate(cs)
        }
        // Liquid Glass (NSGlassEffectView) in una finestra senza bordo disegna una riga scura squadrata
        // fuori dagli angoli tondi (macOS 27, nov 2026): per ora la sfocatura classica, stessa forma
        if #available(macOS 26.0, *), useLiquidGlass {
            let glass = NSGlassEffectView()
            glass.style = .regular
            glass.cornerRadius = RADIUS
            glass.tintColor = NSColor(calibratedRed: 0.32, green: 0.55, blue: 0.80, alpha: 0.30)
            glass.contentView = content
            window.contentView = glass
        } else {
            let fx = NSVisualEffectView()
            fx.material = .hudWindow; fx.blendingMode = .behindWindow; fx.state = .active
            fx.maskImage = frameMask(NSSize(width: 64, height: 64))
            content.translatesAutoresizingMaskIntoConstraints = false
            fx.addSubview(content)
            NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo: fx.leadingAnchor), content.trailingAnchor.constraint(equalTo: fx.trailingAnchor),
                                         content.topAnchor.constraint(equalTo: fx.topAnchor), content.bottomAnchor.constraint(equalTo: fx.bottomAnchor)])
            window.contentView = fx
        }
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
        case "max": (window as? StudioWindow)?.toggleMax()
        case "full": window.toggleFullScreen(nil)
        // finestra senza cornice: performClose non fa niente (manca .closable), si chiude da qui
        case "close": if windowShouldClose(window) { NSApp.terminate(nil) }
        // fin dove arrivano le schede (in punti, dal bordo sinistro della striscia)
        case "tabs": strip?.tabsWidth = CGFloat(((m.body as? [String: Any])?["w"] as? NSNumber)?.doubleValue ?? 0)
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
        NSApp.windowsMenu = main.items.last?.submenu
        // Aiuto: macOS ci mette la sua casella di ricerca; i risultati vengono anche dallo studio
        sub("Help", [
            item("Scan Studio Help", #selector(App.helpHome), "?"),
            item("Keyboard Shortcuts", #selector(App.helpShortcuts), "/"),
            item("Ask Claude…", #selector(App.askClaude)),
            .separator(),
            item("Report a Problem…", #selector(App.reportProblem)),
        ])
        NSApp.helpMenu = main.items.last?.submenu
        NSApp.mainMenu = main
        NSApp.registerUserInterfaceItemSearchHandler(self)
    }

    @objc func reload() { web.reload() }
    func js(_ code: String) { window.makeKeyAndOrderFront(nil); web.evaluateJavaScript(code, completionHandler: nil) }
    @objc func helpHome() { js("openHelp()") }
    @objc func helpShortcuts() { js("showHelpTopic('Shortcuts (editor)')") }
    @objc func askClaude() { js("toggleChat(true, 'claude')") }
    @objc func reportProblem() { NSWorkspace.shared.open(URL(string: "https://github.com/aallevi/scancut/issues")!) }

    // niente invalidateShadow(): ricalcolata dal contenuto, l'ombra diventa un rettangolo con una
    // riga scura squadrata fuori dagli angoli tondi; quella del vetro segue gia' la sua forma

    static let loadingPage = """
    <html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0b3a52;
    font:13px 'Segoe UI',Tahoma,sans-serif;color:#cfe6f5">Starting Scan Studio…</body></html>
    """
    static let errorPage = """
    <html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0b3a52;
    font:13px 'Segoe UI',Tahoma,sans-serif;color:#fff;text-align:center">
    <div>Scan Studio could not start.<br><br>See \(logDir)/server.log</div></body></html>
    """
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()

// la casella di ricerca del menu Aiuto di macOS: argomenti d'aiuto e scansioni dallo studio
func jsString(_ v: String) -> String {
    let d = try! JSONSerialization.data(withJSONObject: [v]); let a = String(data: d, encoding: .utf8)!
    return String(a.dropFirst().dropLast())
}
extension App {
    func searchForItems(withSearch q: String, resultLimit: Int, matchedItemHandler: @escaping ([Any]) -> Void) {
        var c = URLComponents(url: base.appendingPathComponent("api/search"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "q", value: q)]
        URLSession.shared.dataTask(with: c.url!) { data, _, _ in
            var out: [[String: String]] = []
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                for x in (j["help"] as? [[String: Any]]) ?? [] { let t = (x["title"] as? String) ?? ""; out.append(["title": "Help: " + t, "topic": t]) }
                for x in (j["files"] as? [[String: Any]]) ?? [] { out.append(["title": "Open " + ((x["name"] as? String) ?? ""), "rel": (x["rel"] as? String) ?? ""]) }
            }
            out.append(["title": "Ask the assistant: " + q, "ask": q])
            matchedItemHandler(Array(out.prefix(resultLimit)))
        }.resume()
    }
    func localizedTitles(forItem item: Any) -> [String] { [((item as? [String: String])?["title"]) ?? ""] }
    func performAction(forItem item: Any) {
        guard let x = item as? [String: String] else { return }
        if let t = x["topic"] { js("showHelpTopic(" + jsString(t) + ")") }
        else if let r = x["rel"] { js("openScan(" + jsString(r) + ")") }
        else if let q = x["ask"] { js("openHelp(" + jsString(q) + ")") }
    }
    func showAllHelpTopics(forSearch q: String) { js("openHelp(" + jsString(q) + ")") }
}
