import asyncio
from dotenv import load_dotenv

# Carrega chaves do .env para o os.environ
load_dotenv()

from mbft_gerador.local_adapters import GeminiLLMClient
from mbft_gerador.orquestrador import OrquestradorGeracao

async def main():
    print("Iniciando teste do Gerador com Gemini Flash Lite 2.5 (Flex Tier)...\n")
    
    # 1. Instanciar o cliente e o orquestrador
    cliente_gemini = GeminiLLMClient()
    orquestrador = OrquestradorGeracao(llm_client=cliente_gemini)
    
    # Contexto Mockado
    contexto_mock = """
    Ficha de Enquadramento: 518-51
    Infração: Deixar o condutor de usar o cinto de segurança.
    Artigo: 167
    Gravidade: Grave
    Penalidade: Multa
    Medida Administrativa: Retenção do veículo até colocação do cinto pelo infrator.
    
    Regra Geral: A notificação de autuação deve ser expedida em até 30 dias do cometimento da infração.
    """
    
    print("--- TESTE 1: Pergunta COM resposta no contexto ---")
    pergunta_1 = "O que acontece se eu for pego dirigindo sem cinto de segurança? O carro é guinchado?"
    print(f"Pergunta: {pergunta_1}")
    resposta_1 = await orquestrador.gerar_resposta(pergunta_1, contexto_mock)
    print(f"Resposta do LLM:\n{resposta_1}\n")
    
    print("--- TESTE 2: Pergunta SEM resposta no contexto (Teste de Strict RAG) ---")
    pergunta_2 = "Posso recorrer da multa de cinto de segurança no JARI de outro estado?"
    print(f"Pergunta: {pergunta_2}")
    resposta_2 = await orquestrador.gerar_resposta(pergunta_2, contexto_mock)
    print(f"Resposta do LLM:\n{resposta_2}\n")

if __name__ == "__main__":
    asyncio.run(main())
