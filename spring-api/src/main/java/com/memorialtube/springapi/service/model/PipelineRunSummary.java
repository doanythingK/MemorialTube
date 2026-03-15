package com.memorialtube.springapi.service.model;

import java.util.List;

public record PipelineRunSummary(
        String finalOutputPath,
        List<String> canvasPaths,
        List<String> transitionPaths,
        String lastClipPath,
        int fallbackCount,
        int canvasFallbackCount,
        int transitionFallbackCount,
        int safetyFailedCount
) {
}
