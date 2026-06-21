import json
import re
from typing import Optional, Dict

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from dotenv import load_dotenv

from src.main.python.llms import create_chat_model
from src.main.python.llms.base import detect_provider
from src.main.python.prompts.input_ingestion import (
    claim_decomposition_prompt, claim_decomposition,
    claim_classification_prompt, claim_classification,
    claim_splitter_prompt, claim_splitting
)
from src.main.python.prompts.query_generation import query_generation_prompt, query_generation
from src.main.python.prompts.evidence_seeking import evidence_seeking_prompt, evidence_seeking
from src.main.python.prompts.verdict_prediction import verdict_prediction_prompt, verdict_prediction
from src.main.python.tools.retrieve import search_retrieve_news
from src.main.python import tracing

load_dotenv()


class State(MessagesState):
    next: str


class FactAgent:
    """主流程 Agent，通过 LLM 抽象层接入不同大模型（OpenAI / Ollama / 豆包）。

    通过 `model_name` 的前缀或关键字自动推断 provider，也可以显式传入 `provider`。
    新增模型时仅需在 `src/llms` 下新增一个 BaseLLM 子类并在 `get_llm_provider` 中注册即可，
    无需修改本文件（开闭原则）。
    """

    def __init__(self, dataset: str,
                 model_name: str = "doubao/doubao-seed-2-0-mini-260428",
                 provider: Optional[str] = None,
                 temperature: float = 0.2,
                 enable_trace: bool = True):
        self.dataset = dataset
        self.model_name = model_name
        self.provider = provider or detect_provider(model_name)
        self.temperature = temperature

        # 统一通过工厂获得 LangChain BaseChatModel
        self.llm = create_chat_model(
            model_name=self.model_name,
            provider=self.provider,
            temperature=self.temperature,
        )
        # 推理路径与证据链 trace 收集器（默认开启，可关闭）
        self.trace = tracing.TraceCollector(enabled=enable_trace)
        self._setup_agents()
        self._build_graphs()

    # ------------------------------------------------------------------
    def _make_supervisor_node(self, members: list, graph_name: str = "main"):
        options = ["FINISH"] + members

        # 在系统提示里明确加上 "json" 单词，满足豆包要求！
        system_prompt = (
            f"You are a supervisor tasked with managing a conversation between the following workers: {members}. "
            f"Given the following user request and dataset {self.dataset}, respond with the worker to act next. "
            "Each worker will perform a task and respond with their results and status. When finished, respond with FINISH. "
            "Please output your answer in valid JSON format with a single key 'next'."
        )

        def supervisor_node(state: State) -> Command:
            messages = [
                {"role": "system", "content": system_prompt},
            ] + state["messages"]

            # 不再用 with_structured_output，手动调用然后解析 JSON！
            response = self.llm.invoke(messages)
            content = response.content

            # 手动解析返回内容里的 JSON
            parsed = self._extract_json_from_content(content)
            goto = parsed.get("next", "FINISH")
            self.trace.supervisor(graph_name, goto)
            if goto == "FINISH":
                goto = END
            return Command(goto=goto, update={"next": goto})

        return supervisor_node

    def _extract_json_from_content(self, content: str) -> Dict:
        """从 LLM 返回的内容里提取 JSON，容忍 markdown 代码块等。"""
        # 先试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 再试提取 ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 最后试提取第一个 { ... } 对
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end+1])
            except json.JSONDecodeError:
                pass

        # 兜底，返回 {"next": "FINISH"}
        return {"next": "FINISH"}

    # ------------------------------------------------------------------
    def _setup_agents(self):
        self.claim_decomposition_agent = create_react_agent(
            self.llm, tools=[], prompt=claim_decomposition_prompt,
            response_format=claim_decomposition,
        )
        self.claim_classification_agent = create_react_agent(
            self.llm, tools=[], prompt=claim_classification_prompt,
            response_format=claim_classification,
        )
        self.claim_splitter_agent = create_react_agent(
            self.llm, tools=[], prompt=claim_splitter_prompt,
            response_format=claim_splitting,
        )
        self.query_generation_agent = create_react_agent(
            self.llm, tools=[], prompt=query_generation_prompt,
            response_format=query_generation,
        )
        self.evidence_seeking_agent = create_react_agent(
            self.llm, tools=[search_retrieve_news], prompt=evidence_seeking_prompt,
            response_format=evidence_seeking,
        )
        self.verdict_prediction_agent = create_react_agent(
            self.llm, tools=[], prompt=verdict_prediction_prompt,
            response_format=verdict_prediction,
        )

    # ------------------------------------------------------------------
    def _build_graphs(self):
        self._build_input_ingestion_graph()
        self._build_main_graph()

    def _build_input_ingestion_graph(self):
        def claim_decomposition_node(state: State) -> Command:
            result = self.claim_decomposition_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("claim_decomposition", sr)
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("subclaims")),
                                 name="claim_decomposition"),
                ]},
                goto="supervisor",
            )

        def claim_classification_node(state: State) -> Command:
            result = self.claim_classification_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("claim_classification", sr)
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("subclaim_type_dict")),
                                 name="claim_classification"),
                ]},
                goto="supervisor",
            )

        def claim_splitter_node(state: State) -> Command:
            result = self.claim_splitter_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("claim_splitter", sr)
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("subclaims")),
                                 name="claim_splitter"),
                ]},
                goto="supervisor",
            )

        input_ingestion_node = self._make_supervisor_node(
            ["claim_decomposition", "claim_classification", "claim_splitter"],
            graph_name="ingestion",
        )
        ingester = StateGraph(State)
        ingester.add_node("supervisor", input_ingestion_node)
        ingester.add_node("claim_decomposition", claim_decomposition_node)
        ingester.add_node("claim_classification", claim_classification_node)
        ingester.add_node("claim_splitter", claim_splitter_node)
        ingester.add_edge(START, "supervisor")
        self.ingestion_graph = ingester.compile()

    def _build_main_graph(self):
        def call_input_ingestion_team(state: State) -> Command:
            response = self.ingestion_graph.invoke({"messages": state["messages"][-1]})
            return Command(
                update={"messages": [
                    HumanMessage(content=response["messages"][-1].content,
                                 name="input_ingestor"),
                ]},
                goto="supervisor",
            )

        def query_generation_node(state: State) -> Command:
            result = self.query_generation_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("query_generator", sr)
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("subclaim_with_questions")),
                                 name="query_generator"),
                ]},
                goto="supervisor",
            )

        def evidence_seeking_node(state: State) -> Command:
            result = self.evidence_seeking_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("evidence_seeker", sr)
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("subclaims_with_query_evidence")),
                                 name="evidence_seeker"),
                ]},
                goto="supervisor",
            )

        def verdict_prediction_node(state: State) -> Command:
            result = self.verdict_prediction_agent.invoke(state)
            sr = result.get("structured_response", {})
            self.trace.step("verdict_predictor", sr)
            res = sr.get("result") if isinstance(sr.get("result"), dict) else sr
            self.trace.verdict(res.get("label"), res.get("explanation"))
            return Command(
                update={"messages": [
                    HumanMessage(content=str(sr.get("result")),
                                 name="verdict_predictor"),
                ]},
                goto="supervisor",
            )

        orchestrator = self._make_supervisor_node(
            ["input_ingestor", "query_generator", "evidence_seeker", "verdict_predictor"],
            graph_name="main",
        )
        super_builder = StateGraph(State)
        super_builder.add_node("supervisor", orchestrator)
        super_builder.add_node("input_ingestor", call_input_ingestion_team)
        super_builder.add_node("query_generator", query_generation_node)
        super_builder.add_node("evidence_seeker", evidence_seeking_node)
        super_builder.add_node("verdict_predictor", verdict_prediction_node)
        super_builder.add_edge(START, "supervisor")
        self.super_graph = super_builder.compile()

    # ------------------------------------------------------------------
    def process_claim(self, claim: str, recursion_limit: int = 200, verbose: bool = False):
        messages = [("user", claim)]
        # 设置当前 trace 句柄，供 retrieve.py 写入证据链；结束后清除
        self.trace = tracing.TraceCollector(enabled=self.trace.enabled)
        tracing.set_current(self.trace)
        self.trace.claim_start(claim, self.dataset, self.model_name)
        results = []
        try:
            for step in self.super_graph.stream(
                {"messages": messages},
                {"recursion_limit": recursion_limit},
            ):
                if verbose:
                    print(step)
                    print("---")
                results.append(step)
        finally:
            self.trace.claim_end()
            self.trace.finalize()
            tracing.set_current(None)
        return results

    def process_multiple_claims(self, claims: list, recursion_limit: int = 200, verbose: bool = False):
        results = []
        for i, claim in enumerate(claims):
            if verbose:
                print(f"\n=== Processing Claim {i+1}/{len(claims)} ===")
                print(f"Claim: {claim}")
                print("=" * 50)
            result = self.process_claim(claim, recursion_limit, verbose)
            result = json.loads(result) if isinstance(result, str) else result
            results.append({
                "claim": claim,
                "label": result.get("label") if isinstance(result, dict) else None,
                "explanation": result.get("explanation") if isinstance(result, dict) else None,
            })
        return results