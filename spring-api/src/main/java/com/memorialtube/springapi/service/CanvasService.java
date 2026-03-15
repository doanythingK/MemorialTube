package com.memorialtube.springapi.service;

import com.memorialtube.springapi.service.model.CanvasJobResult;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class CanvasService {

    private final WorkspaceService workspaceService;
    private final ImageService imageService;

    public CanvasService(WorkspaceService workspaceService, ImageService imageService) {
        this.workspaceService = workspaceService;
        this.imageService = imageService;
    }

    public CanvasJobResult buildCanvas(String inputPath, String outputPath) {
        Path input = workspaceService.resolveUserPath(inputPath);
        if (!Files.exists(input)) {
            throw new IllegalArgumentException("input image not found: " + inputPath);
        }
        Path output = workspaceService.resolveUserPath(outputPath);
        BufferedImage source = imageService.readRgb(input);
        BufferedImage canvas = imageService.buildCanvas(source);
        imageService.writeJpg(canvas, output);
        return new CanvasJobResult(
                workspaceService.toWorkspaceString(output),
                false,
                "java_safe_background",
                true,
                true,
                "blurred background extension"
        );
    }
}
