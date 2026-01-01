"""
Translator 模块 - 提供翻译服务
"""
from .TranslatorBase import TranslatorBase
from .OllamaTranslator import OllamaTranslator
from .TranslatorManager import TranslatorManager, translator_manager, get_translator_manager

__all__ = [
    'TranslatorBase',
    'OllamaTranslator',
    'TranslatorManager',
    'translator_manager',
    'get_translator_manager'
]
