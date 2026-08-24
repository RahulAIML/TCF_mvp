from fastapi import APIRouter, Depends, HTTPException

from auth import get_optional_user
from models import User
from schemas import TtsGenerateRequest, TtsGenerateResponse, TtsVoice
from tts_service import generate_tts_audio, list_active_voices

router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/voices", response_model=list[TtsVoice])
async def get_voices(
    _user: User = Depends(get_optional_user),
) -> list[TtsVoice]:
    return list_active_voices()


@router.post("/generate", response_model=TtsGenerateResponse)
async def post_generate_tts(
    payload: TtsGenerateRequest,
    _user: User = Depends(get_optional_user),
) -> TtsGenerateResponse:
    try:
        audio_url = generate_tts_audio(payload.text, payload.voice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TtsGenerateResponse(
        audio_url=audio_url,
        voice_id=payload.voice_id,
        character_count=len(payload.text.strip()),
    )
