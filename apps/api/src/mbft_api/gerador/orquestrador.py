from .interfaces import ILLMClient
from .prompts import SYSTEM_PROMPT_TEMPLATE

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
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(contexto=contexto_formatado)
        
        return await self.llm_client.gerar_resposta(
            system_prompt=system_prompt,
            user_prompt=pergunta,
            temperature=0.0,
            max_tokens=1024 # Limite conservador para evitar Timeout no Workers
        )
