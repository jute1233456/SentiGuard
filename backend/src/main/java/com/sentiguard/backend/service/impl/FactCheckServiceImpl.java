package com.sentiguard.backend.service.impl;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.sentiguard.backend.common.PageResult;
import com.sentiguard.backend.agent.AgentCheckRequest;
import com.sentiguard.backend.agent.AgentCheckResponse;
import com.sentiguard.backend.agent.AgentClaim;
import com.sentiguard.backend.agent.AgentEvidence;
import com.sentiguard.backend.dto.FactCheckAnalyzeDTO;
import com.sentiguard.backend.dto.HistoryQueryDTO;
import com.sentiguard.backend.entity.AnalysisReport;
import com.sentiguard.backend.entity.Evidence;
import com.sentiguard.backend.entity.FactCheckResult;
import com.sentiguard.backend.entity.FactCheckTask;
import com.sentiguard.backend.entity.FactClaim;
import com.sentiguard.backend.mapper.AnalysisReportMapper;
import com.sentiguard.backend.mapper.EvidenceMapper;
import com.sentiguard.backend.mapper.FactCheckResultMapper;
import com.sentiguard.backend.mapper.FactCheckTaskMapper;
import com.sentiguard.backend.mapper.FactClaimMapper;
import com.sentiguard.backend.service.AgentService;
import com.sentiguard.backend.service.FactCheckService;
import com.sentiguard.backend.vo.AnalysisReportVO;
import com.sentiguard.backend.vo.EvidenceVO;
import com.sentiguard.backend.vo.FactCheckDetailVO;
import com.sentiguard.backend.vo.FactCheckResultVO;
import com.sentiguard.backend.vo.FactClaimVO;
import com.sentiguard.backend.vo.HistoryVO;

@Service
public class FactCheckServiceImpl implements FactCheckService {

    private static final String STATUS_RUNNING = "running";
    private static final String STATUS_SUCCESS = "success";
    private static final String STATUS_FAILED = "failed";

    private final FactCheckTaskMapper taskMapper;
    private final FactClaimMapper claimMapper;
    private final EvidenceMapper evidenceMapper;
    private final FactCheckResultMapper resultMapper;
    private final AnalysisReportMapper reportMapper;
    private final AgentService agentService;

    public FactCheckServiceImpl(FactCheckTaskMapper taskMapper,
                                FactClaimMapper claimMapper,
                                EvidenceMapper evidenceMapper,
                                FactCheckResultMapper resultMapper,
                                AnalysisReportMapper reportMapper,
                                AgentService agentService) {
        this.taskMapper = taskMapper;
        this.claimMapper = claimMapper;
        this.evidenceMapper = evidenceMapper;
        this.resultMapper = resultMapper;
        this.reportMapper = reportMapper;
        this.agentService = agentService;
    }

    @Override
    @Transactional
    public FactCheckDetailVO analyze(FactCheckAnalyzeDTO dto) {
        LocalDateTime now = LocalDateTime.now();
        FactCheckTask task = new FactCheckTask();
        task.setUserId(dto.getUserId());
        task.setHotEventId(dto.getHotEventId());
        task.setInputText(dto.getInputText());
        task.setTaskStatus(STATUS_RUNNING);
        task.setTaskType(dto.getHotEventId() == null ? "manual_input" : "hot_event_check");
        task.setSubmitTime(now);
        task.setCreateTime(now);
        task.setUpdateTime(now);
        task.setIsDeleted(0);
        taskMapper.insert(task);

        try {
            AgentCheckResponse agentResponse = agentService.check(new AgentCheckRequest(dto.getHotEventId(), dto.getInputText()));
            Map<Integer, Long> claimIdByOrder = saveClaims(task.getId(), agentResponse.getClaims());
            saveEvidences(task.getId(), claimIdByOrder, agentResponse.getEvidences());
            saveResult(task.getId(), agentResponse);
            saveReport(task.getId(), dto.getInputText(), agentResponse);

            task.setTaskStatus(STATUS_SUCCESS);
            task.setFinishTime(LocalDateTime.now());
            task.setUpdateTime(LocalDateTime.now());
            taskMapper.updateById(task);
            return getDetail(task.getId());
        } catch (RuntimeException ex) {
            task.setTaskStatus(STATUS_FAILED);
            task.setFinishTime(LocalDateTime.now());
            task.setErrorMessage(ex.getMessage());
            task.setUpdateTime(LocalDateTime.now());
            taskMapper.updateById(task);
            throw ex;
        }
    }

    @Override
    public FactCheckDetailVO getDetail(Long taskId) {
        FactCheckTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new IllegalArgumentException("核查任务不存在");
        }

        FactCheckDetailVO detail = new FactCheckDetailVO();
        detail.setTaskId(task.getId());
        detail.setUserId(task.getUserId());
        detail.setHotEventId(task.getHotEventId());
        detail.setInputText(task.getInputText());
        detail.setStatus(task.getTaskStatus());
        detail.setTaskType(task.getTaskType());
        detail.setSubmitTime(task.getSubmitTime());
        detail.setFinishTime(task.getFinishTime());

        List<FactClaim> claims = claimMapper.selectList(new LambdaQueryWrapper<FactClaim>()
                .eq(FactClaim::getTaskId, taskId)
                .orderByAsc(FactClaim::getClaimOrder));
        detail.setClaims(toClaimVOs(claims));

        List<Evidence> evidences = evidenceMapper.selectList(new LambdaQueryWrapper<Evidence>()
                .eq(Evidence::getTaskId, taskId)
                .orderByAsc(Evidence::getId));
        detail.setEvidences(toEvidenceVOs(evidences));

        FactCheckResult result = resultMapper.selectOne(new LambdaQueryWrapper<FactCheckResult>()
                .eq(FactCheckResult::getTaskId, taskId));
        detail.setResult(toResultVO(result));

        AnalysisReport report = reportMapper.selectOne(new LambdaQueryWrapper<AnalysisReport>()
                .eq(AnalysisReport::getTaskId, taskId));
        detail.setReport(toReportVO(report));

        return detail;
    }

    @Override
    public PageResult<HistoryVO> getHistory(HistoryQueryDTO query) {
        HistoryQueryDTO safeQuery = normalizeHistoryQuery(query);
        long total = taskMapper.selectCount(buildHistoryWrapper(safeQuery));
        long offset = (long) (safeQuery.getPageNum() - 1) * safeQuery.getPageSize();
        QueryWrapper<FactCheckTask> pageWrapper = buildHistoryWrapper(safeQuery)
                .orderByDesc("submit_time")
                .last("LIMIT " + offset + ", " + safeQuery.getPageSize());
        List<FactCheckTask> tasks = taskMapper.selectList(pageWrapper);
        List<HistoryVO> history = new ArrayList<>();
        for (FactCheckTask task : tasks) {
            FactCheckResult result = resultMapper.selectOne(new LambdaQueryWrapper<FactCheckResult>()
                    .eq(FactCheckResult::getTaskId, task.getId()));
            HistoryVO vo = new HistoryVO();
            vo.setTaskId(task.getId());
            vo.setHotEventId(task.getHotEventId());
            vo.setInputText(task.getInputText());
            vo.setStatus(task.getTaskStatus());
            vo.setSubmitTime(task.getSubmitTime());
            vo.setFinishTime(task.getFinishTime());
            if (result != null) {
                vo.setResultLabel(result.getResultLabel());
                vo.setResultLabelText(labelText(result.getResultLabel()));
                vo.setConfidenceScore(result.getConfidenceScore());
                vo.setConclusion(result.getConclusion());
                vo.setSupportCount(result.getSupportCount());
                vo.setAttackCount(result.getAttackCount());
            }
            vo.setEvidenceCount(evidenceMapper.selectCount(new LambdaQueryWrapper<Evidence>()
                    .eq(Evidence::getTaskId, task.getId())));
            vo.setHasReport(reportMapper.selectCount(new LambdaQueryWrapper<AnalysisReport>()
                    .eq(AnalysisReport::getTaskId, task.getId())) > 0);
            history.add(vo);
        }
        return PageResult.of(total, safeQuery.getPageNum(), safeQuery.getPageSize(), history);
    }

    @Override
    public AnalysisReportVO getReportByTaskId(Long taskId) {
        AnalysisReport report = reportMapper.selectOne(new LambdaQueryWrapper<AnalysisReport>()
                .eq(AnalysisReport::getTaskId, taskId));
        if (report == null) {
            throw new IllegalArgumentException("核查报告不存在");
        }
        return toReportVO(report);
    }

    @Override
    public FactCheckDetailVO rerun(Long taskId) {
        FactCheckTask oldTask = taskMapper.selectById(taskId);
        if (oldTask == null) {
            throw new IllegalArgumentException("核查任务不存在");
        }
        FactCheckAnalyzeDTO dto = new FactCheckAnalyzeDTO();
        dto.setUserId(oldTask.getUserId());
        dto.setHotEventId(oldTask.getHotEventId());
        dto.setInputText(oldTask.getInputText());
        return analyze(dto);
    }

    @Override
    @Transactional
    public void deleteTask(Long taskId) {
        FactCheckTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new IllegalArgumentException("核查任务不存在");
        }
        taskMapper.deleteById(taskId);
        reportMapper.delete(new LambdaQueryWrapper<AnalysisReport>()
                .eq(AnalysisReport::getTaskId, taskId));
    }

    private HistoryQueryDTO normalizeHistoryQuery(HistoryQueryDTO query) {
        HistoryQueryDTO safeQuery = query == null ? new HistoryQueryDTO() : query;
        int pageNum = safeQuery.getPageNum() == null || safeQuery.getPageNum() < 1 ? 1 : safeQuery.getPageNum();
        int pageSize = safeQuery.getPageSize() == null || safeQuery.getPageSize() < 1 ? 10 : safeQuery.getPageSize();
        if (pageSize > 50) {
            pageSize = 50;
        }
        safeQuery.setPageNum(pageNum);
        safeQuery.setPageSize(pageSize);
        return safeQuery;
    }

    private QueryWrapper<FactCheckTask> buildHistoryWrapper(HistoryQueryDTO query) {
        QueryWrapper<FactCheckTask> wrapper = new QueryWrapper<>();
        if (query.getUserId() != null) {
            wrapper.eq("user_id", query.getUserId());
        }
        if (StringUtils.hasText(query.getTaskStatus())) {
            wrapper.eq("task_status", query.getTaskStatus());
        }
        if (query.getStartTime() != null) {
            wrapper.ge("submit_time", query.getStartTime());
        }
        if (query.getEndTime() != null) {
            wrapper.le("submit_time", query.getEndTime());
        }
        if (StringUtils.hasText(query.getResultLabel())) {
            wrapper.apply("exists (select 1 from fact_check_result r where r.task_id = fact_check_task.id and r.result_label = {0})",
                    query.getResultLabel());
        }
        if (StringUtils.hasText(query.getKeyword())) {
            wrapper.and(item -> item.like("input_text", query.getKeyword())
                    .or()
                    .apply("exists (select 1 from fact_check_result r where r.task_id = fact_check_task.id and r.conclusion like concat('%',{0},'%'))",
                            query.getKeyword()));
        }
        return wrapper;
    }

    private Map<Integer, Long> saveClaims(Long taskId, List<AgentClaim> claims) {
        Map<Integer, Long> claimIdByOrder = new HashMap<>();
        if (claims == null) {
            return claimIdByOrder;
        }
        for (AgentClaim agentClaim : claims) {
            FactClaim claim = new FactClaim();
            claim.setTaskId(taskId);
            claim.setClaimText(agentClaim.getClaimText());
            claim.setClaimType(agentClaim.getClaimType());
            claim.setClaimOrder(agentClaim.getClaimOrder());
            claim.setCreateTime(LocalDateTime.now());
            claimMapper.insert(claim);
            claimIdByOrder.put(agentClaim.getClaimOrder(), claim.getId());
        }
        return claimIdByOrder;
    }

    private void saveEvidences(Long taskId, Map<Integer, Long> claimIdByOrder, List<AgentEvidence> evidences) {
        if (evidences == null) {
            return;
        }
        for (AgentEvidence agentEvidence : evidences) {
            Evidence evidence = new Evidence();
            evidence.setTaskId(taskId);
            evidence.setClaimId(claimIdByOrder.get(agentEvidence.getClaimOrder()));
            evidence.setEvidenceTitle(agentEvidence.getTitle());
            evidence.setEvidenceContent(agentEvidence.getContent());
            evidence.setEvidenceUrl(agentEvidence.getUrl());
            evidence.setSourceName(agentEvidence.getSourceName());
            evidence.setEvidenceType(defaultIfBlank(agentEvidence.getEvidenceType(), "web"));
            evidence.setRelationType(defaultIfBlank(agentEvidence.getRelationType(), "neutral"));
            evidence.setCredibilityScore(agentEvidence.getCredibilityScore());
            evidence.setCreateTime(LocalDateTime.now());
            evidenceMapper.insert(evidence);
        }
    }

    private void saveResult(Long taskId, AgentCheckResponse agentResponse) {
        int supportCount = 0;
        int attackCount = 0;
        if (agentResponse.getEvidences() != null) {
            for (AgentEvidence evidence : agentResponse.getEvidences()) {
                if ("support".equals(evidence.getRelationType())) {
                    supportCount++;
                }
                if ("attack".equals(evidence.getRelationType())) {
                    attackCount++;
                }
            }
        }

        FactCheckResult result = new FactCheckResult();
        result.setTaskId(taskId);
        result.setResultLabel(agentResponse.getResult().getLabel());
        result.setConfidenceScore(agentResponse.getResult().getConfidenceScore());
        result.setConclusion(agentResponse.getResult().getConclusion());
        result.setAnalysisDetail(agentResponse.getResult().getAnalysisDetail());
        result.setSupportCount(supportCount);
        result.setAttackCount(attackCount);
        result.setReviewStatus("pending");
        result.setCreateTime(LocalDateTime.now());
        result.setUpdateTime(LocalDateTime.now());
        resultMapper.insert(result);
    }

    private void saveReport(Long taskId, String inputText, AgentCheckResponse agentResponse) {
        AnalysisReport report = new AnalysisReport();
        report.setTaskId(taskId);
        report.setReportTitle(defaultIfBlank(agentResponse.getReport().getTitle(), inputText + "事实核查报告"));
        report.setReportContent(agentResponse.getReport().getContent());
        report.setReportFormat(defaultIfBlank(agentResponse.getReport().getFormat(), "markdown"));
        report.setCreateTime(LocalDateTime.now());
        report.setUpdateTime(LocalDateTime.now());
        report.setIsDeleted(0);
        reportMapper.insert(report);
    }

    private List<FactClaimVO> toClaimVOs(List<FactClaim> claims) {
        List<FactClaimVO> vos = new ArrayList<>();
        for (FactClaim claim : claims) {
            FactClaimVO vo = new FactClaimVO();
            vo.setId(claim.getId());
            vo.setClaimText(claim.getClaimText());
            vo.setClaimType(claim.getClaimType());
            vo.setClaimOrder(claim.getClaimOrder());
            vos.add(vo);
        }
        return vos;
    }

    private List<EvidenceVO> toEvidenceVOs(List<Evidence> evidences) {
        List<EvidenceVO> vos = new ArrayList<>();
        for (Evidence evidence : evidences) {
            EvidenceVO vo = new EvidenceVO();
            vo.setId(evidence.getId());
            vo.setClaimId(evidence.getClaimId());
            vo.setTitle(evidence.getEvidenceTitle());
            vo.setContent(evidence.getEvidenceContent());
            vo.setUrl(evidence.getEvidenceUrl());
            vo.setSourceName(evidence.getSourceName());
            vo.setEvidenceType(evidence.getEvidenceType());
            vo.setRelationType(evidence.getRelationType());
            vo.setCredibilityScore(evidence.getCredibilityScore());
            vos.add(vo);
        }
        return vos;
    }

    private FactCheckResultVO toResultVO(FactCheckResult result) {
        if (result == null) {
            return null;
        }
        FactCheckResultVO vo = new FactCheckResultVO();
        vo.setId(result.getId());
        vo.setLabel(result.getResultLabel());
        vo.setLabelText(labelText(result.getResultLabel()));
        vo.setConfidenceScore(result.getConfidenceScore());
        vo.setConclusion(result.getConclusion());
        vo.setAnalysisDetail(result.getAnalysisDetail());
        vo.setSupportCount(result.getSupportCount());
        vo.setAttackCount(result.getAttackCount());
        vo.setReviewStatus(result.getReviewStatus());
        return vo;
    }

    private AnalysisReportVO toReportVO(AnalysisReport report) {
        if (report == null) {
            return null;
        }
        AnalysisReportVO vo = new AnalysisReportVO();
        vo.setId(report.getId());
        vo.setTitle(report.getReportTitle());
        vo.setContent(report.getReportContent());
        vo.setFormat(report.getReportFormat());
        vo.setExportUrl(report.getExportUrl());
        return vo;
    }

    private String labelText(String label) {
        if ("true".equals(label) || "supported".equals(label)) {
            return "真实";
        }
        if ("false".equals(label) || "not_supported".equals(label)) {
            return "不支持";
        }
        if ("partly_true".equals(label)) {
            return "部分真实";
        }
        if ("insufficient_evidence".equals(label)) {
            return "证据不足";
        }
        return "未知";
    }

    private String defaultIfBlank(String value, String defaultValue) {
        return StringUtils.hasText(value) ? value : defaultValue;
    }
}
