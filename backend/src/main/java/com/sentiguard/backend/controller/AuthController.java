package com.sentiguard.backend.controller;

import com.sentiguard.backend.common.Result;
import com.sentiguard.backend.dto.LoginDTO;
import com.sentiguard.backend.dto.RegisterDTO;
import com.sentiguard.backend.entity.User;
import com.sentiguard.backend.service.UserService;
import com.sentiguard.backend.vo.LoginVO;
import com.sentiguard.backend.vo.UserVO;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.validation.Valid;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final UserService userService;

    public AuthController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping("/login")
    public Result<LoginVO> login(@Valid @RequestBody LoginDTO dto) {
        return Result.ok(userService.login(dto));
    }

    @PostMapping("/register")
    public Result<LoginVO> register(@Valid @RequestBody RegisterDTO dto) {
        return Result.ok(userService.register(dto));
    }

    @GetMapping("/me")
    public Result<UserVO> me() {
        User user = userService.getCurrentUser();
        return Result.ok(new UserVO(user.getId(), user.getUsername(),
                user.getNickname(), user.getEmail(), user.getPhone()));
    }
}
