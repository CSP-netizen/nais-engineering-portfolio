import base64
import json
import math
import mimetypes
from pathlib import Path
import urllib.error
import urllib.request

from .config import CONFIG


class InferenceProviderError(RuntimeError):
    pass


def _model_key(value: str) -> str:
    return "".join(
        ch for ch in value.lower()
        if ch.isalnum()
    )


class LMStudioProvider:

    def __init__(
        self,
        default_temperature: float = 0.2,
    ):
        if CONFIG.provider != "lmstudio":
            raise InferenceProviderError(
                f"Active provider is "
                f"{CONFIG.provider!r}; "
                "expected 'lmstudio'."
            )

        self.base_url = CONFIG.base_url.rstrip("/")
        self.api_token = CONFIG.api_token
        self.timeout = CONFIG.timeout_seconds
        self.default_temperature = default_temperature

        self.model = None


    def _request(
        self,
        method: str,
        path: str,
        payload=None,
    ):
        headers = {
            "Content-Type": "application/json"
        }

        if self.api_token:
            headers["Authorization"] = (
                f"Bearer {self.api_token}"
            )

        body = (
            None
            if payload is None
            else json.dumps(payload).encode("utf-8")
        )

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )

        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({})
            )

            with opener.open(
                request,
                timeout=self.timeout,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise InferenceProviderError(
                f"LM Studio HTTP {exc.code}: "
                f"{detail[:500]}"
            ) from exc

        except Exception as exc:
            raise InferenceProviderError(
                f"LM Studio unavailable: {exc}"
            ) from exc


    def list_models(self):
        return self._request(
            "GET",
            "/models",
        )


    def _resolve(
        self,
        preferred: str,
        *,
        embedding: bool = False,
    ) -> str:

        models = self.list_models().get("data", [])

        model_ids = [
            item.get("id", "")
            for item in models
            if item.get("id")
        ]

        if not model_ids:
            raise InferenceProviderError(
                "LM Studio exposes no models."
            )

        # Exact ID
        if preferred in model_ids:
            return preferred

        # Fuzzy match so different GGUF identifiers still work.
        wanted = (
            _model_key(preferred.split("/")[-1])
            if preferred
            else ""
        )

        if wanted:
            matches = [
                model_id
                for model_id in model_ids
                if wanted in _model_key(model_id)
            ]

            if len(matches) == 1:
                return matches[0]

            raise InferenceProviderError("Configured model unavailable or ambiguous")

        # Sensible fallback.
        if embedding:
            matches = [
                model_id
                for model_id in model_ids
                if "embed" in model_id.lower()
            ]
        else:
            matches = [
                model_id
                for model_id in model_ids
                if "embed" not in model_id.lower()
            ]

        if matches:
            return matches[0]

        raise InferenceProviderError(
            "Could not resolve model "
            f"{preferred!r}. "
            f"LM Studio models: {model_ids}"
        )


    def resolve_model(self) -> str:
        if self.model is None:
            self.model = self._resolve(
                CONFIG.model,
                embedding=False,
            )

        return self.model


    def probe(self) -> str:
        return self.resolve_model()


    def chat(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:

        messages = []

        if system:
            messages.append({
                "role": "system",
                "content": system,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        payload = {
            "model": self.resolve_model(),
            "messages": messages,
            "temperature": (
                self.default_temperature
                if temperature is None
                else temperature
            ),
            "stream": False,
        }

        data = self._request(
            "POST",
            "/chat/completions",
            payload,
        )

        try:
            return (
                data["choices"][0]
                ["message"]["content"]
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise InferenceProviderError(
                "Unexpected LM Studio response: "
                f"{data}"
            ) from exc


    # Compatibility with the existing LangChain-style call sites.
    def invoke(self, prompt: str) -> str:
        return self.chat(prompt)


    def vision(
        self,
        image_path: str | Path,
        prompt: str,
    ) -> str:

        path = Path(image_path)

        mime_type = (
            mimetypes.guess_type(path.name)[0]
            or "image/png"
        )

        encoded = base64.b64encode(
            path.read_bytes()
        ).decode("ascii")

        data_url = (
            f"data:{mime_type};base64,{encoded}"
        )

        payload = {
            "model": self.resolve_model(),

            "messages": [{
                "role": "user",

                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                        },
                    },
                ],
            }],

            "temperature": 0,
            "stream": False,
        }

        data = self._request(
            "POST",
            "/chat/completions",
            payload,
        )

        return (
            data["choices"][0]
            ["message"]["content"]
        )


class LMStudioEmbedding:

    def __init__(
        self,
        model: str | None = None,
    ):
        self.client = LMStudioProvider(
            default_temperature=0
        )

        self.model = self.client._resolve(
            model or CONFIG.embed_model,
            embedding=True,
        )

        # The signature participates in IP Fabric cache
        # invalidation. A provider/model change therefore
        # invalidates previous vectors automatically.
        self.signature = (
            f"{self.model}"
            "@lmstudio-openai-v1"
            ":nomic-prefix-v1"
        )


    def embed(
        self,
        texts,
        query: bool = False,
    ):
        if not texts:
            return []

        prefix = ""

        if "nomic" in self.model.lower():
            prefix = (
                "search_query: "
                if query
                else "search_document: "
            )

        payload = {
            "model": self.model,
            "input": [
                prefix + text
                for text in texts
            ],
        }

        result = self.client._request(
            "POST",
            "/embeddings",
            payload,
        )

        items = sorted(
            result.get("data", []),
            key=lambda item: item.get("index", 0),
        )

        vectors = [
            item.get("embedding")
            for item in items
        ]

        if len(vectors) != len(texts):
            raise InferenceProviderError(
                "Embedding response count mismatch"
            )

        for vector in vectors:
            if (
                not vector
                or not all(
                    math.isfinite(value)
                    for value in vector
                )
                or not any(vector)
            ):
                raise InferenceProviderError(
                    "Invalid embedding returned "
                    "by LM Studio"
                )

        return vectors
