package com.memorialtube.springapi.service;

import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class LastClipService {

    private final WorkspaceService workspaceService;
    private final FfmpegService ffmpegService;

    public LastClipService(WorkspaceService workspaceService, FfmpegService ffmpegService) {
        this.workspaceService = workspaceService;
        this.ffmpegService = ffmpegService;
    }

    public String buildLastClip(String imagePath, String outputPath, int durationSeconds, String motionStyle) {
        Path input = workspaceService.resolveUserPath(imagePath);
        if (!Files.exists(input)) {
            throw new IllegalArgumentException("image not found: " + imagePath);
        }
        Path output = workspaceService.resolveUserPath(outputPath);
        ffmpegService.buildLastClip(input, output, durationSeconds, motionStyle);
        return workspaceService.toWorkspaceString(output);
    }
}
