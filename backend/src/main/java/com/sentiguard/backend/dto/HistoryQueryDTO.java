package com.sentiguard.backend.dto;

import java.time.LocalDateTime;

import lombok.Data;

@Data
public class HistoryQueryDTO {

    private Long userId;

    private String keyword;

    private String resultLabel;

    private String taskStatus;

    private LocalDateTime startTime;

    private LocalDateTime endTime;

    private Integer pageNum = 1;

    private Integer pageSize = 10;
}
