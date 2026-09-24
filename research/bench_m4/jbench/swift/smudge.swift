import Foundation
import Vision
import ImageIO
@main struct M { static func main() async {
  for p in CommandLine.arguments.dropFirst() {
    let s = CGImageSourceCreateWithURL(URL(fileURLWithPath: p) as CFURL, nil)!; let img = CGImageSourceCreateImageAtIndex(s, 0, nil)!
    var ts: [Double] = []; var last = ""
    for _ in 0..<5 { let t = Date(); if let o = try? await DetectLensSmudgeRequest().perform(on: img) { last = String(format: "confidence %.3f", o.confidence) } else { last = "ERR" }; ts.append(Date().timeIntervalSince(t)) }
    print(p.split(separator: "/").last!, last, String(format: "median %.0f ms", ts.sorted()[2]*1000))
  }
}}
