package com.memorialtube.springapi.domain;

import com.fasterxml.jackson.annotation.JsonValue;

public enum JobStatus {
    QUEUED("queued"),
    PROCESSING("processing"),
    SUCCEEDED("succeeded"),
    FAILED("failed");

    private final String value;

    JobStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
