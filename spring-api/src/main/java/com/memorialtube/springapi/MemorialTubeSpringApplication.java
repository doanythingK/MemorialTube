package com.memorialtube.springapi;

import com.memorialtube.springapi.config.MemorialTubeProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableAsync;

@EnableAsync
@SpringBootApplication
@EnableConfigurationProperties(MemorialTubeProperties.class)
public class MemorialTubeSpringApplication {

    public static void main(String[] args) {
        SpringApplication.run(MemorialTubeSpringApplication.class, args);
    }
}
