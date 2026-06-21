"""FactAgent 推理路径与证据链 trace 收集器。

提供 TraceCollector：一次 process_claim 对应一个实例，在推理源头记录结构化事件，
finalize() 时输出人类可读的控制台摘要 + 一个 JSON trace 文件。

retrieve.py 通过模块级 set_current/get_current 写入当前 trace（threading.local，
FastAPI 多请求安全），避免改动 LangGraph @tool 签名。

设计原则：与 LLM / 搜索引擎解耦；默认开启可关闭；不改动任何既有返回值。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 当前活跃 trace 句柄（线程局部，供 retrieve.py 等叶子节点写入）
# ---------------------------------------------------------------------------
_local = threading.local()


def set_current(trace: Optional["TraceCollector"]) -> None:
    """设置当前线程的活跃 trace；process_claim 开始时调用。"""
    _local.trace = trace


def get_current() -> Optional["TraceCollector"]:
    """获取当前线程的活跃 trace；无活跃 trace 时返回 None。"""
    return getattr(_local, "trace", None)


def _short(text: Any, limit: int = 200) -> str:
    s = str(text) if text is not None else ""
    return s if len(s) <= limit else s[:limit] + "..."


class TraceCollector:
    """收集一次事实核查的推理路径与证据链事件。"""

    def __init__(self, enabled: bool = True,
                 trace_dir: Optional[Path] = None) -> None:
        self.enabled = enabled
        # 仓库根：src/main/python/tracing.py -> parents[3]
        repo_root = Path(__file__).resolve().parents[3]
        self.trace_dir = Path(
            os.environ.get("SENTIGUARD_TRACE_DIR", repo_root / "logs" / "traces")
        )
        self.events: List[Dict[str, Any]] = []
        self._run_id: str = datetime.now().strftime("%Y%m%d_%H%M%S") + \
            f"_{threading.get_ident() & 0xffff:04x}"
        self._claim: str = ""
        self._trace_file: Optional[Path] = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def claim(self) -> str:
        return self._claim

    # ------------------------------------------------------------------
    # 事件记录
    # ------------------------------------------------------------------
    def _add(self, event: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        event.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
        self.events.append(event)

    def claim_start(self, claim: str, dataset: str, model: str) -> None:
        self._claim = claim
        self._add({
            "type": "claim_start",
            "claim": claim,
            "dataset": dataset,
            "model": model,
        })

    def claim_end(self) -> None:
        self._add({"type": "claim_end"})

    def supervisor(self, graph: str, next_worker: str) -> None:
        self._add({
            "type": "supervisor",
            "graph": graph,
            "next": next_worker,
        })

    def step(self, node: str, structured_response: Any) -> None:
        self._add({
            "type": "step",
            "node": node,
            "structured_response": structured_response,
        })

    def search(self, query: str, num_results: int,
               chosen_url: str, evidence_snippet: str,
               source_title: str = "", source_name: str = "") -> None:
        self._add({
            "type": "search",
            "query": query,
            "num_results": num_results,
            "chosen_url": chosen_url,
            "evidence_snippet": evidence_snippet,
            "source_title": source_title,
            "source_name": source_name,
        })

    def verdict(self, label: Optional[str], explanation: Optional[str]) -> None:
        self._add({
            "type": "verdict",
            "label": label,
            "explanation": explanation,
        })

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------
    def finalize(self) -> Optional[Path]:
        """打印人类可读摘要到控制台 + 写 JSON trace 文件；返回文件路径。"""
        if not self.enabled:
            return None
        self._print_summary()
        self._trace_file = self._write_json()
        return self._trace_file

    @property
    def trace_file(self) -> Optional[Path]:
        return self._trace_file

    def _write_json(self) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        path = self.trace_dir / f"trace_{self._run_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"run_id": self._run_id, "claim": self._claim,
                 "events": self.events},
                f, ensure_ascii=False, indent=2, default=str,
            )
        return path

    def _print_summary(self) -> None:
        print("\n" + "=" * 80)
        print(f"🔍 FactAgent Trace  <{self._run_id}>")
        print("=" * 80)
        print(f"claim: {_short(self._claim, 300)}")

        # 先打印 supervisor 路由序列
        routes = [e for e in self.events if e["type"] == "supervisor"]
        if routes:
            print("\n[路由路径]")
            for e in routes:
                print(f"  {e['graph']:>10} supervisor → {e['next']}")

        # 各阶段结构化输出
        print("\n[推理步骤]")
        for e in self.events:
            t = e["type"]
            if t == "step":
                self._print_step(e)
            elif t == "search":
                self._print_search(e)
            elif t == "verdict":
                print(f"\n  ── verdict ──")
                print(f"     label: {e['label']}")
                print(f"     explanation: {_short(e['explanation'], 400)}")

        print("\n" + "=" * 80)

    def _print_step(self, e: Dict[str, Any]) -> None:
        node = e["node"]
        sr = e.get("structured_response") or {}
        print(f"\n  ── {node} ──")
        if not isinstance(sr, dict):
            print(f"     {_short(sr, 300)}")
            return
        # 按各节点的已知字段友好展示，未知字段兜底 JSON
        shown = self._format_structured(node, sr)
        for line in shown:
            print(f"     {line}")

    @staticmethod
    def _format_structured(node: str, sr: Dict[str, Any]) -> List[str]:
        lines: List[str] = []

        def items_for_subclaims(key: str) -> None:
            subs = sr.get(key)
            if isinstance(subs, list):
                for i, s in enumerate(subs, 1):
                    lines.append(f"{i}. {_short(s, 160)}")

        if node in ("claim_decomposition", "claim_splitter"):
            items_for_subclaims("subclaims")
        elif node == "claim_classification":
            for i, item in enumerate(sr.get("subclaim_type_dict", []) or [], 1):
                if isinstance(item, dict):
                    lines.append(f"{i}. [{item.get('type')}] {_short(item.get('subclaim'), 160)}")
        elif node == "query_generator":
            for i, item in enumerate(sr.get("subclaim_with_questions", []) or [], 1):
                if isinstance(item, dict):
                    qs = item.get("questions", []) or []
                    lines.append(f"{i}. {_short(item.get('subclaim'), 120)}")
                    for q in qs:
                        lines.append(f"     ? {_short(q, 120)}")
        elif node == "evidence_seeker":
            for i, item in enumerate(sr.get("subclaims_with_query_evidence", []) or [], 1):
                if isinstance(item, dict):
                    lines.append(f"{i}. subclaim: {_short(item.get('subclaim'), 120)}")
                    for qe in item.get("queries_with_evidence", []) or []:
                        if isinstance(qe, dict):
                            lines.append(f"     ? {_short(qe.get('query'), 120)}")
                            lines.append(f"       evidence: {_short(qe.get('evidence'), 200)}")
        elif node == "verdict_predictor":
            res = sr.get("result") if isinstance(sr.get("result"), dict) else sr
            lines.append(f"label: {res.get('label')}")
            lines.append(f"explanation: {_short(res.get('explanation'), 300)}")
        else:
            lines.append(_short(json.dumps(sr, ensure_ascii=False, default=str), 300))
        return lines

    def _print_search(self, e: Dict[str, Any]) -> None:
        print(f"\n  [search] {_short(e['query'], 120)}")
        print(f"     → {e['num_results']} 条结果，选中: {_short(e['chosen_url'], 120)}")
        print(f"     证据: {_short(e['evidence_snippet'], 200)}")
