import json
from typing import Any, Dict, Optional

import ollama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama

from src.main.python.llms.base import BaseLLM, LLMProvider


class OllamaLLM(BaseLLM):
    """本地 Ollama 服务的封装。"""

    provider = LLMProvider.OLLAMA

    def __init__(self, model_name: str = "qwen2.5:3b",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 temperature: float = 0.2, **kwargs: Any):
        super().__init__(model_name=model_name, api_key=api_key,
                         base_url=base_url, temperature=temperature, **kwargs)

    # ------------------------------------------------------------------
    def _build_client(self):
        """Ollama SDK 不需要显式构建客户端，但在这里确保模型可用。"""
        try:
            ollama.chat(self.model_name, messages=[{"role": "user", "content": "ping"}])
        except ollama.ResponseError as e:
            if "not found" in str(e).lower() or getattr(e, "status_code", None) == 404:
                ollama.pull(self.model_name)
            else:
                # 其它错误（例如本地 ollama 服务未启动）也向上抛出，便于定位
                raise
        return ollama

    # ------------------------------------------------------------------
    def chat(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            options={
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
        )
        return response.get("message", {}).get("content", "")

    # ------------------------------------------------------------------
    def chat_with_json(self, prompt: str,
                        json_schema: Optional[Dict[str, Any]] = None,
                        system_prompt: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        messages: list = []
        final_system = system_prompt or "你是一个善于输出结构化 JSON 的助手。"
        messages.append({"role": "system", "content": final_system})
        messages.append({"role": "user", "content": prompt})

        # Ollama 使用 format=json 来约束输出；schema 作为可选提示写入 prompt
        response = self._client.chat(
            model=self.model_name,
            messages=messages,
            stream=False,
            format=json_schema if json_schema is not None else "json",
            options={
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
        )
        content = response.get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ValueError(f"LLM 返回内容不是合法 JSON：\n{content}")

    # ------------------------------------------------------------------
    def as_langchain_chat_model(self) -> BaseChatModel:
        """返回 LangChain ChatOllama 实例。"""
        return ChatOllama(model=self.model_name, temperature=self.temperature,
                         num_predict=self.max_tokens)
