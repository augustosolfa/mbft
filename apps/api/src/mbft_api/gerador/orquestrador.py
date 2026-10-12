import re
from .interfaces import ILLMClient
from .prompts import SYSTEM_PROMPT_TEMPLATE, FRASE_CANONICA_RECUSA

class OrquestradorGeracao:
    """
    Orquestra o fluxo de geração RAG (Strict RAG e Stateless).
    """
    def __init__(self, llm_client: ILLMClient):
        self.llm_client = llm_client

    async def gerar_resposta(self, pergunta: str, contexto_formatado: str) -> str:
        """
        Recebe a pergunta do usuário e o contexto estruturado (Fichas/Regras),
        monta o prompt e aciona o LLM via interface injetada.

        Args:
            pergunta: A pergunta natural do usuário.
            contexto_formatado: O texto contendo as regras/fichas recuperadas.

        Returns:
            A resposta redigida pelo LLM.
        """
        if not contexto_formatado or not contexto_formatado.strip():
            return FRASE_CANONICA_RECUSA

        pergunta_limpa = re.sub(r"</?pergunta_usuario>", "", pergunta.strip(), flags=re.IGNORECASE)
        if not pergunta_limpa.strip():
            return FRASE_CANONICA_RECUSA

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(contexto=contexto_formatado)
        user_prompt = f"<pergunta_usuario>{pergunta_limpa}</pergunta_usuario>"
        
        return await self.llm_client.gerar_resposta(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=1024 # Limite conservador para evitar Timeout no Workers
        )

    def montar_prompt(self, pergunta: str, contexto_formatado: str) -> str:
        """
        Monta o prompt completo estruturado (system prompt + user prompt encapado).
        """
        pergunta_limpa = re.sub(r"</?pergunta_usuario>", "", pergunta.strip(), flags=re.IGNORECASE)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(contexto=contexto_formatado)
        user_prompt = f"<pergunta_usuario>{pergunta_limpa}</pergunta_usuario>"
        return f"{system_prompt}\n\n{user_prompt}"
