"""
Ollama Translator - 使用本地 Ollama 服务进行翻译
"""
import time
from typing import Optional

import requests
from django.conf import settings
from loguru import logger

from .TranslatorBase import TranslatorBase


class OllamaTranslator(TranslatorBase):
    """Ollama 翻译器"""

    def __init__(self, timeout: int = 30):
        """
        初始化 Ollama 翻译器

        Args:
            timeout: 请求超时时间（秒）
        """
        super().__init__(timeout)

        # 从配置中读取 Ollama 设置
        translator_config = getattr(settings, 'TRANSLATOR_CONFIG', {})
        ollama_config = translator_config.get('ollama', {})

        self.url = ollama_config.get('url', 'http://localhost:11434')
        self.model = ollama_config.get('model', 'qwen2.5:7b')
        self.max_retries = ollama_config.get('max_retries', 3)
        self.prompt_template = ollama_config.get(
            'prompt_template',
            '将以下日语标题翻译成简体中文，只返回翻译结果，不要添加任何解释或额外内容：\n{text}'
        )

        logger.info(f"初始化 OllamaTranslator: url={self.url}, model={self.model}")

    def get_translator_name(self) -> str:
        return "Ollama"

    def is_available(self) -> bool:
        """
        检查 Ollama 服务是否可用

        Returns:
            True 表示服务可用，False 表示不可用
        """
        try:
            # 尝试访问 Ollama API 的 /api/tags 端点
            response = requests.get(f"{self.url}/api/tags", timeout=5)
            if response.status_code == 200:
                # 检查模型是否存在
                data = response.json()
                models = data.get('models', [])
                model_names = [m.get('name', '') for m in models]

                if self.model in model_names:
                    logger.info(f"Ollama 服务可用，加载模型 {self.model}")
                    return True
                else:
                    logger.warning(f"Ollama 服务可用，但未找到模型 {self.model} ")
                    logger.info(f"可用模型: {model_names}")
                    return False
            else:
                logger.warning(f"Ollama 服务返回异常状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"检查 Ollama 服务可用性失败: {e}")
            return False

    def translate(self, text: str, source_lang: str = 'ja', target_lang: str = 'zh') -> Optional[str]:
        """
        使用 Ollama 翻译文本

        Args:
            text: 待翻译的文本
            source_lang: 源语言代码（暂未使用，默认日语）
            target_lang: 目标语言代码（暂未使用，默认中文）

        Returns:
            翻译后的文本，失败返回 None
        """
        if not text or not text.strip():
            return None

        try:
            # 构建 prompt
            prompt = self.prompt_template.format(text=text)

            # 调用 Ollama API
            start_time = time.time()
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    'model': self.model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,  # 极低随机性，提高翻译一致性
                        'top_p': 0.9,
                        'top_k': 20,  # 限制采样范围
                        'repeat_penalty': 0.8,  # 降低重复
                    }
                },
                timeout=self.timeout
            )
            elapsed = time.time() - start_time

            response.raise_for_status()
            result = response.json()

            # 提取翻译结果
            translated = result.get('response', '').strip()

            if translated:
                return translated
            else:
                logger.warning("Ollama 返回空翻译结果")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Ollama 翻译超时（{self.timeout}秒）")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama 请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"Ollama 翻译异常: {e}")
            return None

    def batch_translate(self, texts: list[str], source_lang: str = 'ja',
                       target_lang: str = 'zh') -> list[Optional[str]]:
        """
        批量翻译（逐个翻译，保持顺序）

        Args:
            texts: 待翻译的文本列表
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            翻译后的文本列表，失败的项为 None
        """
        logger.info(f"开始批量翻译 {len(texts)} 条文本")
        results = []

        for i, text in enumerate(texts, 1):
            logger.info(f"翻译进度: {i}/{len(texts)}")
            result = self.translate_with_retry(text, max_retries=self.max_retries,
                                              source_lang=source_lang, target_lang=target_lang)
            results.append(result)

            # 避免请求过快
            if i < len(texts):
                time.sleep(0.5)

        success_count = sum(1 for r in results if r is not None)
        logger.info(f"批量翻译完成: 成功 {success_count}/{len(texts)}")

        return results
