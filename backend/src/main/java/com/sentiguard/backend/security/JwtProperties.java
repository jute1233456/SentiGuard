package com.sentiguard.backend.security;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "jwt")
public class JwtProperties {

    private String secret = "c2VudGlndWFyZC1qd3Qtc2VjcmV0LWtleS0yMDI0LWZvci1kZXYtZW52aXJvbm1lbnQ=";

    private long expirationMs = 86400000;
}
