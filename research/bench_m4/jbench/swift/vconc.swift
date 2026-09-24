import Foundation
import Vision
import ImageIO
func load(_ p: String) -> CGImage { let s = CGImageSourceCreateWithURL(URL(fileURLWithPath: p) as CFURL, nil)!; return CGImageSourceCreateImageAtIndex(s, 0, nil)! }
@main struct M { static func main() async {
  let img = load(CommandLine.arguments[1])
  for (name, lvl, lc) in [("fast", RecognizeTextRequest.RecognitionLevel.fast, false), ("accurate", .accurate, true), ("accurate-noLC", .accurate, false)] {
    var r = RecognizeTextRequest(); r.recognitionLevel = lvl; r.usesLanguageCorrection = lc; r.recognitionLanguages = [Locale.Language(identifier: "en-US")]
    let o = (try? await r.perform(on: img)) ?? []
    print(name, "lines:", o.count, "sample:", o.prefix(2).compactMap { $0.topCandidates(1).first?.string })
  }
  for conc in [1, 4, 8] {
    let n = 16; let t = Date()
    await withTaskGroup(of: Void.self) { g in
      var launched = 0
      for _ in 0..<min(conc, n) { launched += 1; g.addTask { var r = RecognizeTextRequest(); r.recognitionLevel = .accurate; _ = try? await r.perform(on: img) } }
      while await g.next() != nil { if launched < n { launched += 1; g.addTask { var r = RecognizeTextRequest(); r.recognitionLevel = .accurate; _ = try? await r.perform(on: img) } } }
    }
    print(String(format: "accurate OCR concurrency %d: %.2f pages/s", conc, Double(n)/Date().timeIntervalSince(t)))
  }
  for conc in [1, 4] {
    let n = 8; let t = Date()
    await withTaskGroup(of: Void.self) { g in
      var launched = 0
      for _ in 0..<min(conc, n) { launched += 1; g.addTask { _ = try? await RecognizeDocumentsRequest().perform(on: img) } }
      while await g.next() != nil { if launched < n { launched += 1; g.addTask { _ = try? await RecognizeDocumentsRequest().perform(on: img) } } }
    }
    print(String(format: "RecognizeDocuments concurrency %d: %.2f pages/s", conc, Double(n)/Date().timeIntervalSince(t)))
  }
}}
