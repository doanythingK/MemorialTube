package com.memorialtube.springapi.service.model;

public record CanvasJobResult(
        String outputPath,
        boolean usedOutpaint,
        String adapterName,
        boolean fallbackApplied,
        boolean safetyPassed,
        String fallbackReason
) {
}
