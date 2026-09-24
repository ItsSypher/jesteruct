# /// script
# requires-python = ">=3.12"
# dependencies = ["pyobjc-framework-Vision"]
# ///
import Vision, Foundation
o = Vision.VNRecognizeDocumentsRequest.alloc().init()
h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(Foundation.NSURL.fileURLWithPath_("imgs/guide0_clean.png"), {})
h.performRequests_error_([o], None); r = o.results()[0]
own = set(dir(r)) - set(dir(Vision.VNObservation.alloc().init()))
print(sorted(m for m in own if not m.startswith("_") and not m.startswith(("ab","ck","ax","bs","ams","ak"))))
print([n for n in dir(Vision) if "DocumentObservationBlockType" in n or n.startswith("VNDocumentBlock")][:30])
