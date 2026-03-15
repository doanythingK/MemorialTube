package com.memorialtube.springapi.api.dto;

import com.memorialtube.springapi.domain.JobStatus;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.time.Instant;
import java.util.List;

public final class JobDtos {

    private JobDtos() {
    }

    public record JobCreateRequest(String jobType) {
        public String resolvedJobType() {
            return jobType == null || jobType.isBlank() ? "test_render" : jobType;
        }
    }

    public record CanvasJobCreateRequest(
            @NotBlank String inputPath,
            @NotBlank String outputPath,
            Boolean fastMode,
            Boolean animalDetection
    ) {
        public boolean resolvedFastMode() {
            return Boolean.TRUE.equals(fastMode);
        }

        public boolean resolvedAnimalDetection() {
            return animalDetection == null || animalDetection;
        }
    }

    public record TransitionJobCreateRequest(
            @NotBlank String imageAPath,
            @NotBlank String imageBPath,
            @NotBlank String outputPath,
            Integer durationSeconds,
            @NotBlank String prompt,
            String negativePrompt
    ) {
        public int resolvedDurationSeconds() {
            return durationSeconds == null ? 6 : durationSeconds;
        }
    }

    public record LastClipJobCreateRequest(
            @NotBlank String imagePath,
            @NotBlank String outputPath,
            Integer durationSeconds,
            String motionStyle
    ) {
        public int resolvedDurationSeconds() {
            return durationSeconds == null ? 4 : durationSeconds;
        }

        public String resolvedMotionStyle() {
            return motionStyle == null || motionStyle.isBlank() ? "zoom_in" : motionStyle;
        }
    }

    public record RenderJobCreateRequest(
            @NotEmpty List<String> clipPaths,
            List<Integer> clipOrders,
            @NotBlank String outputPath,
            String bgmPath,
            @DecimalMin("0.0") @DecimalMax("1.0") Double bgmVolume,
            String callbackUri
    ) {
        public double resolvedBgmVolume() {
            return bgmVolume == null ? 0.15d : bgmVolume;
        }
    }

    public record PipelineJobCreateRequest(
            @NotEmpty List<String> imagePaths,
            @NotBlank String workingDir,
            @NotBlank String finalOutputPath,
            Integer transitionDurationSeconds,
            @NotBlank String transitionPrompt,
            String transitionNegativePrompt,
            Integer lastClipDurationSeconds,
            String lastClipMotionStyle,
            String bgmPath,
            @DecimalMin("0.0") @DecimalMax("1.0") Double bgmVolume
    ) {
        public int resolvedTransitionDurationSeconds() {
            return transitionDurationSeconds == null ? 6 : transitionDurationSeconds;
        }

        public int resolvedLastClipDurationSeconds() {
            return lastClipDurationSeconds == null ? 4 : lastClipDurationSeconds;
        }

        public String resolvedLastClipMotionStyle() {
            return lastClipMotionStyle == null || lastClipMotionStyle.isBlank() ? "zoom_in" : lastClipMotionStyle;
        }

        public double resolvedBgmVolume() {
            return bgmVolume == null ? 0.15d : bgmVolume;
        }
    }

    public record JobEnqueueResponse(String jobId, String taskId, JobStatus status) {
    }

    public record JobRuntimeResponse(
            String jobId,
            String stage,
            int progressPercent,
            String detailMessage,
            boolean cancelRequested,
            Instant createdAt,
            Instant updatedAt
    ) {
    }

    public record JobResponse(
            String id,
            String jobType,
            JobStatus status,
            String errorMessage,
            String resultMessage,
            Instant createdAt,
            Instant updatedAt,
            String stage,
            Integer progressPercent,
            String detailMessage,
            Boolean cancelRequested
    ) {
    }

    public record JobCancelResponse(
            String jobId,
            JobStatus status,
            boolean cancelRequested,
            String stage,
            int progressPercent,
            String detailMessage
    ) {
    }
}
