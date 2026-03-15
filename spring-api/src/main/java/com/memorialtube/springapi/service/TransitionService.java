package com.memorialtube.springapi.service;

import com.memorialtube.springapi.config.MemorialTubeProperties;
import com.memorialtube.springapi.service.model.TransitionJobResult;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class TransitionService {

    private final MemorialTubeProperties properties;
    private final WorkspaceService workspaceService;
    private final ImageService imageService;
    private final FfmpegService ffmpegService;

    public TransitionService(
            MemorialTubeProperties properties,
            WorkspaceService workspaceService,
            ImageService imageService,
            FfmpegService ffmpegService
    ) {
        this.properties = properties;
        this.workspaceService = workspaceService;
        this.imageService = imageService;
        this.ffmpegService = ffmpegService;
    }

    public TransitionJobResult buildTransition(
            String imageAPath,
            String imageBPath,
            String outputPath,
            int durationSeconds,
            String prompt,
            String negativePrompt,
            ProgressCallback progressCallback,
            CancellationCheck cancellationCheck
    ) {
        if (durationSeconds != 6 && durationSeconds != 10) {
            throw new IllegalArgumentException("duration_seconds must be one of: 6, 10");
        }
        if (prompt == null || prompt.isBlank()) {
            throw new IllegalArgumentException("prompt is required for transition");
        }
        Path inputA = workspaceService.resolveUserPath(imageAPath);
        Path inputB = workspaceService.resolveUserPath(imageBPath);
        Path output = workspaceService.resolveUserPath(outputPath);
        if (!Files.exists(inputA)) {
            throw new IllegalArgumentException("image_a not found: " + imageAPath);
        }
        if (!Files.exists(inputB)) {
            throw new IllegalArgumentException("image_b not found: " + imageBPath);
        }

        BufferedImage frameA = imageService.buildCanvas(imageService.readRgb(inputA));
        BufferedImage frameB = imageService.buildCanvas(imageService.readRgb(inputB));
        int[] toneA = imageService.averageRgb(frameA);
        int[] toneB = imageService.averageRgb(frameB);
        int[] sharedTone = new int[]{
                (toneA[0] + toneB[0]) / 2,
                (toneA[1] + toneB[1]) / 2,
                (toneA[2] + toneB[2]) / 2
        };
        BufferedImage tonedA = imageService.toneBlend(frameA, sharedTone, 0.12d);
        BufferedImage tonedB = imageService.toneBlend(frameB, sharedTone, 0.12d);

        int totalFrames = Math.max(2, durationSeconds * properties.getTargetFps());
        try {
            Path tempDir = Files.createTempDirectory(workspaceService.tempRoot(), "transition_frames_");
            for (int index = 0; index < totalFrames; index++) {
                if (cancellationCheck != null) {
                    cancellationCheck.check();
                }
                double t = totalFrames == 1 ? 1.0d : (double) index / (double) (totalFrames - 1);
                double eased = imageService.easeInOut(t);
                BufferedImage frame;
                if (index == 0) {
                    frame = tonedA;
                } else if (index == totalFrames - 1) {
                    frame = tonedB;
                } else {
                    double motion = properties.getTransitionMotionScale();
                    BufferedImage movingA = imageService.applyMotion(
                            tonedA,
                            1.0d + (motion * eased),
                            -motion * 0.6d * eased,
                            0.02d * Math.sin(Math.PI * eased)
                    );
                    BufferedImage movingB = imageService.applyMotion(
                            tonedB,
                            1.02d + (motion * (1.0d - eased)),
                            motion * 0.6d * (1.0d - eased),
                            -0.02d * Math.sin(Math.PI * eased)
                    );
                    frame = imageService.blend(movingA, movingB, eased);
                }
                imageService.writePng(frame, tempDir.resolve("frame_%06d.png".formatted(index)));
                if (progressCallback != null && index % Math.max(1, properties.getTransitionFrameProgressStep()) == 0) {
                    int progress = 45 + (int) Math.round((35.0d * index) / (double) totalFrames);
                    progressCallback.update("transition_generate", progress, "transition frame " + (index + 1) + "/" + totalFrames);
                }
            }
            ffmpegService.encodeFrames(tempDir.resolve("frame_%06d.png"), output);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to create transition temp directory", exc);
        }

        String detail = negativePrompt == null || negativePrompt.isBlank()
                ? "java heuristic motion transition"
                : "java heuristic motion transition with prompt/negative prompt accepted";
        return new TransitionJobResult(
                workspaceService.toWorkspaceString(output),
                false,
                false,
                true,
                null,
                detail
        );
    }
}
