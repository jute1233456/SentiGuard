package com.sentiguard.backend;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import com.sentiguard.backend.common.PageResult;
import com.sentiguard.backend.dto.FactCheckAnalyzeDTO;
import com.sentiguard.backend.dto.HistoryQueryDTO;
import com.sentiguard.backend.service.FactCheckService;
import com.sentiguard.backend.vo.FactCheckDetailVO;
import com.sentiguard.backend.vo.HistoryVO;

@SpringBootTest
@ActiveProfiles({"local", "mock-agent"})
class FactCheckModuleTests {

    @Autowired
    private FactCheckService factCheckService;

    @Test
    void shouldAnalyzeWithMockAgentAndPersistResult() {
        FactCheckAnalyzeDTO dto = new FactCheckAnalyzeDTO();
        dto.setInputText("北大鹅腿阿姨事件");

        FactCheckDetailVO detail = factCheckService.analyze(dto);
        FactCheckDetailVO savedDetail = factCheckService.getDetail(detail.getTaskId());

        assertThat(savedDetail.getStatus()).isEqualTo("success");
        assertThat(savedDetail.getClaims()).hasSize(3);
        assertThat(savedDetail.getEvidences()).hasSize(3);
        assertThat(savedDetail.getResult()).isNotNull();
        assertThat(savedDetail.getReport()).isNotNull();
    }

    @Test
    void shouldQueryHistoryWithPagination() {
        HistoryQueryDTO query = new HistoryQueryDTO();
        query.setKeyword("北大鹅腿");
        query.setPageNum(1);
        query.setPageSize(5);

        PageResult<HistoryVO> page = factCheckService.getHistory(query);

        assertThat(page.getPageNum()).isEqualTo(1);
        assertThat(page.getPageSize()).isEqualTo(5);
        assertThat(page.getRecords()).isNotNull();
    }
}
