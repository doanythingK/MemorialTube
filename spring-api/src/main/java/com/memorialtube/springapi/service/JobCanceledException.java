package com.memorialtube.springapi.service;

public class JobCanceledException extends RuntimeException {
    public JobCanceledException(String message) {
        super(message);
    }
}
