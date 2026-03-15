package com.memorialtube.springapi.service.model;

public record TransitionJobResult(
        String outputPath,
        boolean usedGenerative,
        boolean fallbackApplied,
        boolean safetyPassed,
        String fallbackReason,
        String safetyMessage
) {
}
