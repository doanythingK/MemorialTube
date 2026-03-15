package com.memorialtube.springapi.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "memorialtube")
public class MemorialTubeProperties {

    private String ffmpegPath = "ffmpeg";
    private int targetWidth = 1600;
    private int targetHeight = 900;
    private int targetFps = 24;
    private String outputVideoCodec = "libx264";
    private String outputPixelFormat = "yuv420p";
    private int canvasBackgroundBlurRadius = 22;
    private double transitionMotionScale = 0.06;
    private int transitionFrameProgressStep = 12;
    private String storageRoot = "data/java/storage";
    private String workingRoot = "data/java/work";
    private String outputRoot = "data/java/output";
    private String tempRoot = "data/java/tmp";

    public String getFfmpegPath() {
        return ffmpegPath;
    }

    public void setFfmpegPath(String ffmpegPath) {
        this.ffmpegPath = ffmpegPath;
    }

    public int getTargetWidth() {
        return targetWidth;
    }

    public void setTargetWidth(int targetWidth) {
        this.targetWidth = targetWidth;
    }

    public int getTargetHeight() {
        return targetHeight;
    }

    public void setTargetHeight(int targetHeight) {
        this.targetHeight = targetHeight;
    }

    public int getTargetFps() {
        return targetFps;
    }

    public void setTargetFps(int targetFps) {
        this.targetFps = targetFps;
    }

    public String getOutputVideoCodec() {
        return outputVideoCodec;
    }

    public void setOutputVideoCodec(String outputVideoCodec) {
        this.outputVideoCodec = outputVideoCodec;
    }

    public String getOutputPixelFormat() {
        return outputPixelFormat;
    }

    public void setOutputPixelFormat(String outputPixelFormat) {
        this.outputPixelFormat = outputPixelFormat;
    }

    public int getCanvasBackgroundBlurRadius() {
        return canvasBackgroundBlurRadius;
    }

    public void setCanvasBackgroundBlurRadius(int canvasBackgroundBlurRadius) {
        this.canvasBackgroundBlurRadius = canvasBackgroundBlurRadius;
    }

    public double getTransitionMotionScale() {
        return transitionMotionScale;
    }

    public void setTransitionMotionScale(double transitionMotionScale) {
        this.transitionMotionScale = transitionMotionScale;
    }

    public int getTransitionFrameProgressStep() {
        return transitionFrameProgressStep;
    }

    public void setTransitionFrameProgressStep(int transitionFrameProgressStep) {
        this.transitionFrameProgressStep = transitionFrameProgressStep;
    }

    public String getStorageRoot() {
        return storageRoot;
    }

    public void setStorageRoot(String storageRoot) {
        this.storageRoot = storageRoot;
    }

    public String getWorkingRoot() {
        return workingRoot;
    }

    public void setWorkingRoot(String workingRoot) {
        this.workingRoot = workingRoot;
    }

    public String getOutputRoot() {
        return outputRoot;
    }

    public void setOutputRoot(String outputRoot) {
        this.outputRoot = outputRoot;
    }

    public String getTempRoot() {
        return tempRoot;
    }

    public void setTempRoot(String tempRoot) {
        this.tempRoot = tempRoot;
    }
}
