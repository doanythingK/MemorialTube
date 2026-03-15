package com.memorialtube.springapi.service;

import com.memorialtube.springapi.api.dto.JobDtos;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class RenderService {

    private final WorkspaceService workspaceService;
    private final FfmpegService ffmpegService;

    public RenderService(WorkspaceService workspaceService, FfmpegService ffmpegService) {
        this.workspaceService = workspaceService;
        this.ffmpegService = ffmpegService;
    }

    public String buildFinalRender(
            List<String> clipPaths,
            List<Integer> clipOrders,
            String outputPath,
            String bgmPath,
            double bgmVolume
    ) {
        List<String> ordered = applyClipOrders(clipPaths, clipOrders);
        if (ordered.isEmpty()) {
            throw new IllegalArgumentException("clip_paths must not be empty");
        }
        Path output = workspaceService.resolveUserPath(outputPath);
        try {
            Path tempDir = Files.createTempDirectory(workspaceService.tempRoot(), "render_concat_");
            List<Path> normalizedPaths = new ArrayList<>();
            for (int index = 0; index < ordered.size(); index++) {
                Path clip = workspaceService.resolveUserPath(ordered.get(index));
                if (!Files.exists(clip)) {
                    throw new IllegalArgumentException("clip not found: " + ordered.get(index));
                }
                Path normalized = tempDir.resolve("norm_%04d.mp4".formatted(index));
                ffmpegService.normalizeClip(clip, normalized);
                normalizedPaths.add(normalized);
            }

            Path listFile = tempDir.resolve("clips.txt");
            List<String> lines = normalizedPaths.stream()
                    .map(path -> "file '" + path.toAbsolutePath().normalize().toString().replace("\\", "/") + "'")
                    .toList();
            Files.writeString(listFile, String.join(System.lineSeparator(), lines), StandardCharsets.UTF_8);
            Path bgm = null;
            if (bgmPath != null && !bgmPath.isBlank()) {
                bgm = workspaceService.resolveUserPath(bgmPath);
                if (!Files.exists(bgm)) {
                    throw new IllegalArgumentException("bgm not found: " + bgmPath);
                }
            }
            ffmpegService.concatClips(listFile, output, bgm, bgmVolume);
            return workspaceService.toWorkspaceString(output);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to prepare render inputs", exc);
        }
    }

    private List<String> applyClipOrders(List<String> clipPaths, List<Integer> clipOrders) {
        if (clipOrders == null || clipOrders.isEmpty()) {
            return clipPaths;
        }
        if (clipOrders.size() != clipPaths.size()) {
            throw new IllegalArgumentException("clip_orders length must match clip_paths length");
        }
        List<OrderedClip> pairs = new ArrayList<>();
        for (int index = 0; index < clipPaths.size(); index++) {
            Integer order = clipOrders.get(index);
            if (order == null || order < 1) {
                throw new IllegalArgumentException("clip_orders must be positive integers");
            }
            pairs.add(new OrderedClip(order, index, clipPaths.get(index)));
        }
        pairs.sort((left, right) -> {
            int byOrder = Integer.compare(left.order(), right.order());
            return byOrder != 0 ? byOrder : Integer.compare(left.index(), right.index());
        });
        return pairs.stream().map(OrderedClip::path).toList();
    }

    private record OrderedClip(int order, int index, String path) {
    }
}
