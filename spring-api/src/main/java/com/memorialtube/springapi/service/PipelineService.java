package com.memorialtube.springapi.service;

import com.memorialtube.springapi.service.model.CanvasJobResult;
import com.memorialtube.springapi.service.model.PipelineRunSummary;
import com.memorialtube.springapi.service.model.TransitionJobResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PipelineService {

    private final WorkspaceService workspaceService;
    private final CanvasService canvasService;
    private final TransitionService transitionService;
    private final LastClipService lastClipService;
    private final RenderService renderService;

    public PipelineService(
            WorkspaceService workspaceService,
            CanvasService canvasService,
            TransitionService transitionService,
            LastClipService lastClipService,
            RenderService renderService
    ) {
        this.workspaceService = workspaceService;
        this.canvasService = canvasService;
        this.transitionService = transitionService;
        this.lastClipService = lastClipService;
        this.renderService = renderService;
    }

    public PipelineRunSummary runPipeline(
            List<String> imagePaths,
            String workingDir,
            String finalOutputPath,
            int transitionDurationSeconds,
            String transitionPrompt,
            String transitionNegativePrompt,
            int lastClipDurationSeconds,
            String lastClipMotionStyle,
            String bgmPath,
            double bgmVolume,
            ProgressCallback progressCallback,
            CancellationCheck cancellationCheck
    ) {
        if (imagePaths == null || imagePaths.isEmpty()) {
            throw new IllegalArgumentException("image_paths must not be empty");
        }
        if (transitionPrompt == null || transitionPrompt.isBlank()) {
            throw new IllegalArgumentException("transition_prompt is required");
        }
        Path root = workspaceService.resolveUserPath(workingDir);
        Path canvasDir = root.resolve("canvas");
        Path transitionDir = root.resolve("transitions");
        Path lastDir = root.resolve("last");
        Path renderDir = root.resolve("render");
        try {
            Files.createDirectories(canvasDir);
            Files.createDirectories(transitionDir);
            Files.createDirectories(lastDir);
            Files.createDirectories(renderDir);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to create pipeline directories", exc);
        }

        List<String> canvasPaths = new ArrayList<>();
        List<String> transitionPaths = new ArrayList<>();
        int fallbackCount = 0;
        int canvasFallbackCount = 0;
        int transitionFallbackCount = 0;
        int safetyFailedCount = 0;

        emit(progressCallback, "pipeline_prepare", 1, "starting pipeline");
        check(cancellationCheck);
        emit(progressCallback, "canvas_start", 5, "canvas start: " + imagePaths.size() + " image(s)");
        for (int index = 0; index < imagePaths.size(); index++) {
            check(cancellationCheck);
            emit(progressCallback, "canvas", 6 + (int) ((33.0d * index) / Math.max(1, imagePaths.size())), "canvas " + (index + 1) + "/" + imagePaths.size());
            CanvasJobResult canvasResult = canvasService.buildCanvas(
                    imagePaths.get(index),
                    canvasDir.resolve("canvas_%04d.jpg".formatted(index)).toString()
            );
            canvasPaths.add(canvasResult.outputPath());
            if (canvasResult.fallbackApplied()) {
                fallbackCount++;
                canvasFallbackCount++;
            }
            if (!canvasResult.safetyPassed()) {
                safetyFailedCount++;
            }
        }
        emit(progressCallback, "canvas_done", 40, "canvas done: " + canvasPaths.size() + " image(s)");

        if (canvasPaths.size() >= 2) {
            emit(progressCallback, "transition_start", 45, "transition start: " + (canvasPaths.size() - 1) + " clip(s)");
            for (int index = 0; index < canvasPaths.size() - 1; index++) {
                check(cancellationCheck);
                emit(progressCallback, "transition", 46 + (int) ((28.0d * index) / Math.max(1, canvasPaths.size() - 1)), "transition " + (index + 1) + "/" + (canvasPaths.size() - 1));
                TransitionJobResult transitionResult = transitionService.buildTransition(
                        canvasPaths.get(index),
                        canvasPaths.get(index + 1),
                        transitionDir.resolve("transition_%04d.mp4".formatted(index)).toString(),
                        transitionDurationSeconds,
                        transitionPrompt,
                        transitionNegativePrompt,
                        null,
                        cancellationCheck
                );
                transitionPaths.add(transitionResult.outputPath());
                if (transitionResult.fallbackApplied()) {
                    fallbackCount++;
                    transitionFallbackCount++;
                }
                if (!transitionResult.safetyPassed()) {
                    safetyFailedCount++;
                }
            }
            emit(progressCallback, "transition_done", 75, "transition done: " + transitionPaths.size() + " clip(s)");
        } else {
            emit(progressCallback, "transition_skipped", 75, "transition skipped: single image");
        }

        check(cancellationCheck);
        emit(progressCallback, "last_clip_start", 82, "building last clip");
        String lastClipPath = lastClipService.buildLastClip(
                canvasPaths.get(canvasPaths.size() - 1),
                lastDir.resolve("last_clip.mp4").toString(),
                lastClipDurationSeconds,
                lastClipMotionStyle
        );
        emit(progressCallback, "last_clip_done", 90, "last clip completed");

        check(cancellationCheck);
        emit(progressCallback, "render_start", 92, "building final render");
        List<String> clips = new ArrayList<>(transitionPaths);
        clips.add(lastClipPath);
        String finalPath = renderService.buildFinalRender(clips, null, finalOutputPath, bgmPath, bgmVolume);
        emit(progressCallback, "render_done", 99, "final render completed");
        emit(progressCallback, "completed", 100, "pipeline completed");

        return new PipelineRunSummary(
                finalPath,
                canvasPaths,
                transitionPaths,
                lastClipPath,
                fallbackCount,
                canvasFallbackCount,
                transitionFallbackCount,
                safetyFailedCount
        );
    }

    private void emit(ProgressCallback progressCallback, String stage, int progress, String detail) {
        if (progressCallback != null) {
            progressCallback.update(stage, progress, detail);
        }
    }

    private void check(CancellationCheck cancellationCheck) {
        if (cancellationCheck != null) {
            cancellationCheck.check();
        }
    }
}
