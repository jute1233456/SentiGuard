import json
import os
from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI as LangChainChatOpenAI
from openai import OpenAI

from src.main.python.llms.base import BaseLLM, LLMProvider


class OpenAILLM(BaseLLM):
    """OpenAI 官方 API 的封装。"""

    provider = LLMProvider.OPENAI

    def __init__(self, model_name: str = "gpt-4o-mini",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 temperature: float = 0.2, **kwargs: Any):
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OPENAI_API_KEY 未提供。请在环境变量或构造参数中设置。"
            )
        super().__init__(model_name=model_name, api_key=resolved_key,
                         base_url=base_url, temperature=temperature, **kwargs)

    # ------------------------------------------------------------------
    def _build_client(self):
        """构建原生 openai SDK 客户端，用于 chat / chat_with_json。"""
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ------------------------------------------------------------------
    def chat(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    def chat_with_json(self, prompt: str,
                        json_schema: Optional[Dict[str, Any]] = None,
                        system_prompt: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        messages: list = []
        final_system = system_prompt or "你是一个善于输出结构化 JSON 的助手。"
        messages.append({"role": "system", "content": final_system})
        messages.append({"role": "user", "content": prompt})

        extra: Dict[str, Any] = {}
        if json_schema is not None:
            # 使用 response_format=json_schema 做严格约束
            schema_name = json_schema.get("name") or "response"
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                },
            }
        else:
            extra["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **extra,
        )
        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ValueError(f"LLM 返回内容不是合法 JSON：\n{content}")

    # ------------------------------------------------------------------
    def as_langchain_chat_model(self) -> BaseChatModel:
        """返回 LangChain ChatOpenAI 实例，支持 with_structured_output。"""
        return LangChainChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
