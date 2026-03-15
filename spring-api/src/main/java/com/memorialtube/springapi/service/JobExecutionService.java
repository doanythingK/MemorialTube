package com.memorialtube.springapi.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.memorialtube.springapi.api.dto.JobDtos;
import com.memorialtube.springapi.api.dto.ProjectDtos;
import com.memorialtube.springapi.domain.ProjectStatus;
import com.memorialtube.springapi.entity.JobEntity;
import com.memorialtube.springapi.entity.ProjectEntity;
import com.memorialtube.springapi.service.model.CanvasJobResult;
import com.memorialtube.springapi.service.model.PipelineRunSummary;
import com.memorialtube.springapi.service.model.TransitionJobResult;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class JobExecutionService {

    private final Executor executor;
    private final ObjectMapper objectMapper;
    private final JobService jobService;
    private final ProjectService projectService;
    private final FfmpegService ffmpegService;
    private final CanvasService canvasService;
    private final TransitionService transitionService;
    private final LastClipService lastClipService;
    private final RenderService renderService;
    private final PipelineService pipelineService;

    public JobExecutionService(
            @Qualifier("jobTaskExecutor") Executor executor,
            ObjectMapper objectMapper,
            JobService jobService,
            ProjectService projectService,
            FfmpegService ffmpegService,
            CanvasService canvasService,
            TransitionService transitionService,
            LastClipService lastClipService,
            RenderService renderService,
            PipelineService pipelineService
    ) {
        this.executor = executor;
        this.objectMapper = objectMapper;
        this.jobService = jobService;
        this.projectService = projectService;
        this.ffmpegService = ffmpegService;
        this.canvasService = canvasService;
        this.transitionService = transitionService;
        this.lastClipService = lastClipService;
        this.renderService = renderService;
        this.pipelineService = pipelineService;
    }

    public JobDtos.JobEnqueueResponse enqueueTestJob(JobDtos.JobCreateRequest request) {
        JobEntity job = jobService.createJob(request == null ? "test_render" : request.resolvedJobType());
        executor.execute(() -> runTestJob(job.getId()));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    public JobDtos.JobEnqueueResponse enqueueCanvasJob(JobDtos.CanvasJobCreateRequest request) {
        JobEntity job = jobService.createJob("canvas");
        executor.execute(() -> runCanvasJob(job.getId(), request));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    public JobDtos.JobEnqueueResponse enqueueTransitionJob(JobDtos.TransitionJobCreateRequest request) {
        JobEntity job = jobService.createJob("transition");
        executor.execute(() -> runTransitionJob(job.getId(), request));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    public JobDtos.JobEnqueueResponse enqueueLastClipJob(JobDtos.LastClipJobCreateRequest request) {
        JobEntity job = jobService.createJob("last_clip");
        executor.execute(() -> runLastClipJob(job.getId(), request));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    public JobDtos.JobEnqueueResponse enqueueRenderJob(JobDtos.RenderJobCreateRequest request) {
        JobEntity job = jobService.createJob("render");
        executor.execute(() -> runRenderJob(job.getId(), request));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    public JobDtos.JobEnqueueResponse enqueuePipelineJob(JobDtos.PipelineJobCreateRequest request, String projectId) {
        JobEntity job = jobService.createJob("pipeline");
        if (projectId != null) {
            projectService.createProjectRun(projectId, job.getId());
            projectService.setProjectStatus(projectId, ProjectStatus.RUNNING);
        }
        executor.execute(() -> runPipelineJob(job.getId(), request, projectId));
        return new JobDtos.JobEnqueueResponse(job.getId(), job.getId(), job.getStatus());
    }

    private void runTestJob(String jobId) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "test_start", 5, "checking ffmpeg");
            ensureNotCanceled(jobId);
            String resultMessage = ffmpegService.versionLine();
            jobService.updateRuntime(jobId, "test_done", 100, resultMessage);
            jobService.markSucceeded(jobId, resultMessage);
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
        }
    }

    private void runCanvasJob(String jobId, JobDtos.CanvasJobCreateRequest request) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "canvas_start", 5, "starting canvas");
            ensureNotCanceled(jobId);
            jobService.updateRuntime(jobId, "canvas_generate", 45, "running background extension");
            CanvasJobResult result = canvasService.buildCanvas(request.inputPath(), request.outputPath());
            ensureNotCanceled(jobId);
            String message = "canvas done: outpaint=%s, adapter=%s, fast_mode=%s, animal_detection=%s, fallback=%s, safety=%s, reason=%s"
                    .formatted(
                            result.usedOutpaint(),
                            result.adapterName(),
                            request.resolvedFastMode(),
                            request.resolvedAnimalDetection(),
                            result.fallbackApplied(),
                            result.safetyPassed(),
                            result.fallbackReason()
                    );
            jobService.updateRuntime(jobId, "canvas_done", 100, message);
            jobService.markSucceeded(jobId, message);
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
        }
    }

    private void runTransitionJob(String jobId, JobDtos.TransitionJobCreateRequest request) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "transition_start", 5, "starting transition");
            ensureNotCanceled(jobId);
            TransitionJobResult result = transitionService.buildTransition(
                    request.imageAPath(),
                    request.imageBPath(),
                    request.outputPath(),
                    request.resolvedDurationSeconds(),
                    request.prompt(),
                    request.negativePrompt(),
                    (stage, progress, detail) -> jobService.updateRuntime(jobId, stage, progress, detail),
                    () -> ensureNotCanceled(jobId)
            );
            ensureNotCanceled(jobId);
            String message = "transition done: duration=%ss, generative=%s, fallback=%s, safety=%s, reason=%s, output=%s"
                    .formatted(
                            request.resolvedDurationSeconds(),
                            result.usedGenerative(),
                            result.fallbackApplied(),
                            result.safetyPassed(),
                            result.fallbackReason() == null ? "none" : result.fallbackReason(),
                            result.outputPath()
                    );
            jobService.updateRuntime(jobId, "transition_done", 100, message);
            jobService.markSucceeded(jobId, message);
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
        }
    }

    private void runLastClipJob(String jobId, JobDtos.LastClipJobCreateRequest request) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "last_clip_start", 5, "starting last clip");
            ensureNotCanceled(jobId);
            String output = lastClipService.buildLastClip(
                    request.imagePath(),
                    request.outputPath(),
                    request.resolvedDurationSeconds(),
                    request.resolvedMotionStyle()
            );
            ensureNotCanceled(jobId);
            String message = "last clip done: duration=%ss, motion=%s, output=%s"
                    .formatted(request.resolvedDurationSeconds(), request.resolvedMotionStyle(), output);
            jobService.updateRuntime(jobId, "last_clip_done", 100, message);
            jobService.markSucceeded(jobId, message);
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
        }
    }

    private void runRenderJob(String jobId, JobDtos.RenderJobCreateRequest request) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "render_start", 5, "starting final render");
            ensureNotCanceled(jobId);
            jobService.updateRuntime(jobId, "render_concat", 45, "concatenating clips");
            String output = renderService.buildFinalRender(
                    request.clipPaths(),
                    request.clipOrders(),
                    request.outputPath(),
                    request.bgmPath(),
                    request.resolvedBgmVolume()
            );
            ensureNotCanceled(jobId);
            String message = "final render done: clips=%s, bgm=%s, output=%s"
                    .formatted(request.clipPaths().size(), request.bgmPath() == null ? "no" : "yes", output);
            jobService.updateRuntime(jobId, "render_done", 100, message);
            jobService.markSucceeded(jobId, message);
            if (request.callbackUri() != null && !request.callbackUri().isBlank()) {
                sendCallback(jobId, request.callbackUri(), output, message);
            }
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
        }
    }

    private void runPipelineJob(String jobId, JobDtos.PipelineJobCreateRequest request, String projectId) {
        try {
            jobService.beginProcessing(jobId);
            jobService.updateRuntime(jobId, "pipeline_start", 1, "pipeline started");
            ensureNotCanceled(jobId);
            PipelineRunSummary summary = pipelineService.runPipeline(
                    request.imagePaths(),
                    request.workingDir(),
                    request.finalOutputPath(),
                    request.resolvedTransitionDurationSeconds(),
                    request.transitionPrompt(),
                    request.transitionNegativePrompt(),
                    request.resolvedLastClipDurationSeconds(),
                    request.resolvedLastClipMotionStyle(),
                    request.bgmPath(),
                    request.resolvedBgmVolume(),
                    (stage, progress, detail) -> jobService.updateRuntime(jobId, stage, progress, detail),
                    () -> ensureNotCanceled(jobId)
            );
            String message = "pipeline done: images=%s, transitions=%s, fallbacks=%s, safety_failed=%s, output=%s"
                    .formatted(
                            request.imagePaths().size(),
                            summary.transitionPaths().size(),
                            summary.fallbackCount(),
                            summary.safetyFailedCount(),
                            summary.finalOutputPath()
                    );
            jobService.updateRuntime(jobId, "pipeline_done", 100, message);
            jobService.markSucceeded(jobId, message);
            if (projectId != null) {
                projectService.setProjectStatus(projectId, ProjectStatus.COMPLETED);
            }
        } catch (JobCanceledException exc) {
            jobService.markCanceled(jobId, exc.getMessage());
            if (projectId != null) {
                projectService.setProjectStatus(projectId, ProjectStatus.FAILED);
            }
        } catch (Exception exc) {
            jobService.markFailed(jobId, exc.getMessage());
            if (projectId != null) {
                projectService.setProjectStatus(projectId, ProjectStatus.FAILED);
            }
        }
    }

    private void ensureNotCanceled(String jobId) {
        if (jobService.isCancelRequested(jobId)) {
            throw new JobCanceledException("canceled by user");
        }
    }

    private void sendCallback(String jobId, String callbackUri, String outputPath, String resultMessage) {
        try {
            jobService.updateRuntime(jobId, "render_callback", 100, "sending callback");
            String payload = objectMapper.writeValueAsString(new CallbackPayload(
                    jobId,
                    "succeeded",
                    outputPath,
                    resultMessage,
                    Instant.now().toString()
            ));
            ffmpegService.notifyCallback(callbackUri, payload);
            jobService.updateRuntime(jobId, "render_callback_done", 100, "callback sent");
        } catch (Exception exc) {
            jobService.updateRuntime(jobId, "render_callback_failed", 100, "callback failed: " + exc.getMessage());
        }
    }

    public JobDtos.JobEnqueueResponse enqueueProjectRun(ProjectEntity project, ProjectDtos.ProjectRunRequest request) {
        List<String> assetPaths = projectService.listAssets(project.getId()).stream()
                .map(ProjectDtos.AssetResponse::filePath)
                .toList();
        String workingDir = request == null || request.workingDir() == null || request.workingDir().isBlank()
                ? "data/java/work/projects/" + project.getId()
                : request.workingDir();
        String finalOutputPath = request == null || request.finalOutputPath() == null || request.finalOutputPath().isBlank()
                ? (project.getFinalOutputPath() == null || project.getFinalOutputPath().isBlank()
                ? "data/java/output/projects/" + project.getId() + "/final.mp4"
                : project.getFinalOutputPath())
                : request.finalOutputPath();
        JobDtos.PipelineJobCreateRequest pipelineRequest = new JobDtos.PipelineJobCreateRequest(
                assetPaths,
                workingDir,
                finalOutputPath,
                project.getTransitionDurationSeconds(),
                project.getTransitionPrompt(),
                project.getTransitionNegativePrompt(),
                project.getLastClipDurationSeconds(),
                project.getLastClipMotionStyle(),
                project.getBgmPath(),
                project.getBgmVolume()
        );
        return enqueuePipelineJob(pipelineRequest, project.getId());
    }

    private record CallbackPayload(
            String jobId,
            String status,
            String outputPath,
            String resultMessage,
            String timestampUtc
    ) {
    }
}
