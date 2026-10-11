import re
from typing import Any, Dict

from ..recuperador.cloudflare_adapters import _to_js, _to_python
from .interfaces import ILLMClient

DEFAULT_CF_LLM_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8-fast"

_RE_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_RE_THINK_UNOPENED = re.compile(r"^.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_RE_THINK_UNCLOSED = re.compile(r"<think>.*$", flags=re.DOTALL | re.IGNORECASE)


def limpar_bloco_think(texto: str) -> str:
    """
    Remove blocos de raciocínio `<think>...</think>` gerados por modelos como DeepSeek R1,
    incluindo casos em que a tag de abertura foi omitida pelo template ou truncada por max_tokens.
    """
    if not texto:
        return ""
    limpo = _RE_THINK_BLOCK.sub("", texto)
    limpo = _RE_THINK_UNOPENED.sub("", limpo)
    limpo = _RE_THINK_UNCLOSED.sub("", limpo)
    return limpo.strip()


class WorkersAILLMClient(ILLMClient):
    """
    Implementação de produção do `ILLMClient` sobre o binding `env.AI` do Cloudflare Workers AI.
    Parametrizável via `CF_LLM_MODEL` (padrão: `@cf/meta/llama-3.1-8b-instruct-fp8-fast`).
    """

    def __init__(self, ai_binding: Any, model: str = DEFAULT_CF_LLM_MODEL):
        self.ai = ai_binding
        self.model = model or DEFAULT_CF_LLM_MODEL

    async def gerar_resposta(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        raw_res = await self.ai.run(self.model, _to_js(payload))
        res = _to_python(raw_res)

        texto_bruto = ""
        if isinstance(res, str):
            texto_bruto = res
        elif isinstance(res, dict):
            resp_val = _to_python(res.get("response"))
            choices = _to_python(res.get("choices"))
            if resp_val is not None:
                texto_bruto = str(resp_val)
            elif isinstance(choices, (list, tuple)) and choices:
                first_choice = _to_python(choices[0])
                if isinstance(first_choice, dict):
                    msg = _to_python(first_choice.get("message") or {})
                    msg_content = _to_python(msg.get("content")) if isinstance(msg, dict) else None
                    choice_text = _to_python(first_choice.get("text"))
                    if msg_content is not None:
                        texto_bruto = str(msg_content)
                    elif choice_text is not None:
                        texto_bruto = str(choice_text)
        elif hasattr(res, "response"):
            resp_attr = _to_python(getattr(res, "response", None))
            if resp_attr is not None:
                texto_bruto = str(resp_attr)

        return limpar_bloco_think(texto_bruto)
