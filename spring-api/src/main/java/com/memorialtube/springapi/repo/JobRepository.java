package com.memorialtube.springapi.repo;

import com.memorialtube.springapi.entity.JobEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobRepository extends JpaRepository<JobEntity, String> {
}
