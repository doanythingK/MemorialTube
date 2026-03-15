package com.memorialtube.springapi.repo;

import com.memorialtube.springapi.entity.JobRuntimeEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobRuntimeRepository extends JpaRepository<JobRuntimeEntity, String> {
}
