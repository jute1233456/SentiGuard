from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel


class LLMProvider:
    OPENAI = "openai"
    OLLAMA = "ollama"
    DOUBAO = "doubao"

    _ALL = {OPENAI, OLLAMA, DOUBAO}


class BaseLLM(ABC):
    """LLM 调用的抽象基类，遵循开闭原则。

    新增一个大模型提供商时，只需：
      1. 继承 BaseLLM 并实现抽象方法；
      2. 在 `get_llm_provider` 的注册表里追加一项，
         或在 `detect_provider` 增加一段前缀识别逻辑。

    子类不应该修改本基类中的任何既有代码。
    """

    provider: str = "base"

    def __init__(self, model_name: str, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, temperature: float = 0.2, **kwargs: Any):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = kwargs.pop("max_tokens", 16384)  # 默认 16K，解决 structured output 截断问题
        self.extra_kwargs = kwargs
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # 子类必须实现的两个抽象方法
    # ------------------------------------------------------------------
    @abstractmethod
    def _build_client(self):
        """构建并返回底层的 LLM 客户端对象。"""
        ...

    @abstractmethod
    def chat(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        """发送一条文本 prompt 并返回模型生成的文本响应。"""
        ...

    @abstractmethod
    def chat_with_json(self, prompt: str, json_schema: Optional[Dict[str, Any]] = None,
                       system_prompt: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """发送一条文本 prompt 并要求模型返回 JSON 对象。

        Args:
            prompt: 用户 prompt。
            json_schema: 可选的 JSON schema 约束。如不提供则使用通用提示让模型输出 JSON。
            system_prompt: 可选的系统提示。
        """
        ...

    @abstractmethod
    def as_langchain_chat_model(self) -> BaseChatModel:
        """返回一个可直接用于 LangChain/LangGraph 的 BaseChatModel 实例。

        该对象支持 `.with_structured_output(...)`，用于 main_agent 的 ReAct Agent 等流程。
        """
        ...

    # ------------------------------------------------------------------
    # 工厂：统一入口
    # ------------------------------------------------------------------


def detect_provider(model_name: str) -> str:
    """根据 model 名称自动推断 provider。

    规则（按顺序匹配，命中即返回）：
      - 前缀 `ollama/` 或包含 `ollama` -> OLLAMA
      - 前缀 `doubao/` 或包含 `doubao` -> DOUBAO
      - 其它 -> OPENAI
    """
    name_lower = model_name.lower()
    if name_lower.startswith("ollama/") or "ollama" in name_lower:
        return LLMProvider.OLLAMA
    if name_lower.startswith("doubao/") or "doubao" in name_lower:
        return LLMProvider.DOUBAO
    return LLMProvider.OPENAI


def get_llm_provider(model_name: str, provider: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: Optional[str] = None,
                     temperature: float = 0.2, **kwargs: Any) -> BaseLLM:
    """工厂函数：根据 provider（或自动检测）返回对应的 BaseLLM 实例。"""
    provider = (provider or detect_provider(model_name)).lower()

    if provider == LLMProvider.OPENAI:
        from src.main.python.llms.openai_client import OpenAILLM
        return OpenAILLM(model_name=model_name, api_key=api_key,
                         base_url=base_url, temperature=temperature, **kwargs)

    if provider == LLMProvider.OLLAMA:
        from src.main.python.llms.ollama_client import OllamaLLM
        # Ollama 不需要 api_key / base_url，走本地服务
        raw_model = model_name.replace("ollama/", "", 1) if model_name.lower().startswith("ollama/") else model_name
        return OllamaLLM(model_name=raw_model, temperature=temperature, **kwargs)

    if provider == LLMProvider.DOUBAO:
        from src.main.python.llms.doubao_client import DoubaoLLM
        raw_model = model_name.replace("doubao/", "", 1) if model_name.lower().startswith("doubao/") else model_name
        return DoubaoLLM(model_name=raw_model, api_key=api_key,
                         base_url=base_url, temperature=temperature, **kwargs)

    raise ValueError(
        f"未知的 LLM provider: {provider!r}；可用值为 {sorted(LLMProvider._ALL)}。"
        "如需新增提供商，请继承 src.llms.base.BaseLLM 并在此函数中注册。"
    )


def create_chat_model(model_name: str, provider: Optional[str] = None,
                      api_key: Optional[str] = None, base_url: Optional[str] = None,
                      temperature: float = 0.2, **kwargs: Any) -> BaseChatModel:
    """便捷函数：直接返回一个 LangChain 的 BaseChatModel 实例。"""
    llm = get_llm_provider(model_name=model_name, provider=provider,
                           api_key=api_key, base_url=base_url,
                           temperature=temperature, **kwargs)
    return llm.as_langchain_chat_model()


def invoke_with_json(model_name: str, prompt: str,
                     json_schema: Optional[Dict[str, Any]] = None,
                     system_prompt: Optional[str] = None,
                     provider: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: Optional[str] = None,
                     temperature: float = 0.2, **kwargs: Any) -> Dict[str, Any]:
    """便捷函数：直接调用 LLM 并返回 JSON 结果。"""
    llm = get_llm_provider(model_name=model_name, provider=provider,
                           api_key=api_key, base_url=base_url,
                           temperature=temperature, **kwargs)
    return llm.chat_with_json(prompt=prompt, json_schema=json_schema,
                              system_prompt=system_prompt, **kwargs)
