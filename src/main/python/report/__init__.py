"""报告模块。

## 使用方式

### 数据驱动模式（原有，快速生成结构化报告）

    from src.main.python.report import ReportGenerator, ReportData
    report_data = ReportData.from_f3_data(f3_data)
    result = ReportGenerator(report_data).generate()
    # result.content 为 Markdown

### LLM 叙事模式（借鉴 BettaFish，AI 撰写叙事性报告）

    from src.main.python.report import LLMReportGenerator, ReportData
    report_data = ReportData.from_f3_data(f3_data)
    result = LLMReportGenerator(report_data).generate(renderer_name="html")
    # result.content 为完整 HTML 页面（结构化 IR 渲染）
    # result.format == "html"
"""
from .generator import ReportGenerator, LLMReportGenerator, DeepLLMReportGenerator
from .models import ReportData, ReportResult, SectionOutput

__all__ = [
    "ReportGenerator",
    "LLMReportGenerator",
    "DeepLLMReportGenerator",
    "ReportData",
    "ReportResult",
    "SectionOutput",
]
