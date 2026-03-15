package com.memorialtube.springapi.service;

import com.memorialtube.springapi.config.MemorialTubeProperties;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class WorkspaceService {

    private final MemorialTubeProperties properties;
    private final Path workspaceRoot;

    public WorkspaceService(MemorialTubeProperties properties) {
        this.properties = properties;
        this.workspaceRoot = detectWorkspaceRoot();
        ensureDirectory(storageRoot());
        ensureDirectory(workingRoot());
        ensureDirectory(outputRoot());
        ensureDirectory(tempRoot());
    }

    public Path workspaceRoot() {
        return workspaceRoot;
    }

    public Path storageRoot() {
        return resolveManagedRoot(properties.getStorageRoot());
    }

    public Path workingRoot() {
        return resolveManagedRoot(properties.getWorkingRoot());
    }

    public Path outputRoot() {
        return resolveManagedRoot(properties.getOutputRoot());
    }

    public Path tempRoot() {
        return resolveManagedRoot(properties.getTempRoot());
    }

    public Path resolveUserPath(String rawPath) {
        if (rawPath == null || rawPath.isBlank()) {
            throw new IllegalArgumentException("path must not be blank");
        }
        Path candidate = Path.of(rawPath);
        Path resolved = candidate.isAbsolute()
                ? candidate.normalize()
                : workspaceRoot.resolve(rawPath).normalize();
        ensureUnderWorkspace(resolved);
        return resolved;
    }

    public void ensureParent(Path path) {
        ensureDirectory(path.getParent());
    }

    public String toWorkspaceString(Path path) {
        Path normalized = path.toAbsolutePath().normalize();
        try {
            return workspaceRoot.relativize(normalized).toString().replace('\\', '/');
        } catch (IllegalArgumentException exc) {
            return normalized.toString();
        }
    }

    public String safeFileName(String rawName) {
        String base = rawName == null ? "asset.bin" : rawName.trim();
        if (base.isEmpty()) {
            base = "asset.bin";
        }
        base = base.replace('\\', '_').replace('/', '_').replace(':', '_');
        base = base.replaceAll("[^A-Za-z0-9._-]", "_");
        return base.toLowerCase(Locale.ROOT);
    }

    private Path resolveManagedRoot(String configured) {
        Path path = Path.of(configured);
        Path resolved = path.isAbsolute() ? path.normalize() : workspaceRoot.resolve(configured).normalize();
        ensureUnderWorkspace(resolved);
        return resolved;
    }

    private Path detectWorkspaceRoot() {
        Path cwd = Path.of("").toAbsolutePath().normalize();
        if (Files.isDirectory(cwd.resolve("app"))) {
            return cwd;
        }
        Path parent = cwd.getParent();
        if (parent != null && Files.isDirectory(parent.resolve("app"))) {
            return parent.normalize();
        }
        return cwd;
    }

    private void ensureUnderWorkspace(Path path) {
        if (!path.toAbsolutePath().normalize().startsWith(workspaceRoot)) {
            throw new IllegalArgumentException("path is outside workspace: " + path);
        }
    }

    private void ensureDirectory(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.createDirectories(path);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to create directory: " + path, exc);
        }
    }
}
