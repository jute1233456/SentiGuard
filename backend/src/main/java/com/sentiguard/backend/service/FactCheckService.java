package com.sentiguard.backend.service;

import com.sentiguard.backend.common.PageResult;
import com.sentiguard.backend.dto.FactCheckAnalyzeDTO;
import com.sentiguard.backend.dto.HistoryQueryDTO;
import com.sentiguard.backend.vo.AnalysisReportVO;
import com.sentiguard.backend.vo.FactCheckDetailVO;
import com.sentiguard.backend.vo.HistoryVO;

public interface FactCheckService {

    FactCheckDetailVO analyze(FactCheckAnalyzeDTO dto);

    FactCheckDetailVO getDetail(Long taskId);

    PageResult<HistoryVO> getHistory(HistoryQueryDTO query);

    AnalysisReportVO getReportByTaskId(Long taskId);

    FactCheckDetailVO rerun(Long taskId);

    void deleteTask(Long taskId);
}
