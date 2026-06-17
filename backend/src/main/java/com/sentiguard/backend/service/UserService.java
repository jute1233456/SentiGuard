package com.sentiguard.backend.service;

import com.sentiguard.backend.dto.LoginDTO;
import com.sentiguard.backend.dto.RegisterDTO;
import com.sentiguard.backend.entity.User;
import com.sentiguard.backend.vo.LoginVO;
import com.sentiguard.backend.vo.UserVO;

public interface UserService {

    LoginVO login(LoginDTO dto);

    LoginVO register(RegisterDTO dto);

    User getCurrentUser();
}
