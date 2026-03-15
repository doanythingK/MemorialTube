package com.memorialtube.springapi.service;

import com.memorialtube.springapi.config.MemorialTubeProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class FfmpegService {

    private final MemorialTubeProperties properties;
    private final WorkspaceService workspaceService;
    private final HttpClient httpClient = HttpClient.newHttpClient();

    public FfmpegService(MemorialTubeProperties properties, WorkspaceService workspaceService) {
        this.properties = properties;
        this.workspaceService = workspaceService;
    }

    public String versionLine() {
        CommandResult result = execute(List.of(properties.getFfmpegPath(), "-version"), "ffmpeg command failed");
        String[] lines = result.stdout().split("\\R");
        return lines.length == 0 ? "ffmpeg check succeeded" : lines[0];
    }

    public void encodeFrames(Path framePattern, Path outputPath) {
        workspaceService.ensureParent(outputPath);
        List<String> command = List.of(
                properties.getFfmpegPath(),
                "-y",
                "-framerate",
                String.valueOf(properties.getTargetFps()),
                "-i",
                framePattern.toString(),
                "-r",
                String.valueOf(properties.getTargetFps()),
                "-pix_fmt",
                properties.getOutputPixelFormat(),
                "-c:v",
                properties.getOutputVideoCodec(),
                outputPath.toString()
        );
        execute(command, "ffmpeg frame-to-video failed");
    }

    public void buildLastClip(Path imagePath, Path outputPath, int durationSeconds, String motionStyle) {
        workspaceService.ensureParent(outputPath);
        String motion = switch (motionStyle) {
            case "zoom_out" -> "zoompan=z='if(lte(on,1),1.08,max(1.0,zoom-0.0008))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d"
                    .formatted(properties.getTargetWidth(), properties.getTargetHeight(), properties.getTargetFps());
            case "none" -> "fps=%d".formatted(properties.getTargetFps());
            default -> "zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d"
                    .formatted(properties.getTargetWidth(), properties.getTargetHeight(), properties.getTargetFps());
        };
        String vf = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,%s,format=%s"
                .formatted(
                        properties.getTargetWidth(),
                        properties.getTargetHeight(),
                        properties.getTargetWidth(),
                        properties.getTargetHeight(),
                        motion,
                        properties.getOutputPixelFormat()
                );
        List<String> command = List.of(
                properties.getFfmpegPath(),
                "-y",
                "-loop",
                "1",
                "-t",
                String.valueOf(durationSeconds),
                "-i",
                imagePath.toString(),
                "-vf",
                vf,
                "-t",
                String.valueOf(durationSeconds),
                "-r",
                String.valueOf(properties.getTargetFps()),
                "-pix_fmt",
                properties.getOutputPixelFormat(),
                "-c:v",
                properties.getOutputVideoCodec(),
                outputPath.toString()
        );
        execute(command, "ffmpeg last-clip build failed");
    }

    public void normalizeClip(Path inputPath, Path outputPath) {
        workspaceService.ensureParent(outputPath);
        String vf = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black,fps=%d,setsar=1,format=%s"
                .formatted(
                        properties.getTargetWidth(),
                        properties.getTargetHeight(),
                        properties.getTargetWidth(),
                        properties.getTargetHeight(),
                        properties.getTargetFps(),
                        properties.getOutputPixelFormat()
                );
        List<String> command = List.of(
                properties.getFfmpegPath(),
                "-y",
                "-i",
                inputPath.toString(),
                "-vf",
                vf,
                "-an",
                "-r",
                String.valueOf(properties.getTargetFps()),
                "-pix_fmt",
                properties.getOutputPixelFormat(),
                "-c:v",
                properties.getOutputVideoCodec(),
                outputPath.toString()
        );
        execute(command, "ffmpeg normalize clip failed");
    }

    public void concatClips(Path listFile, Path outputPath, Path bgmPath, double bgmVolume) {
        workspaceService.ensureParent(outputPath);
        List<String> command = new ArrayList<>(List.of(
                properties.getFfmpegPath(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                listFile.toString()
        ));
        if (bgmPath != null) {
            command.addAll(List.of(
                    "-stream_loop",
                    "-1",
                    "-i",
                    bgmPath.toString(),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-filter:a",
                    "volume=" + bgmVolume,
                    "-shortest"
            ));
        } else {
            command.addAll(List.of("-map", "0:v:0", "-an"));
        }
        command.addAll(List.of(
                "-r",
                String.valueOf(properties.getTargetFps()),
                "-pix_fmt",
                properties.getOutputPixelFormat(),
                "-c:v",
                properties.getOutputVideoCodec()
        ));
        if (bgmPath != null) {
            command.addAll(List.of("-c:a", "aac"));
        }
        command.add(outputPath.toString());
        execute(command, "ffmpeg final render failed");
    }

    public void notifyCallback(String callbackUri, String payload) {
        HttpRequest request = HttpRequest.newBuilder(URI.create(callbackUri))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                .build();
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 400) {
                throw new IllegalStateException("callback http error: status=" + response.statusCode());
            }
        } catch (IOException exc) {
            throw new IllegalStateException("callback request failed", exc);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("callback request interrupted", exc);
        }
    }

    private CommandResult execute(List<String> command, String defaultErrorMessage) {
        ProcessBuilder processBuilder = new ProcessBuilder(command);
        try {
            Process process = processBuilder.start();
            byte[] stdoutBytes = process.getInputStream().readAllBytes();
            byte[] stderrBytes = process.getErrorStream().readAllBytes();
            int exitCode = process.waitFor();
            String stdout = new String(stdoutBytes, StandardCharsets.UTF_8);
            String stderr = new String(stderrBytes, StandardCharsets.UTF_8);
            if (exitCode != 0) {
                throw new IllegalStateException(stderr.isBlank() ? defaultErrorMessage : stderr.trim());
            }
            return new CommandResult(stdout, stderr);
        } catch (IOException exc) {
            throw new IllegalStateException(defaultErrorMessage, exc);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(defaultErrorMessage, exc);
        }
    }

    private record CommandResult(String stdout, String stderr) {
    }
}
