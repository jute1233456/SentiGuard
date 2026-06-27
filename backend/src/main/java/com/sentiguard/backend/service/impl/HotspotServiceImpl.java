package com.sentiguard.backend.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.sentiguard.backend.entity.HotEvent;
import com.sentiguard.backend.entity.SentimentAnalysis;
import com.sentiguard.backend.entity.TopicKeyword;
import com.sentiguard.backend.mapper.HotEventMapper;
import com.sentiguard.backend.mapper.SentimentAnalysisMapper;
import com.sentiguard.backend.mapper.TopicKeywordMapper;
import com.sentiguard.backend.config.SentiGuardAgentProperties;
import com.sentiguard.backend.service.HotspotService;
import com.sentiguard.backend.vo.*;

import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Service
public class HotspotServiceImpl implements HotspotService {

    private final HotEventMapper hotEventMapper;
    private final TopicKeywordMapper keywordMapper;
    private final SentimentAnalysisMapper sentimentMapper;
    private final RestTemplate agentRestTemplate;
    private final SentiGuardAgentProperties agentProperties;

    public HotspotServiceImpl(HotEventMapper hotEventMapper,
                              TopicKeywordMapper keywordMapper,
                              SentimentAnalysisMapper sentimentMapper,
                              RestTemplate agentRestTemplate,
                              SentiGuardAgentProperties agentProperties) {
        this.hotEventMapper = hotEventMapper;
        this.keywordMapper = keywordMapper;
        this.sentimentMapper = sentimentMapper;
        this.agentRestTemplate = agentRestTemplate;
        this.agentProperties = agentProperties;
    }

    @Override
    public List<HotspotVO> getHotspots(int limit) {
        List<HotEvent> events = hotEventMapper.selectList(
                new LambdaQueryWrapper<HotEvent>()
                        .orderByDesc(HotEvent::getHeatScore)
                        .last("LIMIT " + Math.min(limit, 100))
        );

        List<HotspotVO> result = new ArrayList<>();
        int rank = 1;
        for (HotEvent event : events) {
            HotspotVO vo = new HotspotVO();
            vo.setId(event.getId());
            vo.setRank(rank++);
            vo.setName(event.getEventTitle());
            vo.setHeat(event.getHeatScore());
            vo.setRiskLevel(event.getRiskLevel());
            vo.setSentimentLabel(event.getSentimentLabel());
            vo.setNewsCount(event.getNewsCount());

            // 关键词
            List<TopicKeyword> keywords = keywordMapper.selectList(
                    new LambdaQueryWrapper<TopicKeyword>()
                            .eq(TopicKeyword::getHotEventId, event.getId())
                            .orderByAsc(TopicKeyword::getRankNo)
            );
            List<KeywordVO> keywordVOs = new ArrayList<>();
            for (TopicKeyword kw : keywords) {
                keywordVOs.add(new KeywordVO(kw.getKeyword(), kw.getWeight()));
            }
            vo.setKeywords(keywordVOs);

            // 情感分析
            SentimentAnalysis sa = sentimentMapper.selectOne(
                    new LambdaQueryWrapper<SentimentAnalysis>()
                            .eq(SentimentAnalysis::getHotEventId, event.getId())
            );
            if (sa != null) {
                SentimentVO sv = new SentimentVO();
                sv.setLabel(sa.getSentimentLabel());
                sv.setPosRatio(sa.getPositiveRatio());
                sv.setNegRatio(sa.getNegativeRatio());
                sv.setNeuRatio(sa.getNeutralRatio());
                sv.setPositiveCount(sa.getPositiveCount());
                sv.setNegativeCount(sa.getNegativeCount());
                sv.setNeutralCount(sa.getNeutralCount());
                // 综合得分
                BigDecimal score = BigDecimal.ZERO;
                if (sa.getPositiveRatio() != null && sa.getNegativeRatio() != null) {
                    score = sa.getPositiveRatio().subtract(sa.getNegativeRatio())
                            .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
                }
                sv.setScore(score);
                vo.setSentiment(sv);
            }

            result.add(vo);
        }
        return result;
    }

    @Override
    public DashboardStatsVO getDashboardStats() {
        DashboardStatsVO stats = new DashboardStatsVO();

        // 总热点数（24h内）
        List<HotEvent> allEvents = hotEventMapper.selectList(
                new LambdaQueryWrapper<HotEvent>()
                        .ge(HotEvent::getCreateTime, LocalDateTime.now().minusHours(24))
        );
        stats.setTotalHotspots(allEvents.size());

        // 风险分布
        long lowRisk = allEvents.stream().filter(e -> "low".equals(e.getRiskLevel())).count();
        long mediumRisk = allEvents.stream().filter(e -> "medium".equals(e.getRiskLevel())).count();
        long highRisk = allEvents.stream().filter(e -> "high".equals(e.getRiskLevel())).count();
        stats.setLowRiskCount((int) lowRisk);
        stats.setMediumRiskCount((int) mediumRisk);
        stats.setHighRiskCount((int) highRisk);

        // 情感占比
        if (!allEvents.isEmpty()) {
            long posC = allEvents.stream().filter(e -> "pos".equals(e.getSentimentLabel())).count();
            long negC = allEvents.stream().filter(e -> "neg".equals(e.getSentimentLabel())).count();
            long neuC = allEvents.size() - posC - negC;
            stats.setPosRatio(BigDecimal.valueOf(posC * 100.0 / allEvents.size()).setScale(1, RoundingMode.HALF_UP));
            stats.setNegRatio(BigDecimal.valueOf(negC * 100.0 / allEvents.size()).setScale(1, RoundingMode.HALF_UP));
            stats.setNeuRatio(BigDecimal.valueOf(neuC * 100.0 / allEvents.size()).setScale(1, RoundingMode.HALF_UP));
        } else {
            stats.setPosRatio(BigDecimal.ZERO);
            stats.setNegRatio(BigDecimal.ZERO);
            stats.setNeuRatio(BigDecimal.ZERO);
        }

        // 总新闻数
        stats.setTotalNews(allEvents.stream().mapToInt(e -> e.getNewsCount() != null ? e.getNewsCount() : 0).sum());

        // 最近采集时间
        HotEvent latest = hotEventMapper.selectOne(
                new LambdaQueryWrapper<HotEvent>()
                        .orderByDesc(HotEvent::getCreateTime)
                        .last("LIMIT 1")
        );
        stats.setLastCollectTime(latest != null
                ? latest.getCreateTime().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))
                : "暂无");

        return stats;
    }

    @Override
    public HotspotVO getHotspotDetail(Long id) {
        List<HotspotVO> list = getHotspots(100);
        return list.stream().filter(h -> h.getId().equals(id)).findFirst().orElse(null);
    }

    @Override
    public CollectResultVO triggerCollect(String sources) {
        String src = (sources != null && !sources.trim().isEmpty()) ? sources : "BAIDU";
        String url = agentProperties.getBaseUrl() + agentProperties.getCollectPath()
                   + "?sources=" + src;
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.set("X-Internal-Token", agentProperties.getInternalToken());
            HttpEntity<Void> entity = new HttpEntity<>(headers);

            ResponseEntity<Map> response = agentRestTemplate.exchange(
                    url, HttpMethod.POST, entity, Map.class);

            Map<String, Object> body = response.getBody();
            CollectResultVO result = new CollectResultVO();
            if (body != null && body.get("data") != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> data = (Map<String, Object>) body.get("data");
                result.setMessage((String) body.get("message"));
                result.setNewsSaved(data.get("news_saved") != null
                        ? ((Number) data.get("news_saved")).intValue() : 0);
                result.setHotEvents(data.get("hot_events") != null
                        ? ((Number) data.get("hot_events")).intValue() : 0);
                result.setTaskId(data.get("task_id") != null
                        ? ((Number) data.get("task_id")).intValue() : 0);
            } else {
                result.setMessage("采集请求已发送");
            }
            return result;
        } catch (Exception e) {
            CollectResultVO result = new CollectResultVO();
            result.setMessage("采集失败: " + e.getMessage());
            return result;
        }
    }
}
