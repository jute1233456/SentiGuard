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
import com.sentiguard.backend.entity.User;
import com.sentiguard.backend.service.FactCheckService;
import com.sentiguard.backend.service.UserService;
import com.sentiguard.backend.vo.FactCheckDetailVO;
import com.sentiguard.backend.vo.HistoryVO;

@RestController
@RequestMapping("/api/fact-check")
public class FactCheckController {

    private final FactCheckService factCheckService;
    private final UserService userService;

    public FactCheckController(FactCheckService factCheckService, UserService userService) {
        this.factCheckService = factCheckService;
        this.userService = userService;
    }

    @PostMapping("/analyze")
    public Result<FactCheckDetailVO> analyze(@Valid @RequestBody FactCheckAnalyzeDTO dto) {
        return analyzeWithMode(dto, dto.getCheckMode());
    }

    @PostMapping("/analyze/quick")
    public Result<FactCheckDetailVO> analyzeQuick(@Valid @RequestBody FactCheckAnalyzeDTO dto) {
        return analyzeWithMode(dto, "quick");
    }

    @PostMapping("/analyze/deep")
    public Result<FactCheckDetailVO> analyzeDeep(@Valid @RequestBody FactCheckAnalyzeDTO dto) {
        return analyzeWithMode(dto, "deep");
    }

    private Result<FactCheckDetailVO> analyzeWithMode(FactCheckAnalyzeDTO dto, String checkMode) {
        User currentUser = userService.getCurrentUser();
        dto.setUserId(currentUser.getId());
        dto.setCheckMode(checkMode);
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
        User currentUser = userService.getCurrentUser();
        HistoryQueryDTO query = new HistoryQueryDTO();
        query.setUserId(currentUser.getId());
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
