package com.memorialtube.springapi.api;

import com.memorialtube.springapi.api.dto.JobDtos;
import com.memorialtube.springapi.api.dto.ProjectDtos;
import com.memorialtube.springapi.entity.JobEntity;
import com.memorialtube.springapi.entity.ProjectEntity;
import com.memorialtube.springapi.service.JobExecutionService;
import com.memorialtube.springapi.service.JobService;
import com.memorialtube.springapi.service.ProjectService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/projects")
public class ProjectsController {

    private final ProjectService projectService;
    private final JobService jobService;
    private final JobExecutionService jobExecutionService;

    public ProjectsController(
            ProjectService projectService,
            JobService jobService,
            JobExecutionService jobExecutionService
    ) {
        this.projectService = projectService;
        this.jobService = jobService;
        this.jobExecutionService = jobExecutionService;
    }

    @PostMapping
    public ProjectDtos.ProjectResponse createProject(@Valid @org.springframework.web.bind.annotation.RequestBody ProjectDtos.ProjectCreateRequest request) {
        return projectService.toProjectResponse(projectService.createProject(request));
    }

    @GetMapping
    public List<ProjectDtos.ProjectResponse> listProjects(@RequestParam(defaultValue = "20") int limit) {
        return projectService.listProjects(limit);
    }

    @GetMapping("/{projectId}")
    public ProjectDtos.ProjectResponse getProject(@PathVariable String projectId) {
        return projectService.getProjectResponse(projectId);
    }

    @PostMapping(value = "/{projectId}/assets", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ProjectDtos.AssetResponse uploadAsset(
            @PathVariable String projectId,
            @RequestPart("file") MultipartFile file,
            @RequestParam(required = false) Integer orderIndex
    ) {
        return projectService.toAssetResponse(projectService.addAsset(projectId, file, orderIndex));
    }

    @GetMapping("/{projectId}/assets")
    public List<ProjectDtos.AssetResponse> listAssets(@PathVariable String projectId) {
        return projectService.listAssets(projectId);
    }

    @PostMapping("/{projectId}/run")
    public JobDtos.JobEnqueueResponse runProject(
            @PathVariable String projectId,
            @org.springframework.web.bind.annotation.RequestBody(required = false) ProjectDtos.ProjectRunRequest request
    ) {
        ProjectEntity project = projectService.requireProject(projectId);
        if (projectService.findLatestActiveJob(projectId) != null) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.CONFLICT,
                    "project already has an active run"
            );
        }
        return jobExecutionService.enqueueProjectRun(project, request);
    }

    @PostMapping("/{projectId}/cancel")
    public JobDtos.JobCancelResponse cancelProject(@PathVariable String projectId) {
        JobEntity job = projectService.findLatestActiveJob(projectId);
        if (job == null) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.CONFLICT,
                    "no active project run found"
            );
        }
        jobService.requestCancel(job.getId());
        return jobService.toCancelResponse(job.getId());
    }
}
