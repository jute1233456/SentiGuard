package com.sentiguard.backend.service;

import com.sentiguard.backend.vo.CollectResultVO;
import com.sentiguard.backend.vo.DashboardStatsVO;
import com.sentiguard.backend.vo.HotspotVO;

import java.util.List;

public interface HotspotService {

    List<HotspotVO> getHotspots(int limit);

    DashboardStatsVO getDashboardStats();

    HotspotVO getHotspotDetail(Long id);

    CollectResultVO triggerCollect(String sources);
}
