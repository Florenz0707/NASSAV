"""
Translator 模块 - 提供翻译服务
"""
from .OllamaTranslator import OllamaTranslator
from .TranslatorBase import TranslatorBase
from .TranslatorManager import (
    TranslatorManager,
    get_translator_manager,
    translator_manager,
)

__all__ = [
    "TranslatorBase",
    "OllamaTranslator",
    "TranslatorManager",
    "translator_manager",
    "get_translator_manager",
]
