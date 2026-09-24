# /// script
# requires-python = ">=3.12"
# dependencies = ["pyobjc-framework-Vision", "pyobjc-framework-Quartz"]
# ///
import Vision, Foundation, time
def handler(p):
    url = Foundation.NSURL.fileURLWithPath_(p)
    return Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
for p in ["imgs/guide0_clean.png", "imgs/guide0_clean.png", "imgs/paper1_scan.jpg", "imgs/paper1_photo.jpg"]:
    reqs = {"docs": Vision.VNRecognizeDocumentsRequest.alloc().init(),
            "smudge": Vision.VNDetectLensSmudgeRequest.alloc().init(),
            "seg": Vision.VNDetectDocumentSegmentationRequest.alloc().init(),
            "aesth": Vision.VNCalculateImageAestheticsScoresRequest.alloc().init()}
    out = []
    for k, r in reqs.items():
        h = handler(p); t = time.perf_counter()
        ok, err = h.performRequests_error_([r], None)
        dt = (time.perf_counter()-t)*1000
        res = r.results() or []
        desc = ""
        if res:
            o = res[0]
            if k == "docs":
                meths = [m for m in dir(o) if not m.startswith("_")][:0]
                desc = f"type={type(o).__name__} conf={o.confidence():.2f}"
                try:
                    d = o.document()
                    desc += f" doc={type(d).__name__}"
                except Exception as e:
                    desc += f" document() err {e.__class__.__name__}"
            elif k == "smudge": desc = f"conf={o.confidence():.2f}"
            elif k == "seg": desc = f"conf={o.confidence():.2f}"
            elif k == "aesth": desc = f"overall={o.overallScore():.2f} utility={o.isUtility()}"
        out.append(f"{k} {dt:.0f}ms ok={ok} n={len(res)} {desc}")
    print(p, " | ".join(out))
o = Vision.VNRecognizeDocumentsRequest.alloc().init()
h = handler("imgs/guide0_clean.png"); h.performRequests_error_([o], None)
r = o.results()[0]
print([m for m in dir(r) if not m.startswith("_") and m[0].islower()][:80])
