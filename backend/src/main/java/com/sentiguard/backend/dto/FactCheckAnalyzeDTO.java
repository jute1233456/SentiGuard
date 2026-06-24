package com.sentiguard.backend.dto;

import javax.validation.constraints.NotBlank;

import lombok.Data;

@Data
public class FactCheckAnalyzeDTO {

    private Long userId;

    private Long hotEventId;

    @NotBlank(message = "核查内容不能为空")
    private String inputText;
    private String checkMode = "quick";
}
