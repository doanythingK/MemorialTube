package com.memorialtube.springapi.service;

import com.memorialtube.springapi.api.dto.JobDtos;
import com.memorialtube.springapi.domain.JobStatus;
import com.memorialtube.springapi.entity.JobEntity;
import com.memorialtube.springapi.entity.JobRuntimeEntity;
import com.memorialtube.springapi.repo.JobRepository;
import com.memorialtube.springapi.repo.JobRuntimeRepository;
import jakarta.transaction.Transactional;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class JobService {

    private final JobRepository jobRepository;
    private final JobRuntimeRepository jobRuntimeRepository;

    public JobService(JobRepository jobRepository, JobRuntimeRepository jobRuntimeRepository) {
        this.jobRepository = jobRepository;
        this.jobRuntimeRepository = jobRuntimeRepository;
    }

    @Transactional
    public JobEntity createJob(String jobType) {
        JobEntity job = new JobEntity();
        job.setJobType(jobType);
        job.setStatus(JobStatus.QUEUED);
        jobRepository.save(job);

        JobRuntimeEntity runtime = new JobRuntimeEntity();
        runtime.setJobId(job.getId());
        runtime.setStage("queued");
        runtime.setProgressPercent(0);
        runtime.setDetailMessage("queued");
        runtime.setCancelRequested(false);
        jobRuntimeRepository.save(runtime);
        return job;
    }

    @Transactional
    public void beginProcessing(String jobId) {
        JobEntity job = requireJob(jobId);
        job.setStatus(JobStatus.PROCESSING);
        jobRepository.save(job);

        JobRuntimeEntity runtime = requireRuntime(jobId);
        if ("queued".equals(runtime.getStage())) {
            runtime.setStage("processing");
        }
        runtime.setProgressPercent(Math.max(1, Math.min(99, runtime.getProgressPercent())));
        jobRuntimeRepository.save(runtime);
    }

    @Transactional
    public void updateRuntime(String jobId, String stage, int progressPercent, String detailMessage) {
        JobRuntimeEntity runtime = requireRuntime(jobId);
        runtime.setStage(stage);
        runtime.setProgressPercent(Math.max(0, Math.min(100, progressPercent)));
        runtime.setDetailMessage(detailMessage);
        jobRuntimeRepository.save(runtime);
    }

    @Transactional
    public void markSucceeded(String jobId, String resultMessage) {
        JobEntity job = requireJob(jobId);
        job.setStatus(JobStatus.SUCCEEDED);
        job.setResultMessage(resultMessage);
        jobRepository.save(job);
        JobRuntimeEntity runtime = requireRuntime(jobId);
        runtime.setStage("completed");
        runtime.setProgressPercent(100);
        runtime.setDetailMessage(resultMessage);
        jobRuntimeRepository.save(runtime);
    }

    @Transactional
    public void markFailed(String jobId, String errorMessage) {
        JobEntity job = requireJob(jobId);
        job.setStatus(JobStatus.FAILED);
        job.setErrorMessage(errorMessage);
        jobRepository.save(job);
        JobRuntimeEntity runtime = requireRuntime(jobId);
        if (!"canceled".equals(runtime.getStage())) {
            runtime.setStage("failed");
            runtime.setProgressPercent(Math.min(99, runtime.getProgressPercent()));
            runtime.setDetailMessage(errorMessage);
            jobRuntimeRepository.save(runtime);
        }
    }

    @Transactional
    public JobRuntimeEntity requestCancel(String jobId) {
        JobRuntimeEntity runtime = requireRuntime(jobId);
        runtime.setStage("cancel_requested");
        runtime.setDetailMessage("cancel requested by user");
        runtime.setCancelRequested(true);
        return jobRuntimeRepository.save(runtime);
    }

    @Transactional
    public void markCanceled(String jobId, String reason) {
        JobRuntimeEntity runtime = requireRuntime(jobId);
        runtime.setStage("canceled");
        runtime.setProgressPercent(Math.min(99, runtime.getProgressPercent()));
        runtime.setDetailMessage(reason);
        runtime.setCancelRequested(true);
        jobRuntimeRepository.save(runtime);

        JobEntity job = requireJob(jobId);
        job.setStatus(JobStatus.FAILED);
        job.setErrorMessage(reason);
        jobRepository.save(job);
    }

    public boolean isCancelRequested(String jobId) {
        return requireRuntime(jobId).isCancelRequested();
    }

    public JobDtos.JobResponse getJobResponse(String jobId) {
        JobEntity job = requireJob(jobId);
        JobRuntimeEntity runtime = requireRuntime(jobId);
        return toJobResponse(job, runtime);
    }

    public JobDtos.JobRuntimeResponse getRuntimeResponse(String jobId) {
        JobRuntimeEntity runtime = requireRuntime(jobId);
        return new JobDtos.JobRuntimeResponse(
                runtime.getJobId(),
                runtime.getStage(),
                runtime.getProgressPercent(),
                runtime.getDetailMessage(),
                runtime.isCancelRequested(),
                runtime.getCreatedAt(),
                runtime.getUpdatedAt()
        );
    }

    public List<JobDtos.JobResponse> listJobs(int limit) {
        return jobRepository.findAll(
                        PageRequest.of(0, Math.max(1, limit), Sort.by(Sort.Direction.DESC, "createdAt"))
                )
                .stream()
                .map(job -> toJobResponse(job, jobRuntimeRepository.findById(job.getId()).orElse(null)))
                .toList();
    }

    public JobEntity requireJob(String jobId) {
        return jobRepository.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "job not found: " + jobId));
    }

    public JobRuntimeEntity requireRuntime(String jobId) {
        return jobRuntimeRepository.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "job runtime not found: " + jobId));
    }

    public JobDtos.JobCancelResponse toCancelResponse(String jobId) {
        JobEntity job = requireJob(jobId);
        JobRuntimeEntity runtime = requireRuntime(jobId);
        return new JobDtos.JobCancelResponse(
                job.getId(),
                job.getStatus(),
                runtime.isCancelRequested(),
                runtime.getStage(),
                runtime.getProgressPercent(),
                runtime.getDetailMessage()
        );
    }

    private JobDtos.JobResponse toJobResponse(JobEntity job, JobRuntimeEntity runtime) {
        return new JobDtos.JobResponse(
                job.getId(),
                job.getJobType(),
                job.getStatus(),
                job.getErrorMessage(),
                job.getResultMessage(),
                job.getCreatedAt(),
                job.getUpdatedAt(),
                runtime == null ? null : runtime.getStage(),
                runtime == null ? null : runtime.getProgressPercent(),
                runtime == null ? null : runtime.getDetailMessage(),
                runtime == null ? null : runtime.isCancelRequested()
        );
    }
}
