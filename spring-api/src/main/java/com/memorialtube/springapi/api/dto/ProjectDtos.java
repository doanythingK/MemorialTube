package com.memorialtube.springapi.api.dto;

import com.memorialtube.springapi.domain.ProjectStatus;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;

public final class ProjectDtos {

    private ProjectDtos() {
    }

    public record ProjectCreateRequest(
            @NotBlank String name,
            Integer transitionDurationSeconds,
            @NotBlank String transitionPrompt,
            String transitionNegativePrompt,
            Integer lastClipDurationSeconds,
            String lastClipMotionStyle,
            String bgmPath,
            @DecimalMin("0.0") @DecimalMax("1.0") Double bgmVolume,
            String finalOutputPath
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

    public record ProjectRunRequest(String workingDir, String finalOutputPath) {
    }

    public record ProjectResponse(
            String id,
            String name,
            ProjectStatus status,
            int transitionDurationSeconds,
            String transitionPrompt,
            String transitionNegativePrompt,
            int lastClipDurationSeconds,
            String lastClipMotionStyle,
            String bgmPath,
            double bgmVolume,
            String finalOutputPath,
            Instant createdAt,
            Instant updatedAt
    ) {
    }

    public record AssetResponse(
            String id,
            String projectId,
            int orderIndex,
            String fileName,
            String filePath,
            int width,
            int height,
            Instant createdAt
    ) {
    }
}
