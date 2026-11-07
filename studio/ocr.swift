// ocr <immagine>: il testo che Apple Vision riconosce (in locale), una riga JSON per pezzo:
// {"text": ..., "conf": 0..1, "box": [x, y, w, h]} in pixel, origine in alto a sinistra.
// Build: swiftc -O studio/ocr.swift -o studio/ocr
import Foundation
import Vision
import AppKit
let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot read image\n".data(using: .utf8)!); exit(1)
}
let W = Double(cg.width), H = Double(cg.height)
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
// testi in piu' lingue insieme: la lingua si riconosce riga per riga; la lista resta come suggerimento
req.recognitionLanguages = ["it-IT", "en-US", "fr-FR", "de-DE", "es-ES", "pt-BR"]
if #available(macOS 13.0, *) { req.automaticallyDetectsLanguage = true }
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
for o in req.results ?? [] {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox
    let rec: [String: Any] = ["text": c.string, "conf": Double(c.confidence),
                              "box": [b.minX * W, (1 - b.maxY) * H, b.width * W, b.height * H].map { ($0 * 10).rounded() / 10 }]
    if let d = try? JSONSerialization.data(withJSONObject: rec), let s = String(data: d, encoding: .utf8) { print(s) }
}
