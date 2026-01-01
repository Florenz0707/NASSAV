"""
Translator 基类 - 定义翻译器的通用接口
"""
from typing import Optional
from abc import ABC, abstractmethod

from loguru import logger


class TranslatorBase(ABC):
    """翻译器基类"""

    def __init__(self, timeout: int = 30):
        """
        初始化翻译器

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout

    @abstractmethod
    def get_translator_name(self) -> str:
        """获取翻译器名称，子类必须实现"""
        raise NotImplementedError

    @abstractmethod
    def translate(self, text: str, source_lang: str = 'ja', target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本

        Args:
            text: 待翻译的文本
            source_lang: 源语言代码（默认 'ja' 日语）
            target_lang: 目标语言代码（默认 'zh' 中文）

        Returns:
            翻译后的文本，失败返回 None
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查翻译服务是否可用

        Returns:
            True 表示服务可用，False 表示不可用
        """
        raise NotImplementedError

    def translate_with_retry(self, text: str, max_retries: int = 3,
                            source_lang: str = 'ja', target_lang: str = 'zh') -> Optional[str]:
        """
        带重试机制的翻译

        Args:
            text: 待翻译的文本
            max_retries: 最大重试次数
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            翻译后的文本，失败返回 None
        """
        if not text or not text.strip():
            logger.warning("翻译文本为空")
            return None

        translator_name = self.get_translator_name()

        for attempt in range(max_retries):
            try:
                result = self.translate(text, source_lang, target_lang)

                if result:
                    logger.info(f"{translator_name}: 翻译成功")
                    return result
                else:
                    logger.warning(f"{translator_name}: 翻译返回空结果")

            except Exception as e:
                logger.error(f"{translator_name}: 翻译失败（第 {attempt + 1}/{max_retries} 次）: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"{translator_name}: 已达最大重试次数，翻译失败")
                    return None

        return None

    def batch_translate(self, texts: list[str], source_lang: str = 'ja',
                       target_lang: str = 'zh') -> list[Optional[str]]:
        """
        批量翻译（默认实现为逐个翻译，子类可重写以提高效率）

        Args:
            texts: 待翻译的文本列表
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            翻译后的文本列表，失败的项为 None
        """
        results = []
        for text in texts:
            result = self.translate_with_retry(text, source_lang=source_lang, target_lang=target_lang)
            results.append(result)
        return results
