"""
Translator 管理器 - 管理所有翻译器的注册和调用
"""
import re
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from loguru import logger
from nassav.constants import TRANSLATION_DICT

from .OllamaTranslator import OllamaTranslator
from .TranslatorBase import TranslatorBase


class TranslatorManager:
    """翻译器管理器"""

    # 翻译器类映射
    TRANSLATOR_CLASSES = {
        "ollama": OllamaTranslator,
        # 未来可以添加其他翻译器：
        # 'google': GoogleTranslator,
        # 'deepl': DeepLTranslator,
        # 'baidu': BaiduTranslator,
    }

    def __init__(self, timeout: int = 30):
        """
        初始化翻译器管理器

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.translators: Dict[str, TranslatorBase] = {}
        self.translator_priority: List[str] = []  # 翻译器优先级列表

        # 从配置中读取活动翻译器
        translator_config = getattr(settings, "TRANSLATOR_CONFIG", {})
        active_translator = getattr(settings, "ACTIVE_TRANSLATOR", "ollama")

        # 只注册活动的翻译器
        if active_translator in translator_config:
            config = translator_config[active_translator]
            translator_type = config.get("type", "ollama")  # 读取 type 字段

            # 根据 type 获取翻译器类
            translator_class = self.TRANSLATOR_CLASSES.get(translator_type)
            if not translator_class:
                logger.error(f"未知的翻译器类型: {translator_type}")
                return

            try:
                # 提取超时配置（如果有）
                timeout_val = config.get("timeout", self.timeout)
                translator = translator_class(
                    timeout=timeout_val, config_name=active_translator
                )

                # 检查翻译器是否可用
                if translator.is_available():
                    translator_display_name = translator.get_translator_name()
                    self.translators[translator_display_name] = translator
                    self.translator_priority.append(translator_display_name)
                    logger.info(
                        f"已加载翻译器: {active_translator} (type: {translator_type})"
                    )
                else:
                    logger.warning(f"翻译器 {active_translator} 不可用")
            except Exception as e:
                logger.error(f"注册翻译器 {active_translator} 失败: {e}")
        else:
            logger.warning(f"未找到活动翻译器配置: {active_translator}")

        if not self.translators:
            logger.warning("没有可用的翻译器")

    def _preprocess_fixed_terms(self, text: str) -> tuple[str, list]:
        """
        预处理：将原文中的固定翻译词汇直接替换为目标中文

        这样 LLM 在翻译时会直接保留这些中文词汇

        Args:
            text: 原始日文文本

        Returns:
            (处理后的文本, 已替换的词汇列表用于日志)
        """
        if not text or not TRANSLATION_DICT:
            return text, []

        result = text
        replaced_terms = []  # 记录已替换的词汇

        # 按词汇长度降序排序，优先匹配长词
        sorted_terms = sorted(
            TRANSLATION_DICT.items(), key=lambda x: len(x[0]), reverse=True
        )

        for jp_term, zh_term in sorted_terms:
            if jp_term in result:
                result = result.replace(jp_term, zh_term)
                replaced_terms.append((jp_term, zh_term))

        return result, replaced_terms

    def _postprocess_fixed_terms(self, text: str, replaced_terms: list) -> str:
        """
        后处理：目前采用直接替换策略，无需后处理

        Args:
            text: 翻译后的文本
            replaced_terms: 已替换的词汇列表（仅用于兼容性）

        Returns:
            原文本
        """
        return text

    def get_translators(self) -> List[Tuple[str, TranslatorBase]]:
        """
        获取所有已注册的翻译器列表（按优先级排序）

        Returns:
            翻译器列表 [(名称, 翻译器实例), ...]
        """
        return [
            (name, self.translators[name])
            for name in self.translator_priority
            if name in self.translators
        ]

    def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "zh",
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        翻译文本，自动轮询所有可用翻译器直到成功

        Args:
            text: 待翻译的文本
            source_lang: 源语言代码（默认 'ja' 日语）
            target_lang: 目标语言代码（默认 'zh' 中文）
            max_retries: 每个翻译器的最大重试次数

        Returns:
            翻译后的文本，所有翻译器都失败返回 None
        """
        if not text or not text.strip():
            return None

        if not self.translators:
            logger.error("没有可用的翻译器")
            return None

        # 预处理：将固定翻译词汇替换为占位符
        processed_text, placeholder_map = self._preprocess_fixed_terms(text)

        # 轮询所有翻译器
        for name, translator in self.get_translators():
            try:
                result = translator.translate_with_retry(
                    processed_text,
                    max_retries=max_retries,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )

                if result:
                    # 后处理：将占位符还原为目标中文词汇
                    result = self._postprocess_fixed_terms(result, placeholder_map)
                    return result
                else:
                    logger.warning(f"{name} 翻译失败，尝试下一个翻译器")

            except Exception as e:
                logger.error(f"{name} 翻译异常: {e}，尝试下一个翻译器")
                continue

        logger.error(f"所有翻译器都无法翻译: {text[:50]}...")
        return None

    def translate_from_specific(
        self,
        text: str,
        translator_name: str,
        source_lang: str = "ja",
        target_lang: str = "zh",
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        使用指定的翻译器翻译文本

        Args:
            text: 待翻译的文本
            translator_name: 翻译器名称
            source_lang: 源语言代码
            target_lang: 目标语言代码
            max_retries: 最大重试次数

        Returns:
            翻译后的文本，失败返回 None
        """
        translator = self.translators.get(translator_name)
        if not translator:
            return None

        # 预处理：将固定翻译词汇替换为占位符
        processed_text, placeholder_map = self._preprocess_fixed_terms(text)

        result = translator.translate_with_retry(
            processed_text,
            max_retries=max_retries,
            source_lang=source_lang,
            target_lang=target_lang,
        )

        # 后处理：将占位符还原为目标中文词汇
        if result:
            result = self._postprocess_fixed_terms(result, placeholder_map)

        return result

    def batch_translate(
        self,
        texts: List[str],
        source_lang: str = "ja",
        target_lang: str = "zh",
        max_retries: int = 3,
    ) -> List[Optional[str]]:
        """
        批量翻译文本列表

        Args:
            texts: 待翻译的文本列表
            source_lang: 源语言代码
            target_lang: 目标语言代码
            max_retries: 每个翻译器的最大重试次数

        Returns:
            翻译后的文本列表，失败的项为 None
        """
        if not texts:
            return []

        if not self.translators:
            logger.error("没有可用的翻译器")
            return [None] * len(texts)

        # 预处理所有文本
        processed_texts = []
        placeholder_maps = []
        for text in texts:
            processed_text, placeholder_map = self._preprocess_fixed_terms(text)
            processed_texts.append(processed_text)
            placeholder_maps.append(placeholder_map)

        results = []

        # 优先使用第一个可用的翻译器进行批量翻译
        if self.translator_priority:
            first_translator_name = self.translator_priority[0]
            first_translator = self.translators.get(first_translator_name)

            if first_translator:
                try:
                    results = first_translator.batch_translate(
                        processed_texts, source_lang, target_lang
                    )

                    # 检查是否有失败的项，对失败的项尝试其他翻译器
                    failed_indices = [i for i, r in enumerate(results) if r is None]

                    if failed_indices and len(self.translator_priority) > 1:
                        for idx in failed_indices:
                            processed_text = processed_texts[idx]
                            # 尝试其他翻译器
                            for translator_name in self.translator_priority[1:]:
                                translator = self.translators.get(translator_name)
                                if translator:
                                    retry_result = translator.translate_with_retry(
                                        processed_text,
                                        max_retries=max_retries,
                                        source_lang=source_lang,
                                        target_lang=target_lang,
                                    )
                                    if retry_result:
                                        results[idx] = retry_result
                                        break

                    # 后处理：将占位符还原为目标中文词汇
                    results = [
                        self._postprocess_fixed_terms(r, placeholder_maps[i])
                        if r
                        else None
                        for i, r in enumerate(results)
                    ]

                    success_count = sum(1 for r in results if r is not None)
                    logger.info(f"批量翻译完成: 成功 {success_count}/{len(texts)}")
                    return results

                except Exception as e:
                    logger.error(f"{first_translator_name} 批量翻译异常: {e}")

        for text in texts:
            result = self.translate(text, source_lang, target_lang, max_retries)
            results.append(result)

        # 注意：单条翻译时 translate() 已经应用了固定翻译，这里不需要重复
        return results

    def is_available(self) -> bool:
        """
        检查是否有可用的翻译器

        Returns:
            True 表示至少有一个翻译器可用，False 表示没有可用翻译器
        """
        return len(self.translators) > 0

    def get_available_translators(self) -> List[str]:
        """
        获取所有可用翻译器的名称列表

        Returns:
            翻译器名称列表
        """
        return list(self.translators.keys())


# 全局翻译器管理器实例（延迟初始化）
_translator_manager_instance: Optional[TranslatorManager] = None


def get_translator_manager() -> TranslatorManager:
    """
    获取全局翻译器管理器实例（单例模式）

    Returns:
        TranslatorManager 实例
    """
    global _translator_manager_instance
    if _translator_manager_instance is None:
        _translator_manager_instance = TranslatorManager()
    return _translator_manager_instance


# 为了向后兼容，提供一个简单的全局实例
translator_manager = get_translator_manager()
