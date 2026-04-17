from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any

import requests
from requests.utils import parse_header_links

from .config import GreenhouseConfig


class HarvestClient:
    def __init__(self, config: GreenhouseConfig, timeout: int = 60) -> None:
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        form_data = {"grant_type": "client_credentials"}
        if self.config.user_id:
            form_data["sub"] = self.config.user_id

        response = self.session.post(
            self.config.token_url,
            auth=(self.config.client_id, self.config.client_secret),
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        self._token = payload["access_token"]
        expires_at = payload.get("expires_at")
        if expires_at:
            self._token_expires_at = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            ).timestamp()
        else:
            self._token_expires_at = time.time() + 3600
        return self._token

    def _request(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        for attempt in range(5):
            response = self.session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._get_access_token()}"},
                timeout=self.timeout,
            )
            if response.status_code != 429:
                response.raise_for_status()
                return response

            retry_after = int(response.headers.get("Retry-After", "5"))
            time.sleep(retry_after)

        response.raise_for_status()
        return response

    @staticmethod
    def _parse_next_url(link_header: str | None) -> str | None:
        if not link_header:
            return None
        for link in parse_header_links(link_header.rstrip(">").replace(">,", ">, ")):
            if link.get("rel") == "next":
                return link.get("url")
        return None

    def fetch_endpoint(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        next_url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        next_params = {"per_page": self.config.per_page, **(params or {})}
        records: list[dict[str, Any]] = []

        while next_url:
            response = self._request(next_url, params=next_params)
            page_records = response.json()
            if not isinstance(page_records, list):
                raise ValueError(f"Expected list response for {endpoint}, got {type(page_records)}")

            records.extend(page_records)
            if limit is not None and len(records) >= limit:
                return records[:limit]

            next_url = self._parse_next_url(response.headers.get("Link"))
            next_params = None

        return records

    @staticmethod
    def extraction_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
