import Vision
@available(macOS 26.0, *) func f() { _ = RecognizeDocumentsRequest() }
@available(macOS 15.0, *) func g() { _ = RecognizeTextRequest(); _ = CalculateImageAestheticsScoresRequest(); _ = DetectDocumentSegmentationRequest() }
