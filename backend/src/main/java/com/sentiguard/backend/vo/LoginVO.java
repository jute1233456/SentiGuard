package com.sentiguard.backend.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class LoginVO {

    private String token;

    private String tokenType;

    private Long expiresIn;

    private Long userId;

    private String username;

    private String nickname;
}
