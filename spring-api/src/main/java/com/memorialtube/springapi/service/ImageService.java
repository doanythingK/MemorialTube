package com.memorialtube.springapi.service;

import com.memorialtube.springapi.config.MemorialTubeProperties;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.imageio.ImageIO;
import org.springframework.stereotype.Service;

@Service
public class ImageService {

    private final MemorialTubeProperties properties;
    private final WorkspaceService workspaceService;

    public ImageService(MemorialTubeProperties properties, WorkspaceService workspaceService) {
        this.properties = properties;
        this.workspaceService = workspaceService;
    }

    public BufferedImage readRgb(Path path) {
        try (InputStream inputStream = Files.newInputStream(path)) {
            BufferedImage image = ImageIO.read(inputStream);
            if (image == null) {
                throw new IllegalArgumentException("unsupported image: " + path);
            }
            return toRgb(image);
        } catch (IOException exc) {
            throw new IllegalStateException("failed to read image: " + path, exc);
        }
    }

    public ImageSize readSize(Path path) {
        BufferedImage image = readRgb(path);
        return new ImageSize(image.getWidth(), image.getHeight());
    }

    public void writeJpg(BufferedImage image, Path outputPath) {
        workspaceService.ensureParent(outputPath);
        try {
            ImageIO.write(toRgb(image), "jpg", outputPath.toFile());
        } catch (IOException exc) {
            throw new IllegalStateException("failed to write image: " + outputPath, exc);
        }
    }

    public void writePng(BufferedImage image, Path outputPath) {
        workspaceService.ensureParent(outputPath);
        try {
            ImageIO.write(toRgb(image), "png", outputPath.toFile());
        } catch (IOException exc) {
            throw new IllegalStateException("failed to write image: " + outputPath, exc);
        }
    }

    public BufferedImage buildCanvas(BufferedImage source) {
        BufferedImage cover = buildCoverBlur(source);
        BufferedImage fitted = fitInside(source, properties.getTargetWidth(), properties.getTargetHeight());
        int x = (properties.getTargetWidth() - fitted.getWidth()) / 2;
        int y = (properties.getTargetHeight() - fitted.getHeight()) / 2;
        Graphics2D graphics = cover.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        graphics.drawImage(fitted, x, y, null);
        graphics.dispose();
        return cover;
    }

    public BufferedImage applyMotion(BufferedImage source, double scale, double shiftXRatio, double shiftYRatio) {
        int width = properties.getTargetWidth();
        int height = properties.getTargetHeight();
        int scaledWidth = (int) Math.round(width * scale);
        int scaledHeight = (int) Math.round(height * scale);
        BufferedImage scaled = resize(source, scaledWidth, scaledHeight);
        int baseX = (width - scaledWidth) / 2;
        int baseY = (height - scaledHeight) / 2;
        int dx = (int) Math.round(shiftXRatio * width);
        int dy = (int) Math.round(shiftYRatio * height);
        BufferedImage canvas = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = canvas.createGraphics();
        graphics.drawImage(scaled, baseX + dx, baseY + dy, null);
        graphics.dispose();
        return canvas;
    }

    public BufferedImage blend(BufferedImage a, BufferedImage b, double alpha) {
        double clamped = Math.max(0.0d, Math.min(1.0d, alpha));
        int width = properties.getTargetWidth();
        int height = properties.getTargetHeight();
        BufferedImage out = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int rgbA = a.getRGB(x, y);
                int rgbB = b.getRGB(x, y);
                int r = (int) Math.round((((rgbA >> 16) & 0xff) * (1.0d - clamped)) + (((rgbB >> 16) & 0xff) * clamped));
                int g = (int) Math.round((((rgbA >> 8) & 0xff) * (1.0d - clamped)) + (((rgbB >> 8) & 0xff) * clamped));
                int bValue = (int) Math.round(((rgbA & 0xff) * (1.0d - clamped)) + ((rgbB & 0xff) * clamped));
                out.setRGB(x, y, (r << 16) | (g << 8) | bValue);
            }
        }
        return out;
    }

    public BufferedImage toneBlend(BufferedImage source, int[] targetRgb, double amount) {
        double clamped = Math.max(0.0d, Math.min(1.0d, amount));
        BufferedImage out = new BufferedImage(source.getWidth(), source.getHeight(), BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < source.getHeight(); y++) {
            for (int x = 0; x < source.getWidth(); x++) {
                int rgb = source.getRGB(x, y);
                int r = (int) Math.round((((rgb >> 16) & 0xff) * (1.0d - clamped)) + (targetRgb[0] * clamped));
                int g = (int) Math.round((((rgb >> 8) & 0xff) * (1.0d - clamped)) + (targetRgb[1] * clamped));
                int b = (int) Math.round(((rgb & 0xff) * (1.0d - clamped)) + (targetRgb[2] * clamped));
                out.setRGB(x, y, (r << 16) | (g << 8) | b);
            }
        }
        return out;
    }

    public int[] averageRgb(BufferedImage image) {
        long r = 0L;
        long g = 0L;
        long b = 0L;
        long total = (long) image.getWidth() * image.getHeight();
        for (int y = 0; y < image.getHeight(); y++) {
            for (int x = 0; x < image.getWidth(); x++) {
                int rgb = image.getRGB(x, y);
                r += (rgb >> 16) & 0xff;
                g += (rgb >> 8) & 0xff;
                b += rgb & 0xff;
            }
        }
        return new int[]{
                (int) (r / total),
                (int) (g / total),
                (int) (b / total)
        };
    }

    public double easeInOut(double t) {
        return 0.5d - (0.5d * Math.cos(Math.PI * Math.max(0.0d, Math.min(1.0d, t))));
    }

    private BufferedImage buildCoverBlur(BufferedImage source) {
        double scale = Math.max(
                (double) properties.getTargetWidth() / source.getWidth(),
                (double) properties.getTargetHeight() / source.getHeight()
        );
        int coverWidth = Math.max(1, (int) Math.round(source.getWidth() * scale));
        int coverHeight = Math.max(1, (int) Math.round(source.getHeight() * scale));
        BufferedImage cover = resize(source, coverWidth, coverHeight);
        BufferedImage cropped = new BufferedImage(
                properties.getTargetWidth(),
                properties.getTargetHeight(),
                BufferedImage.TYPE_INT_RGB
        );
        Graphics2D graphics = cropped.createGraphics();
        graphics.drawImage(
                cover,
                (properties.getTargetWidth() - coverWidth) / 2,
                (properties.getTargetHeight() - coverHeight) / 2,
                null
        );
        graphics.dispose();

        int blurFactor = Math.max(8, properties.getCanvasBackgroundBlurRadius());
        int smallWidth = Math.max(32, properties.getTargetWidth() / blurFactor);
        int smallHeight = Math.max(18, properties.getTargetHeight() / blurFactor);
        BufferedImage down = resize(cropped, smallWidth, smallHeight);
        return resize(down, properties.getTargetWidth(), properties.getTargetHeight());
    }

    private BufferedImage fitInside(BufferedImage source, int targetWidth, int targetHeight) {
        double scale = Math.min((double) targetWidth / source.getWidth(), (double) targetHeight / source.getHeight());
        int width = Math.max(1, (int) Math.round(source.getWidth() * scale));
        int height = Math.max(1, (int) Math.round(source.getHeight() * scale));
        return resize(source, width, height);
    }

    private BufferedImage resize(BufferedImage source, int width, int height) {
        BufferedImage resized = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = resized.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        graphics.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        graphics.drawImage(source, 0, 0, width, height, null);
        graphics.dispose();
        return resized;
    }

    private BufferedImage toRgb(BufferedImage input) {
        if (input.getType() == BufferedImage.TYPE_INT_RGB) {
            return input;
        }
        BufferedImage converted = new BufferedImage(input.getWidth(), input.getHeight(), BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = converted.createGraphics();
        graphics.drawImage(input, 0, 0, null);
        graphics.dispose();
        return converted;
    }

    public record ImageSize(int width, int height) {
    }
}
