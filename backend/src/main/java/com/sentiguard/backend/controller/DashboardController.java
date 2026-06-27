package com.sentiguard.backend.controller;

import com.sentiguard.backend.common.Result;
import com.sentiguard.backend.service.HotspotService;
import com.sentiguard.backend.vo.CollectResultVO;
import com.sentiguard.backend.vo.DashboardStatsVO;
import com.sentiguard.backend.vo.HotspotVO;

import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api")
public class DashboardController {

    private final HotspotService hotspotService;

    public DashboardController(HotspotService hotspotService) {
        this.hotspotService = hotspotService;
    }

    @GetMapping("/hotspots")
    public Result<List<HotspotVO>> listHotspots(
            @RequestParam(defaultValue = "20") int limit) {
        return Result.ok(hotspotService.getHotspots(limit));
    }

    @GetMapping("/hotspots/{id}")
    public Result<HotspotVO> getHotspotDetail(@PathVariable Long id) {
        HotspotVO detail = hotspotService.getHotspotDetail(id);
        if (detail == null) {
            return Result.fail("热点不存在");
        }
        return Result.ok(detail);
    }

    @GetMapping("/dashboard/stats")
    public Result<DashboardStatsVO> getStats() {
        return Result.ok(hotspotService.getDashboardStats());
    }

    @PostMapping("/news/collect")
    public Result<CollectResultVO> triggerCollect(
            @RequestParam(defaultValue = "BAIDU") String sources) {
        return Result.ok(hotspotService.triggerCollect(sources));
    }
}
