// vision_mask: maschera dei soggetti con Vision di Apple, un'etichetta per oggetto
// uso: vision_mask in.png out.png   (out: grigio, 0 = fondo, 1..n = oggetto n)
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: vision_mask in.png out.png"); exit(2) }
let url = URL(fileURLWithPath: args[1])
guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else { print("cannot read"); exit(1) }

let req = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([req]) } catch { print("vision error: \(error)"); exit(1) }
guard let obs = req.results?.first else { print("instances 0"); exit(3) }

let w = cg.width, h = cg.height
var labels = [UInt8](repeating: 0, count: w * h)
for (k, inst) in obs.allInstances.enumerated() {
    let buf = try obs.generateScaledMaskForImage(forInstances: IndexSet(integer: inst), from: handler)
    CVPixelBufferLockBaseAddress(buf, .readOnly)
    let bw = CVPixelBufferGetWidth(buf), bh = CVPixelBufferGetHeight(buf)
    let stride = CVPixelBufferGetBytesPerRow(buf)
    let base = CVPixelBufferGetBaseAddress(buf)!.assumingMemoryBound(to: Float32.self)
    for y in 0..<min(h, bh) {
        let row = base.advanced(by: y * stride / 4)
        for x in 0..<min(w, bw) where row[x] > 0.5 { labels[y * w + x] = UInt8(min(k + 1, 255)) }
    }
    CVPixelBufferUnlockBaseAddress(buf, .readOnly)
}
let cs = CGColorSpaceCreateDeviceGray()
let ctx = CGContext(data: &labels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                    space: cs, bitmapInfo: CGImageAlphaInfo.none.rawValue)!
let out = ctx.makeImage()!
let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[2]) as CFURL,
                                          UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(dst, out, nil)
CGImageDestinationFinalize(dst)
print("instances \(obs.allInstances.count)")
