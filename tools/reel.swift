// reel <url> <dir> <w> <h> <seconds> <fps> [js-file]: carica la pagina, esegue js, salva un
// fotogramma ogni 1/fps secondi per <seconds>: una "registrazione" dell'interfaccia vera.
// build: swiftc -O tools/reel.swift -o tools/reel
import Cocoa
import WebKit
let a = CommandLine.arguments
let url = URL(string: a[1])!, dir = a[2], w = Double(a[3])!, h = Double(a[4])!, secs = Double(a[5])!, fps = Double(a[6])!
let js = a.count > 7 ? (try? String(contentsOfFile: a[7], encoding: .utf8)) : nil
try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
final class D: NSObject, WKNavigationDelegate {
  var n = 0, started = Date(), busy = false
  func webView(_ v: WKWebView, didFinish nav: WKNavigation!) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
      if let js = js { v.evaluateJavaScript(js) { _, e in if let e = e { print("JS error:", e) } } }
      self.started = Date()
      Timer.scheduledTimer(withTimeInterval: 1 / fps, repeats: true) { t in
        let el = Date().timeIntervalSince(self.started)
        if el > secs { t.invalidate(); v.evaluateJavaScript("JSON.stringify(window.__errs||[])") { r, _ in print("frames:", self.n, "errors:", r ?? ""); exit(0) }; return }
        if self.busy { return }
        self.busy = true
        let cfg = WKSnapshotConfiguration(); cfg.snapshotWidth = NSNumber(value: w)
        let idx = Int((el * fps).rounded())
        v.takeSnapshot(with: cfg) { img, _ in
          if let img = img, let t = img.tiffRepresentation, let b = NSBitmapImageRep(data: t), let p = b.representation(using: .jpeg, properties: [.compressionFactor: 0.92]) {
            try? p.write(to: URL(fileURLWithPath: String(format: "%@/f%05d.jpg", dir, idx)))
            self.n += 1
          }
          self.busy = false
        }
      }
    }
  }
}
let cfg = WKWebViewConfiguration()
// una finestra fuori schermo e' "inattiva": WebKit rallenterebbe i timer della pagina
if #available(macOS 14.0, *) { cfg.preferences.inactiveSchedulingPolicy = .none }
cfg.userContentController.addUserScript(WKUserScript(source: "window.__errs=[];window.addEventListener('error',e=>__errs.push(e.message));", injectionTime: .atDocumentStart, forMainFrameOnly: true))
let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: w, height: h), styleMask: [.borderless], backing: .buffered, defer: false)
let wv = WKWebView(frame: NSRect(x: 0, y: 0, width: w, height: h), configuration: cfg)
win.contentView = wv; win.setFrameOrigin(NSPoint(x: -10000, y: -10000)); win.orderBack(nil)
let d = D(); wv.navigationDelegate = d; wv.load(URLRequest(url: url))
DispatchQueue.main.asyncAfter(deadline: .now() + secs + 60) { print("timeout"); exit(1) }
app.run()
