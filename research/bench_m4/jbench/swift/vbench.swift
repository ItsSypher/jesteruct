import Foundation
import Vision
import CoreImage
import ImageIO

func load(_ p: String) -> CGImage {
  let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: p) as CFURL, nil)!
  return CGImageSourceCreateImageAtIndex(src, 0, nil)!
}
func timeit(_ label: String, _ n: Int, _ f: () async throws -> String) async {
  var ts: [Double] = []; var last = ""
  for _ in 0..<n { let t = Date(); last = (try? await f()) ?? "ERR"; ts.append(Date().timeIntervalSince(t)) }
  let s = ts.dropFirst().sorted(); let med = s[s.count/2]
  print(String(format: "%@: first %.0f ms, median %.0f ms (n=%d) -> %@", label, ts[0]*1000, med*1000, n-1, last))
}
@main struct Main { static func main() async {
let paths = CommandLine.arguments.dropFirst()
for p in paths {
  let img = load(p); print("== \(p) \(img.width)x\(img.height)")
  await timeit("RecognizeTextRequest fast", 6) {
    var r = RecognizeTextRequest(); r.recognitionLevel = .fast
    let obs = try await r.perform(on: img)
    let confs = obs.compactMap { $0.topCandidates(1).first?.confidence }
    return "\(obs.count) lines, conf distinct=\(Set(confs.map{ String(format: "%.2f",$0) }).sorted().prefix(6))"
  }
  await timeit("RecognizeTextRequest accurate", 4) {
    var r = RecognizeTextRequest(); r.recognitionLevel = .accurate; r.usesLanguageCorrection = true
    let obs = try await r.perform(on: img)
    let confs = obs.compactMap { $0.topCandidates(1).first?.confidence }
    return "\(obs.count) lines, conf distinct=\(Set(confs.map{ String(format: "%.2f",$0) }).sorted().prefix(6))"
  }
  await timeit("RecognizeDocumentsRequest", 4) {
    let r = RecognizeDocumentsRequest()
    let obs = try await r.perform(on: img)
    guard let d = obs.first?.document else { return "no doc" }
    return "paragraphs=\(d.paragraphs.count) tables=\(d.tables.count) lists=\(d.lists.count) barcodes=\(d.barcodes.count) lines=\(d.text.lines.count)"
  }
  await timeit("DetectDocumentSegmentationRequest", 6) {
    let r = DetectDocumentSegmentationRequest()
    let o = try await r.perform(on: img)
    guard let q = o else { return "none" }
    return String(format: "conf %.2f TL(%.2f,%.2f) BR(%.2f,%.2f)", q.confidence, q.topLeft.x, q.topLeft.y, q.bottomRight.x, q.bottomRight.y)
  }
  await timeit("CalculateImageAestheticsScoresRequest", 6) {
    let r = CalculateImageAestheticsScoresRequest()
    let o = try await r.perform(on: img)
    return String(format: "overall %.3f isUtility %@", o.overallScore, o.isUtility ? "true" : "false")
  }
  await timeit("DetectTextRectanglesRequest", 6) {
    let r = DetectTextRectanglesRequest()
    let o = try await r.perform(on: img)
    return "\(o.count) text rects"
  }
}
}}
