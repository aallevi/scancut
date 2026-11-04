// strumento di prova dello studio: fotografa la pagina con WebKit (lo stesso motore di Safari)
// build: swiftc -O tools/snap.swift -o tools/snap
// snap <url> <out.png> <w> <h> <wait-s> [js-file]: carica la pagina, esegue js, fotografa
import Cocoa
import WebKit
let a = CommandLine.arguments
let url = URL(string: a[1])!, out = a[2], w = Double(a[3])!, h = Double(a[4])!, wait = Double(a[5])!
let js = a.count > 6 ? (try? String(contentsOfFile: a[6], encoding: .utf8)) : nil
let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
class D: NSObject, WKNavigationDelegate {
  let wv: WKWebView; let win: NSWindow
  init(_ wv: WKWebView, _ win: NSWindow) { self.wv = wv; self.win = win }
  func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
      if let js = js { webView.evaluateJavaScript(js) { r, e in if let e = e { print("JS error:", e) } else if let r = r { print("JS:", r) } } }
      DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
        webView.evaluateJavaScript("JSON.stringify(window.__errs||[])") { r, _ in print("page errors:", r ?? "") }
        let c = WKSnapshotConfiguration()
        webView.takeSnapshot(with: c) { img, err in
          if let img = img, let t = img.tiffRepresentation, let b = NSBitmapImageRep(data: t), let p = b.representation(using: .png, properties: [:]) {
            try? p.write(to: URL(fileURLWithPath: out)); print("saved", out)
          } else { print("snapshot failed", err as Any) }
          exit(0)
        }
      }
    }
  }
}
let cfg = WKWebViewConfiguration()
let pre = WKUserScript(source: "window.__errs=[];window.addEventListener('error',e=>__errs.push(e.message+' @'+e.lineno));window.addEventListener('unhandledrejection',e=>__errs.push('rej: '+(e.reason&&e.reason.message||e.reason)));", injectionTime: .atDocumentStart, forMainFrameOnly: true)
cfg.userContentController.addUserScript(pre)
let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: w, height: h), styleMask: [.borderless], backing: .buffered, defer: false)
let wv = WKWebView(frame: NSRect(x: 0, y: 0, width: w, height: h), configuration: cfg)
win.contentView = wv
win.setFrameOrigin(NSPoint(x: -10000, y: -10000)); win.orderBack(nil)
let d = D(wv, win); wv.navigationDelegate = d
wv.load(URLRequest(url: url))
DispatchQueue.main.asyncAfter(deadline: .now() + 60) { print("timeout"); exit(1) }
app.run()
