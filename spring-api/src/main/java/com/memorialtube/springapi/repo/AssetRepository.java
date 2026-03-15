package com.memorialtube.springapi.repo;

import com.memorialtube.springapi.entity.AssetEntity;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AssetRepository extends JpaRepository<AssetEntity, String> {
    List<AssetEntity> findByProjectIdOrderByOrderIndexAscCreatedAtAsc(String projectId);
}
