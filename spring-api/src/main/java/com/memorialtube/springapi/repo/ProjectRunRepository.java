package com.memorialtube.springapi.repo;

import com.memorialtube.springapi.entity.ProjectRunEntity;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectRunRepository extends JpaRepository<ProjectRunEntity, String> {
    List<ProjectRunEntity> findTop20ByProjectIdOrderByCreatedAtDesc(String projectId);
}
