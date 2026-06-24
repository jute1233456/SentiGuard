package com.sentiguard.backend.service.impl;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import com.sentiguard.backend.agent.AgentCheckRequest;
import com.sentiguard.backend.agent.AgentCheckResponse;
import com.sentiguard.backend.agent.AgentClaim;
import com.sentiguard.backend.agent.AgentEvidence;
import com.sentiguard.backend.agent.AgentReport;
import com.sentiguard.backend.agent.AgentResult;
import com.sentiguard.backend.agent.SentiGuardApiRequest;
import com.sentiguard.backend.agent.SentiGuardClaimData;
import com.sentiguard.backend.agent.SentiGuardDetailApiResponse;
import com.sentiguard.backend.agent.SentiGuardEvidenceData;
import com.sentiguard.backend.agent.SentiGuardFactCheckDetailData;
import com.sentiguard.backend.agent.SentiGuardReportData;
import com.sentiguard.backend.agent.SentiGuardResultData;
import com.sentiguard.backend.config.SentiGuardAgentProperties;
import com.sentiguard.backend.service.AgentService;

@Service
@Profile("!mock-agent")
public class SentiGuardAgentServiceImpl implements AgentService {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final RestTemplate agentRestTemplate;
    private final SentiGuardAgentProperties properties;

    public SentiGuardAgentServiceImpl(RestTemplate agentRestTemplate,
                                      SentiGuardAgentProperties properties) {
        this.agentRestTemplate = agentRestTemplate;
        this.properties = properties;
    }

    @Override
    public AgentCheckResponse check(AgentCheckRequest request) {
        SentiGuardDetailApiResponse apiResponse = callFastApi(request.getInputText(), request.getCheckMode());
        SentiGuardFactCheckDetailData data = apiResponse.getData();
        if (data == null) {
            throw new IllegalStateException("SentiGuard 返回数据为空");
        }

        AgentCheckResponse response = new AgentCheckResponse();
        response.setClaims(mapClaims(data.getClaims(), request.getInputText()));
        response.setEvidences(mapEvidences(data.getEvidences()));
        response.setResult(mapResult(data.getResult()));
        response.setReport(mapReport(data.getReport(), request.getInputText()));
        return response;
    }

    private SentiGuardDetailApiResponse callFastApi(String claim, String checkMode) {
        String url = properties.getBaseUrl() + resolveFactCheckPath(checkMode);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Internal-Token", properties.getInternalToken());
        headers.set("X-Trace-Id", UUID.randomUUID().toString());

        HttpEntity<SentiGuardApiRequest> entity = new HttpEntity<>(new SentiGuardApiRequest(claim), headers);
        try {
            ResponseEntity<SentiGuardDetailApiResponse> response = agentRestTemplate.exchange(
                    url,
                    HttpMethod.POST,
                    entity,
                    SentiGuardDetailApiResponse.class
            );
            SentiGuardDetailApiResponse body = response.getBody();
            if (body == null) {
                throw new IllegalStateException("SentiGuard 响应为空");
            }
            if (body.getCode() == null || body.getCode() != 0) {
                throw new IllegalStateException("SentiGuard 调用失败：" + body.getMessage());
            }
            return body;
        } catch (RestClientException ex) {
            throw new IllegalStateException("无法调用 SentiGuard FastAPI：" + ex.getMessage(), ex);
        }
    }

    private String resolveFactCheckPath(String checkMode) {
        if ("deep".equalsIgnoreCase(checkMode)) {
            return properties.getDeepFactCheckPath();
        }
        return properties.getQuickFactCheckPath();
    }

    private List<AgentClaim> mapClaims(List<SentiGuardClaimData> sourceClaims, String inputText) {
        List<AgentClaim> claims = new ArrayList<>();
        if (sourceClaims != null) {
            for (SentiGuardClaimData sourceClaim : sourceClaims) {
                if (sourceClaim == null || !StringUtils.hasText(sourceClaim.getClaimText())) {
                    continue;
                }
                claims.add(new AgentClaim(
                        sourceClaim.getClaimText(),
                        defaultIfBlank(sourceClaim.getClaimType(), "verifiable"),
                        defaultOrder(sourceClaim.getClaimOrder(), claims.size() + 1)
                ));
            }
        }
        if (claims.isEmpty()) {
            claims.add(new AgentClaim(inputText, "verifiable", 1));
        }
        return claims;
    }

    private List<AgentEvidence> mapEvidences(List<SentiGuardEvidenceData> sourceEvidences) {
        List<AgentEvidence> evidences = new ArrayList<>();
        if (sourceEvidences == null) {
            return evidences;
        }
        for (SentiGuardEvidenceData sourceEvidence : sourceEvidences) {
            if (sourceEvidence == null) {
                continue;
            }
            AgentEvidence evidence = new AgentEvidence(
                    defaultOrder(sourceEvidence.getClaimOrder(), 1),
                    sourceEvidence.getEvidenceTitle(),
                    sourceEvidence.getEvidenceContent(),
                    sourceEvidence.getEvidenceUrl(),
                    sourceEvidence.getSourceName(),
                    defaultIfBlank(sourceEvidence.getEvidenceType(), "web"),
                    defaultIfBlank(sourceEvidence.getRelationType(), "neutral"),
                    sourceEvidence.getCredibilityScore()
            );
            evidence.setPublishTime(parsePublishTime(sourceEvidence.getPublishTime()));
            evidences.add(evidence);
        }
        return evidences;
    }

    private AgentResult mapResult(SentiGuardResultData sourceResult) {
        if (sourceResult == null) {
            return new AgentResult(
                    "insufficient_evidence",
                    null,
                    "证据不足以判定声明真伪。",
                    "未获取到有效核查结果。"
            );
        }
        return new AgentResult(
                defaultIfBlank(sourceResult.getResultLabel(), "insufficient_evidence"),
                sourceResult.getConfidenceScore(),
                defaultIfBlank(sourceResult.getConclusion(), "暂无核查结论。"),
                defaultIfBlank(sourceResult.getAnalysisDetail(), "暂无分析说明。")
        );
    }

    private AgentReport mapReport(SentiGuardReportData sourceReport, String inputText) {
        if (sourceReport == null) {
            return new AgentReport(inputText + "事实核查报告", "", "markdown");
        }
        return new AgentReport(
                defaultIfBlank(sourceReport.getReportTitle(), inputText + "事实核查报告"),
                defaultIfBlank(sourceReport.getReportContent(), ""),
                defaultIfBlank(sourceReport.getReportFormat(), "markdown")
        );
    }

    private LocalDateTime parsePublishTime(String publishTime) {
        if (!StringUtils.hasText(publishTime)) {
            return null;
        }
        String value = publishTime.trim();
        try {
            return LocalDateTime.parse(value, DATE_TIME_FORMATTER);
        } catch (DateTimeParseException ignored) {
            // Continue trying common API formats.
        }
        try {
            return LocalDateTime.parse(value);
        } catch (DateTimeParseException ignored) {
            // Continue trying offset date-time values.
        }
        try {
            return OffsetDateTime.parse(value).toLocalDateTime();
        } catch (DateTimeParseException ignored) {
            // Continue trying date-only values.
        }
        try {
            String datePart = value.length() > 10 ? value.substring(0, 10) : value;
            return LocalDate.parse(datePart).atStartOfDay();
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }

    private Integer defaultOrder(Integer order, int defaultOrder) {
        return order == null || order < 1 ? defaultOrder : order;
    }

    private String defaultIfBlank(String value, String defaultValue) {
        return StringUtils.hasText(value) ? value : defaultValue;
    }
}
