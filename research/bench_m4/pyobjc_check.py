# /// script
# requires-python = ">=3.12"
# dependencies = ["pyobjc-framework-Vision", "ocrmac"]
# ///
import Vision, importlib.metadata as md
print("pyobjc-framework-Vision", md.version("pyobjc-framework-Vision"), "ocrmac", md.version("ocrmac"))
for n in ["RecognizeDocumentsRequest","VNRecognizeDocumentsRequest","DetectLensSmudgeRequest","VNDetectLensSmudgeRequest","CalculateImageAestheticsScoresRequest","VNCalculateImageAestheticsScoresRequest","VNRecognizeTextRequest","VNDetectDocumentSegmentationRequest","VNDetectTextRectanglesRequest"]:
    print(n, hasattr(Vision, n))
r = Vision.VNRecognizeTextRequest.alloc().init()
r.setRecognitionLevel_(0)
print("VN langs:", len(r.supportedRecognitionLanguagesAndReturnError_(None)[0]))
import time
from ocrmac import ocrmac
imgs = ["imgs/paper1_clean.png","imgs/paper1_scan.jpg","imgs/guide0_clean.png"]
ocrmac.OCR(imgs[0]).recognize()
for fw in ["vision","livetext"]:
    for lvl in (["accurate","fast"] if fw=="vision" else ["accurate"]):
        t=time.perf_counter()
        for im in imgs*3:
            res = ocrmac.OCR(im, framework=fw, recognition_level=lvl).recognize()
        print(fw, lvl, f"{(time.perf_counter()-t)/9*1000:.0f} ms/page", "n_obs(last)=", len(res))
