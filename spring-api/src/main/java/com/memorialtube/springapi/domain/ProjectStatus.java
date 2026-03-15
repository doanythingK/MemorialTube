package com.memorialtube.springapi.domain;

import com.fasterxml.jackson.annotation.JsonValue;

public enum ProjectStatus {
    DRAFT("draft"),
    RUNNING("running"),
    COMPLETED("completed"),
    FAILED("failed");

    private final String value;

    ProjectStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
