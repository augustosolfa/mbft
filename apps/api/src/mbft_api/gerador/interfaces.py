from typing import Protocol

class ILLMClient(Protocol):
    """
    Contrato agnóstico para geração de texto.
    Abstrai o cliente HTTP (Fetch API no Workers ou httpx local).
    """

    async def gerar_resposta(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """
        Gera a resposta do LLM com base nos prompts fornecidos.

        Args:
            system_prompt: O prompt de sistema com as regras rígidas do RAG.
            user_prompt: A pergunta do usuário concatenada com o contexto recuperado.
            temperature: Grau de aleatoriedade (cravado em 0.0 para Strict RAG).
            max_tokens: Limite máximo de tokens de saída para evitar Timeout no Edge.

        Returns:
            O texto gerado pelo modelo.
        """
        ...
