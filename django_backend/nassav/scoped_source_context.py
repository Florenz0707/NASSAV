"""Per-operation source authorization; anonymous browser pages require bound replay."""

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from typing import Callable, Protocol
from urllib.parse import urlsplit
from threading import Lock
from time import monotonic, sleep

from nassav.credential_crypto import CredentialUnavailable
from nassav.page_fetching.contracts import FetchFailure, PageResult
from nassav.page_fetching.service import PageFetchService
from nassav.page_fetching.session import candidate_for_page
from nassav.source.CookieRepository import SourceCookieRecord
from nassav.source_credentials import (
    CHALLENGE_COOKIE_NAMES,
    cookie_values,
    CredentialSessionRecords,
    CredentialReference,
    validate_secret,
)


class ScopedSourceContext(Protocol):
    @property
    def scope_key(self) -> str: ...

    def check(self) -> None: ...

    def load_session(self) -> SourceCookieRecord | None: ...

    def publish(self, callback: Callable): ...

    def filter_headers(self, url: str, headers: dict) -> dict: ...

    def fork(self, check: Callable[[], None]) -> "ScopedSourceContext": ...

    def bind_browser_page(self, url, result, validator, direct_fetch) -> PageResult: ...

    def fetch_browser_page(
        self, url, browser_fetch, validator, direct_fetch, timeout_ms
    ) -> PageResult: ...


def allowed_origin(url, host):
    try:
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname == host
            and parts.port in {None, 443}
            and parts.username is None
            and parts.password is None
        )
    except ValueError:
        return False


class CredentialSourceContext:
    def __init__(
        self,
        records_builder: Callable[[], CredentialSessionRecords],
        source_name: str,
        *,
        user_id=None,
        credential_id=None,
        egress_profile,
        browser_context,
        capabilities,
        check=lambda: None,
    ):
        self.records_builder = records_builder
        self.source_name = source_name.lower()
        self.user_id, self.credential_id = user_id, credential_id
        self.egress_profile, self.browser_context = egress_profile, browser_context
        self.capabilities = capabilities
        self.check_execution = check
        self._records: CredentialSessionRecords | None = None
        self._reference: CredentialReference | None = None
        self._loaded = False
        self._load_lock = Lock()

    def fork(self, check):
        self.check()
        child = CredentialSourceContext(
            self.records_builder,
            self.source_name,
            user_id=self.user_id,
            credential_id=self.credential_id,
            egress_profile=self.egress_profile,
            browser_context=self.browser_context,
            capabilities=self.capabilities,
            check=check,
        )
        child._records, child._reference, child._loaded = (
            self._records,
            self._reference,
            True,
        )
        return child

    def _load(self):
        if not self._loaded:
            with self._load_lock:
                if not self._loaded:
                    records = self.records_builder()
                    ref = records.resolve(
                        self.source_name,
                        user_id=self.user_id,
                        credential_id=self.credential_id,
                    )
                    self._records, self._reference, self._loaded = records, ref, True
        assert self._records is not None
        return self._records, self._reference

    @property
    def scope_key(self):
        records, ref = self._load()
        self.check()
        return f"{ref.cache_scope if ref else 'anonymous'}:{self.egress_profile}:{self.browser_context}"

    def check(self):
        self.check_execution()
        records, ref = self._load()
        records.check_current(ref, user_id=self.user_id, source_name=self.source_name)

    def load_session(self):
        self.check()
        records, ref = self._load()
        if ref is None:
            return None
        secret, version = records.session(
            ref,
            egress_profile=self.egress_profile,
            browser_context=self.browser_context,
        )
        return SourceCookieRecord(
            self.source_name,
            secret["cookie"],
            updated_at=f"{ref.id}:{version}",
            user_agent=secret["user_agent"],
            egress_profile=None
            if self.egress_profile == "direct"
            else self.egress_profile,
        )

    def publish(self, callback):
        records, ref = self._load()
        return records.publish_current(
            ref, callback, user_id=self.user_id, source_name=self.source_name
        )

    def filter_headers(self, url, headers):
        self.check()
        _, ref = self._load()
        result = dict(headers)
        if ref is not None and not any(key.lower() == "user-agent" for key in result):
            session = self.load_session()
            if session is not None and session.user_agent:
                result["User-Agent"] = session.user_agent
        if ref is None or not allowed_origin(url, ref.origin_host):
            result = {
                key: value for key, value in result.items() if key.lower() != "cookie"
            }
        return result

    def fetch_browser_page(
        self, url, browser_fetch, validator, direct_fetch, timeout_ms
    ):
        self.check()
        records, ref = self._load()
        refused = PageResult(
            final_url=url, provider="direct", failure=FetchFailure.PAGE_MISMATCH
        )
        if not allowed_origin(
            url,
            ref.origin_host
            if ref is not None
            else records.origin_for_source(self.source_name),
        ):
            return refused
        if ref is None:
            result = browser_fetch()
            self.check()
            return result

        def probe(secret):
            record = SourceCookieRecord(
                self.source_name,
                secret["cookie"],
                user_agent=secret["user_agent"],
                egress_profile=None
                if self.egress_profile == "direct"
                else self.egress_profile,
            )
            result = direct_fetch(url, session_override=record, timeout_seconds=3)
            self.check()
            result = PageFetchService.validate_result(url, result, validator)
            return (
                result
                if result.ok
                and result.target_status == 200
                and result.elapsed_ms <= 3000
                else None
            )

        secret, baseline = records.session(
            ref,
            egress_profile=self.egress_profile,
            browser_context=self.browser_context,
        )
        current = probe(secret) if secret["cookie"] else None
        if current is not None:
            return current
        if (
            not self.capabilities.isolated_contexts
            or not self.capabilities.challenge_replay
        ):
            return refused
        lease = records.claim_refresh(
            ref,
            egress_profile=self.egress_profile,
            browser_context=self.browser_context,
            ttl_seconds=120,
        )
        if lease is None:
            started = monotonic()
            while monotonic() - started < min(timeout_ms / 1000, 120):
                self.check()
                secret, version = records.session(
                    ref,
                    egress_profile=self.egress_profile,
                    browser_context=self.browser_context,
                )
                if version != baseline:
                    result = probe(secret)
                    return (
                        replace(
                            result, lock_wait_ms=round((monotonic() - started) * 1000)
                        )
                        if result is not None
                        else refused
                    )
                if not records.refresh_busy(
                    ref,
                    egress_profile=self.egress_profile,
                    browser_context=self.browser_context,
                ):
                    return refused
                sleep(0.25)
            return refused
        try:
            return self.bind_browser_page(
                url, browser_fetch(), validator, direct_fetch, lease=lease
            )
        finally:
            records.release_refresh(lease)

    def bind_browser_page(self, url, result, validator, direct_fetch, *, lease=None):
        self.check()
        records, ref = self._load()
        if ref is None:
            return result  # Explicit anonymous scope; no legacy Cookie is loaded.
        refused = replace(
            result,
            html="",
            cookies=(),
            user_agent="",
            failure=FetchFailure.PAGE_MISMATCH,
        )
        if not result.ok:
            return refused
        if (
            not allowed_origin(url, ref.origin_host)
            or not allowed_origin(result.final_url, ref.origin_host)
            or not self.capabilities.isolated_contexts
            or not self.capabilities.challenge_replay
        ):
            return refused
        challenge_result = replace(
            result,
            cookies=tuple(
                item
                for item in result.cookies
                if isinstance(item.get("name"), str)
                and item["name"] in CHALLENGE_COOKIE_NAMES
            ),
        )
        candidate = candidate_for_page(url, challenge_result)
        if candidate is None or not PageFetchService.same_site(url, result.final_url):
            return refused
        base = records.secret(ref)
        if ref.kind == "account" and candidate.user_agent != base["user_agent"]:
            return refused
        try:
            challenge = cookie_values(candidate.cookie)
        except ValueError:
            return refused
        if not challenge:
            return refused
        merged = cookie_values(base["cookie"]) | challenge
        payload = {
            "cookie": "; ".join(f"{name}={value}" for name, value in merged.items()),
            "user_agent": candidate.user_agent,
        }
        try:
            payload = validate_secret(payload, kind="account")
        except ValueError:
            return refused
        lease = lease or records.claim_refresh(
            ref,
            egress_profile=self.egress_profile,
            browser_context=self.browser_context,
        )
        if lease is None:
            return refused
        try:
            proposed = SourceCookieRecord(
                self.source_name,
                payload["cookie"],
                user_agent=payload["user_agent"],
                egress_profile=None
                if self.egress_profile == "direct"
                else self.egress_profile,
            )
            probe = direct_fetch(url, session_override=proposed, timeout_seconds=3)
            self.check()
            probe = PageFetchService.validate_result(url, probe, validator)
            if not probe.ok or probe.target_status != 200 or probe.elapsed_ms > 3000:
                return refused
            expiry = min(
                candidate.expires_at
                or datetime.now(timezone.utc) + timedelta(minutes=5),
                datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            if not records.publish_refresh(
                lease, payload, expires_at=expiry, check=self.check_execution
            ):
                return refused
            return replace(probe, cookies=(), user_agent="")
        except CredentialUnavailable:
            raise
        finally:
            records.release_refresh(lease)
