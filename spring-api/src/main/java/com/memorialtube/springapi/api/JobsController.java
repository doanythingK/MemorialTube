package com.memorialtube.springapi.api;

import com.memorialtube.springapi.api.dto.JobDtos;
import com.memorialtube.springapi.service.JobExecutionService;
import com.memorialtube.springapi.service.JobService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/jobs")
public class JobsController {

    private final JobExecutionService jobExecutionService;
    private final JobService jobService;

    public JobsController(JobExecutionService jobExecutionService, JobService jobService) {
        this.jobExecutionService = jobExecutionService;
        this.jobService = jobService;
    }

    @PostMapping("/test")
    public JobDtos.JobEnqueueResponse enqueueTestJob(
            @RequestBody(required = false) JobDtos.JobCreateRequest request
    ) {
        return jobExecutionService.enqueueTestJob(request == null ? new JobDtos.JobCreateRequest("test_render") : request);
    }

    @PostMapping("/canvas")
    public JobDtos.JobEnqueueResponse enqueueCanvasJob(@Valid @RequestBody JobDtos.CanvasJobCreateRequest request) {
        return jobExecutionService.enqueueCanvasJob(request);
    }

    @PostMapping("/transition")
    public JobDtos.JobEnqueueResponse enqueueTransitionJob(@Valid @RequestBody JobDtos.TransitionJobCreateRequest request) {
        return jobExecutionService.enqueueTransitionJob(request);
    }

    @PostMapping("/last-clip")
    public JobDtos.JobEnqueueResponse enqueueLastClipJob(@Valid @RequestBody JobDtos.LastClipJobCreateRequest request) {
        return jobExecutionService.enqueueLastClipJob(request);
    }

    @PostMapping("/render")
    public JobDtos.JobEnqueueResponse enqueueRenderJob(@Valid @RequestBody JobDtos.RenderJobCreateRequest request) {
        return jobExecutionService.enqueueRenderJob(request);
    }

    @PostMapping("/pipeline")
    public JobDtos.JobEnqueueResponse enqueuePipelineJob(@Valid @RequestBody JobDtos.PipelineJobCreateRequest request) {
        return jobExecutionService.enqueuePipelineJob(request, null);
    }

    @GetMapping("/{jobId}")
    public JobDtos.JobResponse getJob(@PathVariable String jobId) {
        return jobService.getJobResponse(jobId);
    }

    @GetMapping("/{jobId}/runtime")
    public JobDtos.JobRuntimeResponse getJobRuntime(@PathVariable String jobId) {
        return jobService.getRuntimeResponse(jobId);
    }

    @GetMapping
    public List<JobDtos.JobResponse> listJobs(@RequestParam(defaultValue = "20") int limit) {
        return jobService.listJobs(limit);
    }

    @PostMapping("/{jobId}/cancel")
    public JobDtos.JobCancelResponse cancelJob(@PathVariable String jobId) {
        jobService.requestCancel(jobId);
        return jobService.toCancelResponse(jobId);
    }
}
