"""Durable data behind one URL: file://, s3://, gs:// or az://.

Credentials come from the usual cloud environment variables (AWS_*, GOOGLE_*, AZURE_*) or workload identity, so the
same code runs on a laptop, against in-cluster SeaweedFS, or on a managed bucket."""

import json
from pathlib import Path
from typing import TypeVar

import obstore
from obstore.store import LocalStore, from_url
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def input_key(sha: str) -> str:
    return f"inputs/{sha}"


def manifest_key(doc_sha: str, route_key: str) -> str:
    return f"manifests/{doc_sha}/{route_key}.json"


def job_key(job_id: str) -> str:
    return f"jobs/{job_id}.json"


def thumb_key(doc_sha: str, index: int) -> str:
    return f"thumbs/{doc_sha}/{index}.jpg"


def cache_key(provider: str, digest: str) -> str:
    return f"cache/{provider}/{digest[:2]}/{digest}.json"


class Store:
    def __init__(self, url: str, config: dict[str, str] | None = None, client_options: dict[str, str] | None = None):
        if url.startswith("file://"):
            root = Path(url.removeprefix("file://")).expanduser().resolve()
            self.url = f"file://{root}"
            self._store = LocalStore(root, mkdir=True)
        else:
            self.url = url
            self._store = from_url(url, config=config or None, client_options=client_options or None)

    @classmethod
    def from_settings(cls, settings) -> "Store":
        return cls(settings.store_url, settings.store_config, settings.store_client_options)

    async def get(self, key: str) -> bytes | None:
        try:
            result = await obstore.get_async(self._store, key)
        except FileNotFoundError:
            return None
        return bytes(await result.bytes_async())

    async def put(self, key: str, data: bytes) -> None:
        await obstore.put_async(self._store, key, data)

    async def exists(self, key: str) -> bool:
        try:
            await obstore.head_async(self._store, key)
        except FileNotFoundError:
            return False
        return True

    async def get_json(self, key: str) -> dict | None:
        data = await self.get(key)
        return None if data is None else json.loads(data)

    async def get_model(self, key: str, model: type[T]) -> T | None:
        data = await self.get(key)
        return None if data is None else model.model_validate_json(data)

    async def put_json(self, key: str, obj: BaseModel | dict) -> None:
        data = obj.model_dump_json() if isinstance(obj, BaseModel) else json.dumps(obj, ensure_ascii=False)
        await self.put(key, data.encode())
