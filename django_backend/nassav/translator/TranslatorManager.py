"""
Translator 管理器 - 管理所有翻译器的注册和调用
"""
import re
from typing import Optional, Dict, List, Tuple

from django.conf import settings
from loguru import logger

from .TranslatorBase import TranslatorBase
from .OllamaTranslator import OllamaTranslator
from nassav.constants import TRANSLATION_DICT


class TranslatorManager:
    """翻译器管理器"""

    # 翻译器类映射
    TRANSLATOR_CLASSES = {
        'ollama': OllamaTranslator,
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

        # 从配置中注册翻译器
        translator_config = getattr(settings, 'TRANSLATOR_CONFIG', {})

        # 按配置注册翻译器
        for translator_name, translator_class in self.TRANSLATOR_CLASSES.items():
            config = translator_config.get(translator_name, {})

            # 检查是否配置了该翻译器
            if config:
                try:
                    # 提取超时配置（如果有）
                    timeout_val = config.get('timeout', self.timeout)
                    translator = translator_class(timeout=timeout_val)

                    # 检查翻译器是否可用
                    if translator.is_available():
                        translator_display_name = translator.get_translator_name()
                        self.translators[translator_display_name] = translator
                        self.translator_priority.append(translator_display_name)
                    else:
                        logger.warning(f"翻译器 {translator_name} 不可用，跳过注册")
                except Exception as e:
                    logger.error(f"注册翻译器 {translator_name} 失败: {e}")

        if not self.translators:
            logger.warning("没有可用的翻译器")
        else:
            pass

    def _apply_fixed_translations(self, text: str) -> str:
        """
        应用固定词汇翻译字典

        对翻译结果中的特定词汇进行标准化替换，确保一致性

        Args:
            text: 翻译后的文本

        Returns:
            应用固定翻译后的文本
        """
        if not text or not TRANSLATION_DICT:
            return text

        result = text
        for source, target in TRANSLATION_DICT.items():
            # 使用正则进行不区分大小写的替换（保留原始大小写模式）
            pattern = re.compile(re.escape(source), re.IGNORECASE)
            result = pattern.sub(target, result)

        return result

    def get_translators(self) -> List[Tuple[str, TranslatorBase]]:
        """
        获取所有已注册的翻译器列表（按优先级排序）

        Returns:
            翻译器列表 [(名称, 翻译器实例), ...]
        """
        return [(name, self.translators[name]) for name in self.translator_priority if name in self.translators]

    def translate(self, text: str, source_lang: str = 'ja', target_lang: str = 'zh',
                 max_retries: int = 3) -> Optional[str]:
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

        # 轮询所有翻译器
        for name, translator in self.get_translators():
            try:
                result = translator.translate_with_retry(
                    text,
                    max_retries=max_retries,
                    source_lang=source_lang,
                    target_lang=target_lang
                )

                if result:
                    # 应用固定词汇翻译
                    result = self._apply_fixed_translations(result)
                    return result
                else:
                    logger.warning(f"{name} 翻译失败，尝试下一个翻译器")

            except Exception as e:
                logger.error(f"{name} 翻译异常: {e}，尝试下一个翻译器")
                continue

        logger.error(f"所有翻译器都无法翻译: {text[:50]}...")
        return None

    def translate_from_specific(self, text: str, translator_name: str,
                                source_lang: str = 'ja', target_lang: str = 'zh',
                                max_retries: int = 3) -> Optional[str]:
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

        result = translator.translate_with_retry(
            text,
            max_retries=max_retries,
            source_lang=source_lang,
            target_lang=target_lang
        )

        # 应用固定词汇翻译
        if result:
            result = self._apply_fixed_translations(result)

        return result

    def batch_translate(self, texts: List[str], source_lang: str = 'ja',
                       target_lang: str = 'zh', max_retries: int = 3) -> List[Optional[str]]:
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

        results = []

        # 优先使用第一个可用的翻译器进行批量翻译
        if self.translator_priority:
            first_translator_name = self.translator_priority[0]
            first_translator = self.translators.get(first_translator_name)

            if first_translator:
                try:
                    results = first_translator.batch_translate(texts, source_lang, target_lang)

                    # 检查是否有失败的项，对失败的项尝试其他翻译器
                    failed_indices = [i for i, r in enumerate(results) if r is None]

                    if failed_indices and len(self.translator_priority) > 1:

                        for idx in failed_indices:
                            text = texts[idx]
                            # 尝试其他翻译器
                            for translator_name in self.translator_priority[1:]:
                                translator = self.translators.get(translator_name)
                                if translator:
                                    retry_result = translator.translate_with_retry(
                                        text,
                                        max_retries=max_retries,
                                        source_lang=source_lang,
                                        target_lang=target_lang
                                    )
                                    if retry_result:
                                        results[idx] = retry_result
                                        break

                    # 应用固定词汇翻译
                    results = [self._apply_fixed_translations(r) if r else None for r in results]

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
