import json
import os
import re
from typing import Any, Dict, Optional, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI as LangChainChatOpenAI
from openai import OpenAI

from src.main.python.llms.base import BaseLLM, LLMProvider


# 豆包（字节跳动/火山引擎方舟）默认接入点
# 官方文档: https://www.volcengine.com/docs/82379/1298454
_DEFAULT_DOUBUO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


class DoubaoLLM(BaseLLM):
    """字节跳动豆包（Doubao）大模型的封装。

    使用火山引擎方舟平台（Ark）的 OpenAI 兼容 Chat Completions 接口。

    常用模型名（在代码中可以直接使用）：
        - doubao-pro-4k: 标准版，4K 上下文
        - doubao-pro-32k: 长文本版，32K 上下文
        - doubao-lite-4k: 轻量版，快速响应
        - doubao-seed-2-0-mini-260428: 本次验证使用的模型
    """

    provider = LLMProvider.DOUBAO

    def __init__(self, model_name: str = "doubao-seed-2-0-mini-260428",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 temperature: float = 0.2, **kwargs: Any):
        # API Key 优先级：DOUBAO_API_KEY 环境变量 > ARK_API_KEY 环境变量 > 传入参数
        resolved_key = os.environ.get("DOUBAO_API_KEY") or os.environ.get("ARK_API_KEY") or api_key
        if not resolved_key:
            raise ValueError(
                "DOUBAO_API_KEY / ARK_API_KEY 未提供。请在环境变量或构造参数中设置。"
            )
        # Base URL 优先级：DOUBAO_BASE_URL 环境变量 > ARK_BASE_URL 环境变量 > 传入参数 > 默认值
        resolved_url = (
            os.environ.get("DOUBAO_BASE_URL")
            or os.environ.get("ARK_BASE_URL")
            or base_url
            or _DEFAULT_DOUBUO_BASE_URL
        )
        super().__init__(model_name=model_name, api_key=resolved_key,
                         base_url=resolved_url, temperature=temperature, **kwargs)

    def _build_client(self):
        """构建 OpenAI 兼容客户端，指向火山引擎方舟接口。"""
        # 添加更好的连接配置，处理 SSL 问题
        import httpx

        # 创建自定义 httpx 客户端，增加超时和 SSL 配置
        http_client = httpx.Client(
            timeout=60.0,  # 增加超时时间
            verify=True,   # 默认保持 SSL 验证
        )

        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=http_client,
            timeout=60.0,
        )

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

    def chat_with_json(self, prompt: str,
                        json_schema: Optional[Dict[str, Any]] = None,
                        system_prompt: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        # 将 schema 写入 system prompt，辅助模型理解约束
        schema_hint = ""
        if json_schema is not None:
            try:
                schema_hint = (
                    "\n\n请严格按照以下 JSON Schema 输出结果：\n"
                    + json.dumps(json_schema, ensure_ascii=False, indent=2)
                )
            except Exception:
                schema_hint = ""

        final_system = (system_prompt or "你是一个善于输出结构化 JSON 的助手。") + schema_hint

        messages: list = [
            {"role": "system", "content": final_system},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                response_format={"type": "json_object"},
            )
        except Exception:
            # 回退：不带 response_format 调用，完全依赖 prompt 提示
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )

        content = response.choices[0].message.content or "{}"
        return _parse_json_output(content)

    def as_langchain_chat_model(self) -> BaseChatModel:
        """
        返回可用于 LangChain / LangGraph 的 BaseChatModel 实例，
        自动适配豆包对 JSON 输出的特殊要求（在 messages 里包含 "json"）。
        """

        # 我们返回一个继承自 LangChainChatOpenAI 的子类，重写 _create_message_dicts
        class DoubaoLangChainModel(LangChainChatOpenAI):
            def _create_message_dicts(
                self, messages: List[BaseMessage], stop: Optional[List[str]] = None
            ) -> List[Dict[str, Any]]:
                # 先调用父类方法生成标准的 message dicts
                message_dicts = super()._create_message_dicts(messages, stop)
                # 然后确保 messages 里有 "json"
                has_json = False
                for msg in message_dicts:
                    content = msg.get("content", "")
                    if isinstance(content, str) and "json" in content.lower():
                        has_json = True
                        break

                if not has_json:
                    # 给第一个 system message 加个 "json" 提示，或者创建新的
                    if message_dicts and message_dicts[0]["role"] == "system":
                        message_dicts[0]["content"] += "\nPlease respond in valid JSON format."
                    else:
                        message_dicts.insert(0, {"role": "system", "content": "Please respond in valid JSON format."})

                return message_dicts

        # 返回我们的自定义子类实例
        return DoubaoLangChainModel(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=60.0,
        )


# ----------------------------------------------------------------------
# 工具函数：从 LLM 文本响应中抽取 JSON
# ----------------------------------------------------------------------
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _parse_json_output(text: str) -> Dict[str, Any]:
    """尽力从模型输出中解析 JSON，容忍 markdown 代码块、前后空白文本。"""
    if text is None:
        return {}
    candidate = text.strip()

    # 1. 直接尝试
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 2. 提取 ```json ... ``` 代码块
    m = _JSON_BLOCK_RE.search(candidate)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 定位最外层的大括号 / 方括号
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"豆包模型返回内容不是合法 JSON：\n{text}")
