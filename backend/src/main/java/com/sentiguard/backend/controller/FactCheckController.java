package com.sentiguard.backend.controller;

import java.time.LocalDateTime;

import javax.validation.Valid;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.sentiguard.backend.common.PageResult;
import com.sentiguard.backend.common.Result;
import com.sentiguard.backend.dto.FactCheckAnalyzeDTO;
import com.sentiguard.backend.dto.HistoryQueryDTO;
import com.sentiguard.backend.service.FactCheckService;
import com.sentiguard.backend.vo.FactCheckDetailVO;
import com.sentiguard.backend.vo.HistoryVO;

@RestController
@RequestMapping("/api/fact-check")
public class FactCheckController {

    private final FactCheckService factCheckService;

    public FactCheckController(FactCheckService factCheckService) {
        this.factCheckService = factCheckService;
    }

    @PostMapping("/analyze")
    public Result<FactCheckDetailVO> analyze(@Valid @RequestBody FactCheckAnalyzeDTO dto) {
        return Result.ok(factCheckService.analyze(dto));
    }

    @GetMapping("/tasks/{taskId}")
    public Result<FactCheckDetailVO> getDetail(@PathVariable Long taskId) {
        return Result.ok(factCheckService.getDetail(taskId));
    }

    @GetMapping("/history")
    public Result<PageResult<HistoryVO>> getHistory(@RequestParam(required = false) Long userId,
                                                    @RequestParam(required = false) String keyword,
                                                    @RequestParam(required = false) String resultLabel,
                                                    @RequestParam(required = false) String taskStatus,
                                                    @RequestParam(required = false)
                                                    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
                                                    LocalDateTime startTime,
                                                    @RequestParam(required = false)
                                                    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
                                                    LocalDateTime endTime,
                                                    @RequestParam(defaultValue = "1") Integer pageNum,
                                                    @RequestParam(defaultValue = "10") Integer pageSize) {
        HistoryQueryDTO query = new HistoryQueryDTO();
        query.setUserId(userId);
        query.setKeyword(keyword);
        query.setResultLabel(resultLabel);
        query.setTaskStatus(taskStatus);
        query.setStartTime(startTime);
        query.setEndTime(endTime);
        query.setPageNum(pageNum);
        query.setPageSize(pageSize);
        return Result.ok(factCheckService.getHistory(query));
    }

    @PostMapping("/tasks/{taskId}/rerun")
    public Result<FactCheckDetailVO> rerun(@PathVariable Long taskId) {
        return Result.ok(factCheckService.rerun(taskId));
    }

    @DeleteMapping("/tasks/{taskId}")
    public Result<Void> deleteTask(@PathVariable Long taskId) {
        factCheckService.deleteTask(taskId);
        return Result.ok(null);
    }
}
