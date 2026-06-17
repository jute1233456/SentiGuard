package com.sentiguard.backend.vo;

import java.math.BigDecimal;
import java.time.LocalDateTime;

import lombok.Data;

@Data
public class HistoryVO {

    private Long taskId;

    private Long hotEventId;

    private String inputText;

    private String status;

    private LocalDateTime submitTime;

    private LocalDateTime finishTime;

    private String resultLabel;

    private String resultLabelText;

    private BigDecimal confidenceScore;

    private String conclusion;

    private Integer supportCount;

    private Integer attackCount;

    private Long evidenceCount;

    private Boolean hasReport;
}
