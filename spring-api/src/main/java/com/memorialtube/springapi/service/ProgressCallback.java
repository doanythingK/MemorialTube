package com.memorialtube.springapi.service;

@FunctionalInterface
public interface ProgressCallback {
    void update(String stage, int progressPercent, String detailMessage);
}
