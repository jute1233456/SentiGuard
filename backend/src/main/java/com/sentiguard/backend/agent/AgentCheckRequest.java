package com.sentiguard.backend.agent;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class AgentCheckRequest {

    private Long hotEventId;

    private String inputText;
    private String checkMode = "quick";
}
