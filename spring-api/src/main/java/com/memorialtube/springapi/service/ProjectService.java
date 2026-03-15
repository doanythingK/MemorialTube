package com.memorialtube.springapi.service;

import com.memorialtube.springapi.api.dto.ProjectDtos;
import com.memorialtube.springapi.domain.JobStatus;
import com.memorialtube.springapi.domain.ProjectStatus;
import com.memorialtube.springapi.entity.AssetEntity;
import com.memorialtube.springapi.entity.JobEntity;
import com.memorialtube.springapi.entity.ProjectEntity;
import com.memorialtube.springapi.entity.ProjectRunEntity;
import com.memorialtube.springapi.repo.AssetRepository;
import com.memorialtube.springapi.repo.ProjectRepository;
import com.memorialtube.springapi.repo.ProjectRunRepository;
import jakarta.transaction.Transactional;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final AssetRepository assetRepository;
    private final ProjectRunRepository projectRunRepository;
    private final JobService jobService;
    private final WorkspaceService workspaceService;
    private final ImageService imageService;

    public ProjectService(
            ProjectRepository projectRepository,
            AssetRepository assetRepository,
            ProjectRunRepository projectRunRepository,
            JobService jobService,
            WorkspaceService workspaceService,
            ImageService imageService
    ) {
        this.projectRepository = projectRepository;
        this.assetRepository = assetRepository;
        this.projectRunRepository = projectRunRepository;
        this.jobService = jobService;
        this.workspaceService = workspaceService;
        this.imageService = imageService;
    }

    @Transactional
    public ProjectEntity createProject(ProjectDtos.ProjectCreateRequest request) {
        projectRepository.findByName(request.name()).ifPresent(existing -> {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "project name already exists");
        });
        ProjectEntity project = new ProjectEntity();
        project.setName(request.name());
        project.setStatus(ProjectStatus.DRAFT);
        project.setTransitionDurationSeconds(request.resolvedTransitionDurationSeconds());
        project.setTransitionPrompt(request.transitionPrompt());
        project.setTransitionNegativePrompt(request.transitionNegativePrompt());
        project.setLastClipDurationSeconds(request.resolvedLastClipDurationSeconds());
        project.setLastClipMotionStyle(request.resolvedLastClipMotionStyle());
        project.setBgmPath(request.bgmPath());
        project.setBgmVolume(request.resolvedBgmVolume());
        project.setFinalOutputPath(request.finalOutputPath());
        return projectRepository.save(project);
    }

    public List<ProjectDtos.ProjectResponse> listProjects(int limit) {
        return projectRepository.findAll(
                        PageRequest.of(0, Math.max(1, limit), Sort.by(Sort.Direction.DESC, "createdAt"))
                )
                .stream()
                .map(this::toProjectResponse)
                .toList();
    }

    public ProjectEntity requireProject(String projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "project not found: " + projectId));
    }

    public ProjectDtos.ProjectResponse getProjectResponse(String projectId) {
        return toProjectResponse(requireProject(projectId));
    }

    @Transactional
    public AssetEntity addAsset(String projectId, MultipartFile file, Integer orderIndex) {
        ProjectEntity project = requireProject(projectId);
        String safeName = workspaceService.safeFileName(file.getOriginalFilename());
        Path output = workspaceService.storageRoot().resolve("projects").resolve(project.getId()).resolve(safeName);
        workspaceService.ensureParent(output);
        try {
            file.transferTo(output);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to save uploaded asset", exc);
        }
        ImageService.ImageSize size = imageService.readSize(output);
        AssetEntity asset = new AssetEntity();
        asset.setProjectId(projectId);
        asset.setOrderIndex(orderIndex == null ? nextOrderIndex(projectId) : orderIndex);
        asset.setFileName(safeName);
        asset.setFilePath(workspaceService.toWorkspaceString(output));
        asset.setWidth(size.width());
        asset.setHeight(size.height());
        return assetRepository.save(asset);
    }

    public List<ProjectDtos.AssetResponse> listAssets(String projectId) {
        requireProject(projectId);
        return assetRepository.findByProjectIdOrderByOrderIndexAscCreatedAtAsc(projectId)
                .stream()
                .map(this::toAssetResponse)
                .toList();
    }

    @Transactional
    public void setProjectStatus(String projectId, ProjectStatus status) {
        ProjectEntity project = requireProject(projectId);
        project.setStatus(status);
        projectRepository.save(project);
    }

    @Transactional
    public void createProjectRun(String projectId, String jobId) {
        ProjectRunEntity row = new ProjectRunEntity();
        row.setProjectId(projectId);
        row.setJobId(jobId);
        projectRunRepository.save(row);
    }

    public JobEntity findLatestActiveJob(String projectId) {
        for (ProjectRunEntity row : projectRunRepository.findTop20ByProjectIdOrderByCreatedAtDesc(projectId)) {
            JobEntity job = jobService.requireJob(row.getJobId());
            if (job.getStatus() == JobStatus.QUEUED || job.getStatus() == JobStatus.PROCESSING) {
                return job;
            }
        }
        return null;
    }

    public ProjectDtos.ProjectResponse toProjectResponse(ProjectEntity project) {
        return new ProjectDtos.ProjectResponse(
                project.getId(),
                project.getName(),
                project.getStatus(),
                project.getTransitionDurationSeconds(),
                project.getTransitionPrompt(),
                project.getTransitionNegativePrompt(),
                project.getLastClipDurationSeconds(),
                project.getLastClipMotionStyle(),
                project.getBgmPath(),
                project.getBgmVolume(),
                project.getFinalOutputPath(),
                project.getCreatedAt(),
                project.getUpdatedAt()
        );
    }

    public ProjectDtos.AssetResponse toAssetResponse(AssetEntity asset) {
        return new ProjectDtos.AssetResponse(
                asset.getId(),
                asset.getProjectId(),
                asset.getOrderIndex(),
                asset.getFileName(),
                asset.getFilePath(),
                asset.getWidth(),
                asset.getHeight(),
                asset.getCreatedAt()
        );
    }

    private int nextOrderIndex(String projectId) {
        return assetRepository.findByProjectIdOrderByOrderIndexAscCreatedAtAsc(projectId)
                .stream()
                .mapToInt(AssetEntity::getOrderIndex)
                .max()
                .orElse(-1) + 1;
    }
}
