"""Translation records and replaceable persistence/text capabilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranslationRecord:
    pk: int
    avid: str
    original_title: str | None
    source_title: str | None
    translated_title: str | None
    translation_status: str


class TranslationRepository(ABC):
    @abstractmethod
    def get(self, avid: str) -> TranslationRecord | None: ...
    @abstractmethod
    def select(
        self, avids: list[str] | None, skip_existing: bool
    ) -> list[TranslationRecord]: ...
    @abstractmethod
    def save(self, record: TranslationRecord, fields: list[str]) -> None: ...
    @abstractmethod
    def mark_translating(self, ids: list[int]) -> None: ...
    @abstractmethod
    def fail_inflight(self, ids: list[int]) -> None: ...


class TextTranslator(ABC):
    @abstractmethod
    def translate(self, text: str) -> str | None: ...
    @abstractmethod
    def batch_translate(self, texts: list[str]) -> list[str | None]: ...


class TranslationWorkflow(ABC):
    @abstractmethod
    def translate(self, avid: str) -> dict: ...
    @abstractmethod
    def translate_batch(
        self, avids: list[str] | None = None, skip_existing: bool = True
    ) -> dict: ...
