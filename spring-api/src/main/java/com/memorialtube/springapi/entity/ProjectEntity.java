package com.memorialtube.springapi.entity;

import com.memorialtube.springapi.domain.ProjectStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "projects")
public class ProjectEntity {

    @Id
    @Column(length = 36, nullable = false)
    private String id;

    @Column(length = 200, nullable = false)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProjectStatus status = ProjectStatus.DRAFT;

    @Column(nullable = false)
    private int transitionDurationSeconds = 6;

    @Lob
    @Column(nullable = false)
    private String transitionPrompt;

    @Lob
    private String transitionNegativePrompt;

    @Column(nullable = false)
    private int lastClipDurationSeconds = 4;

    @Column(length = 20, nullable = false)
    private String lastClipMotionStyle = "zoom_in";

    @Lob
    private String bgmPath;

    @Column(nullable = false)
    private double bgmVolume = 0.15d;

    @Lob
    private String finalOutputPath;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    @PrePersist
    public void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    public void onUpdate() {
        updatedAt = Instant.now();
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public ProjectStatus getStatus() {
        return status;
    }

    public void setStatus(ProjectStatus status) {
        this.status = status;
    }

    public int getTransitionDurationSeconds() {
        return transitionDurationSeconds;
    }

    public void setTransitionDurationSeconds(int transitionDurationSeconds) {
        this.transitionDurationSeconds = transitionDurationSeconds;
    }

    public String getTransitionPrompt() {
        return transitionPrompt;
    }

    public void setTransitionPrompt(String transitionPrompt) {
        this.transitionPrompt = transitionPrompt;
    }

    public String getTransitionNegativePrompt() {
        return transitionNegativePrompt;
    }

    public void setTransitionNegativePrompt(String transitionNegativePrompt) {
        this.transitionNegativePrompt = transitionNegativePrompt;
    }

    public int getLastClipDurationSeconds() {
        return lastClipDurationSeconds;
    }

    public void setLastClipDurationSeconds(int lastClipDurationSeconds) {
        this.lastClipDurationSeconds = lastClipDurationSeconds;
    }

    public String getLastClipMotionStyle() {
        return lastClipMotionStyle;
    }

    public void setLastClipMotionStyle(String lastClipMotionStyle) {
        this.lastClipMotionStyle = lastClipMotionStyle;
    }

    public String getBgmPath() {
        return bgmPath;
    }

    public void setBgmPath(String bgmPath) {
        this.bgmPath = bgmPath;
    }

    public double getBgmVolume() {
        return bgmVolume;
    }

    public void setBgmVolume(double bgmVolume) {
        this.bgmVolume = bgmVolume;
    }

    public String getFinalOutputPath() {
        return finalOutputPath;
    }

    public void setFinalOutputPath(String finalOutputPath) {
        this.finalOutputPath = finalOutputPath;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
