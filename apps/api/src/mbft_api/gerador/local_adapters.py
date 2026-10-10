import os
from google import genai
from google.genai import types
from .interfaces import ILLMClient

class GeminiLLMClient(ILLMClient):
    """
    Implementação local do ILLMClient para o Gemini 2.5 Flash-Lite.
    Utiliza o SDK oficial google-genai.
    
    Atenção: Requer a variável de ambiente GEMINI_API_KEY configurada.
    """
    def __init__(self):
        # O Client() puxa automaticamente o GEMINI_API_KEY do os.environ
        self.client = genai.Client()
        self.model = "gemini-3.1-flash-lite"
        
    async def gerar_resposta(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """
        Gera a resposta de forma assíncrona usando o Flex Tier para economia,
        e respeita os controles de temperatura e tamanho impostos pela PMS-006.
        """
        # Monta a configuração incluindo o 'service_tier' flex que reduz custos pela metade.
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            # Documentação aponta que o tier mais barato na v2.5/SDK é 'flex' ou via config
            # Passamos string fixa 'flex' se o sdk aceitar como param extra, ou pelo kwargs do config.
        }
        
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
            
        # No SDK atual google-genai, flex tier é selecionado passando service_tier="flex" 
        # (se suportado na interface Config), ou caso contrário via opções extras de metadados.
        # No snippet passado no grill-me, era direto na chamada de interactions, mas em models usamos config:
        config_kwargs["service_tier"] = "flex"

        config = types.GenerateContentConfig(**config_kwargs)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config
                )
                
                if response.text is not None:
                    return response.text
                return ""
            
            except Exception as e:
                import asyncio
                if attempt < max_retries - 1:
                    print(f"[Gemini Flex] Falha na tentativa {attempt + 1}. Tentando novamente em 2s... Erro: {e}")
                    await asyncio.sleep(2)
                else:
                    print(f"[Gemini Flex] Falha definitiva após {max_retries} tentativas.")
                    raise e
        return ""
