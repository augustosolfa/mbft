from fastapi import APIRouter, Depends, Header
from typing import Optional
from ..database import get_db, FilaRepository
from ..security import get_settings, Settings, TicketService

router = APIRouter(prefix="/ticket", tags=["Ticketizador"])

@router.post("/")
async def solicitar_ticket(
    priority_token: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
    db: FilaRepository = Depends(get_db)
):
    service = TicketService(settings, db)
    return await service.emitir(priority_token)
