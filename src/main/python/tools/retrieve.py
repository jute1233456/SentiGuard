from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import json
import re
import unicodedata
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import requests
from urllib.parse import urlparse
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from itertools import cycle
import whois
import urllib.parse
from datetime import datetime
load_dotenv()

# Load media bias data
_MEDIA_BIAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_bias_data.json")
with open(_MEDIA_BIAS_PATH, "r", encoding="utf-8") as file:
    MEDIA_DATA = json.load(file)

# Create a dictionary for efficient URL lookup
MEDIA_BIAS_DICT = {entry.get("url"): entry for entry in MEDIA_DATA}
DATASET_DATE_LIMITS = {
        "feverous": "10/12/2021",
        "hover": "11/16/2020",
        "scifact": "10/3/2020"
    }


class SearchEngineRetriever:
    def __init__(self, dataset: str, llm: Optional["BaseLLM"] = None, headless: bool = True):
        self.skip_query_token = None
        self.dataset = dataset
        # 内容抽取用的 LLM：由调用方传入（遵循开闭原则）。
        # 不传入时默认构造豆包子类——模型名与 API Key 等细节都在 LLM 子类内部解析，本类不关心。
        if llm is None:
            from src.main.python.llms.doubao_client import DoubaoLLM
            llm = DoubaoLLM()
        self.llm = llm
        # Initialize Selenium WebDriver
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)

        # 获取搜索引擎实例
        from src.main.python.tools.search_base import get_search_engine, list_search_engines
        available = list_search_engines()
        if available:
            # 遍历注册表，找到第一个可用的引擎（兜底策略）
            engine = None
            for name in available:
                engine = get_search_engine(name)
                if engine and engine.is_available():
                    self.search_engine = engine
                    print(f"[Search] 使用搜索引擎: {name}")
                    break
            else:
                self.search_engine = None
                print(f"[Warning] 所有搜索引擎均不可用（共 {len(available)} 个）")
        else:
            self.search_engine = None
            print("[Warning] 未找到可用搜索引擎")

    def create_content_dict(self, content: list, **kwargs) -> Dict:
        resp_content = {"content": content}
        resp_content.update(**kwargs)
        return resp_content

    def _query_search_server(self, query_term):
        if self.search_engine and self.search_engine.is_available():
            try:
                results = self.search_engine.search(query_term, num_results=10)
                # 转换为旧的格式
                organic_results = []
                for r in results:
                    organic_results.append({
                        "title": r.title,
                        "link": r.url,
                        "snippet": r.snippet,
                        "content": r.content,
                        "source": r.source,
                        "published_date": r.published_date,
                        "score": r.score,
                    })
                print(f"[Search] 搜索到 {len(organic_results)} 条结果")
                return organic_results
            except Exception as e:
                logging.error(f"Search engine error: {e}")

        logging.error('No search engine available.')
        return []

    def _get_original_url(self, url):
        parsed_url = urlparse(url)
        return f"{parsed_url.netloc}/"

    def _check_valid_url(self, url):
        """
        Checks if a URL is legitimate based on:
        1. Media bias and factuality (using existing dictionary)
        2. Domain suffix analysis (.edu, .gov, .org)
        3. Publication history (domain age)
        4. Citation patterns (for scientific sources)

        Returns:
            bool: True if the URL is considered legitimate, False otherwise
        """
        # Normalize URL for consistency
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        # 1. Check against media bias dictionary
        entry = MEDIA_BIAS_DICT.get(domain)
        if entry:
            valid_factuality = {"very high", "high", "mostly factual"}
            valid_bias = {"least biased", "left-center", "right-center", "pro-science"}
            factual = entry.get("factual", "").lower()
            bias = entry.get("bias", "").lower()

            if factual in valid_factuality and bias in valid_bias:
                return True

        # 2. Domain suffix analysis
        if domain.endswith(".edu") or domain.endswith(".gov") or domain.endswith(".org"):
            return True

        # 3. Publication history (domain age)
        try:
            domain_info = whois.whois(domain)
            if domain_info.creation_date:
                # Handle both single date and list of dates
                if isinstance(domain_info.creation_date, list):
                    creation_date = domain_info.creation_date[0]
                else:
                    creation_date = domain_info.creation_date

                domain_age_years = (datetime.now() - creation_date).days / 365

                # Consider domains older than 5 years as legitimate
                if domain_age_years > 5:
                    return True
        except Exception:
            # If WHOIS lookup fails, continue to other checks
            pass

        # 4. Citation patterns (for scientific claims)
        # Check if URL is from a recognized scientific source
        scientific_domains = [
            "nature.com", "science.org", "nih.gov", "pubmed.ncbi.nlm.nih.gov",
            "sciencedirect.com", "springer.com", "wiley.com", "oxford", "cambridge.org",
            "cell.com", "nejm.org", "thelancet.com", "bmj.com", "pnas.org"
        ]

        if any(sci_domain in domain for sci_domain in scientific_domains):
            return True

        # If none of the criteria are met, return False
        return False

    def _retrieve_single(self, search_query: str):
        if search_query == self.skip_query_token:
            return None

        # 证据链 trace 句柄（无活跃 trace 时为 None，静默跳过）
        from src.main.python import tracing
        trace = tracing.get_current()

        search_server_resp = self._query_search_server(search_query)
        if not search_server_resp:
            logging.warning(
                f'Server search did not produce any results for "{search_query}" query.'
                ' returning an empty set of results for this query.'
            )
            if trace:
                trace.search(search_query, 0, "", "")
            return ""

        fallback = search_server_resp[0]
        fallback_url = fallback.get("link", "")
        fallback_title = fallback.get("title", "")
        fallback_source_name = fallback.get("source") or self._get_original_url(fallback_url).rstrip("/")
        fallback_publish_time = fallback.get("published_date") or ""
        fallback_score = self._normalize_score(fallback.get("score"))
        fallback_text = self._build_fallback_evidence(fallback)

        retrieved_doc = ""
        chosen_url = ""
        chosen_title = ""
        chosen_source_name = ""
        chosen_publish_time = ""
        chosen_score = None

        for rd in search_server_resp:
            url = rd.get("link", "")
            title = rd.get("title", "")
            snippet = rd.get("snippet", " ")
            published_date = rd.get("published_date") or ""
            # 这里必须传完整 URL，不能传 domain/，否则 urlparse 取不到 netloc。
            if not self._check_valid_url(url):
                continue

            content = self.get_details(url)
            if len(content) > 1:
                article_content = f"Article Title: {title} \nGoogle Snippet: {snippet}\nArticle Content: \n{content}"
                retrieved_doc = self._process_content(search_query, article_content)
            if not retrieved_doc:
                article_content = f"Article Title: {title} \nGoogle Snippet: {snippet}"
                retrieved_doc = self._process_content(search_query, article_content)

            if retrieved_doc and retrieved_doc.strip().lower() not in {"none", "null", "n/a"}:
                chosen_url = url
                chosen_title = title
                chosen_source_name = rd.get("source") or self._get_original_url(url).rstrip("/")
                chosen_publish_time = published_date
                chosen_score = self._normalize_score(rd.get("score"))
                break

        # 如果网页抓取/LLM 抽取失败，仍然使用搜索引擎返回的 Top1 摘要作为可落库证据。
        if not retrieved_doc or retrieved_doc.strip().lower() in {"none", "null", "n/a"}:
            retrieved_doc = fallback_text
            chosen_url = fallback_url
            chosen_title = fallback_title
            chosen_source_name = fallback_source_name
            chosen_publish_time = fallback_publish_time
            chosen_score = fallback_score

        if trace:
            trace.search(search_query, len(search_server_resp), chosen_url, retrieved_doc,
                         source_title=chosen_title, source_name=chosen_source_name,
                         publish_time=chosen_publish_time,
                         credibility_score=chosen_score)

        return retrieved_doc

    def _build_fallback_evidence(self, search_result: Dict[str, Any]) -> str:
        title = str(search_result.get("title") or "").strip()
        snippet = str(search_result.get("snippet") or "").strip()
        content = str(search_result.get("content") or "").strip()
        if content and content != snippet:
            text = content
        else:
            text = snippet
        parts = []
        if title:
            parts.append(title)
        if text:
            parts.append(text)
        return "\n".join(parts).strip()


    def _normalize_score(self, score: Any) -> Optional[int]:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return None
        if value <= 1:
            value *= 100
        return max(0, min(100, round(value)))

    def get_details(self, url):
        """Extract content from webpage using Selenium"""
        try:
            self.driver.get(url)
            # Wait for paragraphs to load
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "p")))

            # Extract all paragraph texts
            paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
            raw_para = ""

            for para in paragraphs:
                text = para.text.strip()
                if text:  # Only add non-empty paragraphs
                    text = " ".join(text.split())  # Normalize whitespace
                    text = unicodedata.normalize("NFKD", text)
                    text = re.sub(r'\n', '', text)
                    text = re.sub(r'\t', '', text)
                    raw_para += ' ' + text

            if not raw_para.strip() or len(raw_para) < 50:  # Arbitrary threshold
                logging.warning(f"Possible bot detection on {url} - No content found")
                return []

            # Detect bot-detection messages
            bot_detection_patterns = [
                r"please enable javascript",
                r"access denied",
                r"are you a robot",
                r"verify you are human",
                r"captcha"
            ]

            for pattern in bot_detection_patterns:
                if re.search(pattern, raw_para, re.IGNORECASE):
                    logging.warning(f"Bot detection triggered on {url}")
                    return []
                # Split into sentences
            sentences = self._split_into_sentences(raw_para)
            return sentences

        except TimeoutException:
            logging.warning(f"Timeout while accessing {url}")
            return []
        except Exception as e:
            logging.error(f"Error accessing {url}: {str(e)}")
            return []

    def _split_into_sentences(self, text):
        """Split text into sentences using regex patterns"""
        abbreviations = {
            "dr.": "doctor", "mr.": "mister", "bro.": "brother", "mrs.": "mistress",
            "ms.": "miss", "jr.": "junior", "sr.": "senior", "i.e.": "for example",
            "e.g.": "for example", "vs.": "versus"
        }

        # Replace abbreviations to avoid false sentence breaks
        for abbr, full in abbreviations.items():
            text = text.replace(abbr, full)

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in sentences if s.strip()]

    def _process_content(self, query: str, content: str):
        # Prompt evidence: evidence_fs_prompt (in prompt file)
        # if not enough info, add evidence
        """
        抽取网页正文中与查询相关的信息。

        通过 LLM 抽象层（src.main.python.llms）调用大模型完成抽取，
        默认使用豆包；不在此处硬编码任何具体厂商，遵循开闭原则。

        Args:
            query: The original search query.
            content: The retrieved text content from a webpage.

        Returns:
            A string containing only the information from the content that is relevant to the query.
            Returns an empty string if no relevant information is found.
        """
        prompt_template = PromptTemplate.from_template(
            """
            You are a helpful assistant who extracts information from text.
            Given the following query and text content, extract only the sentences or phrases that directly
            relate to the query. Do not include any information that is not relevant.
            If the content contains no relevant information, return None.
            Query: {query}
            Content:
            {content}
            Relevant Information:
            """
        )
        prompt = prompt_template.format(query=query, content=content)
        response = self.llm.chat(prompt, temperature=0.1)
        return response.strip() if response else ""

    def retrieve(self, queries: List[str]) -> List[Dict[str, Any]]:
        return [self._retrieve_single(q) for q in queries]

    def __del__(self):
        """Clean up browser instance"""
        if hasattr(self, 'driver'):
            self.driver.quit()


@tool
def search_retrieve_news(query: str, dataset: str):
    """
    （标准模式）快速摘要搜索，返回 10 条结果的摘要列表。

    反思模式（ReflectiveFactAgent）请使用 search_fulltext()。

    Args:
        query: The search query string.
        dataset: The dataset to use for date limits in the search (unused in summary mode).
    Returns:
        A list of dictionaries, where each dictionary represents a search result
        and contains keys like 'url', 'title', 'content', and 'snippet'.
        Returns an empty list if no results are found or if all API keys are exhausted.
    """
    from src.main.python.tools.search_service import search_summary
    try:
        results = search_summary(query, num_results=10)
        # 保持返回格式兼容：list[dict]
        return [
            {
                "title": e.evidenceTitle,
                "url": e.evidenceUrl,
                "snippet": e.evidenceContent,
                "content": e.evidenceContent,
                "source": e.sourceName,
            }
            for e in results
        ]
    except Exception as e:
        logging.error(f"Search retrieve error: {e}")
        return []




