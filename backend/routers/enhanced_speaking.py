"""
Enhanced TCF Speaking Module with conversation memory, follow-up questions,
realistic scoring, and audio storage support.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_optional_user
from database import get_db
from models import User, SpeakingSession, UserAudioResponse
from schemas import (
    EnhancedTcfConversationRequest,
    EnhancedTcfConversationResponse,
    EnhancedSpeakingEvaluationResponse,
    SpeakingSessionInitRequest,
    SpeakingSessionInitResponse,
    UserAudioBlobRequest,
    UserAudioBlobResponse,
)
from tcf_ai_service import generate_tcf_speaking_reply, evaluate_tcf_speaking_conversation

router = APIRouter(prefix="/tcf/speaking/enhanced", tags=["tcf", "speaking"])


@router.post("/session/init", response_model=SpeakingSessionInitResponse)
async def init_speaking_session(
    payload: SpeakingSessionInitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> SpeakingSessionInitResponse:
    """Initialize a new speaking session with topic maintenance."""
    import uuid
    from datetime import datetime

    session_id = str(uuid.uuid4())

    # Create session in DB
    db_session = SpeakingSession(
        user_id=user.id,
        session_id=session_id,
        task_type=payload.task_type,
        mode=payload.mode,
        exchange_count=0,
        conversation_context=json.dumps([]),
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # Generate initial question with TTS
    try:
        response = generate_tcf_speaking_reply(
            message="",
            history=[],
            task_type=payload.task_type,
            mode=payload.mode,
            hints=False,
            session_id=session_id,
            session_topic=None,
        )

        return SpeakingSessionInitResponse(
            session_id=session_id,
            topic=response.get("session_topic", "General Discussion"),
            initial_question=response.get("reply", ""),
            initial_audio_url=response.get("audio_url"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation", response_model=EnhancedTcfConversationResponse)
async def enhanced_conversation(
    payload: EnhancedTcfConversationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> EnhancedTcfConversationResponse:
    """Handle conversation turn with memory-aware follow-ups. Max 5 exchanges."""
    db_session = db.query(SpeakingSession).filter(
        SpeakingSession.session_id == payload.session_id,
        SpeakingSession.user_id == user.id,
    ).first()

    if not db_session:
        raise HTTPException(status_code=404, detail="Speaking session not found")

    if db_session.exchange_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 exchanges reached")

    # Update conversation context
    context = json.loads(db_session.conversation_context or "[]")
    context.append({
        "role": "user",
        "text": payload.message,
        "audio_url": payload.user_audio_url,
        "timestamp": payload.exchange_count,
    })

    # Get examiner's next question
    try:
        response = generate_tcf_speaking_reply(
            message=payload.message,
            history=[],
            task_type=payload.task_type,
            mode=payload.mode,
            hints=False,
            session_id=payload.session_id,
            session_topic=db_session.topic,
        )

        examiner_reply = response.get("reply", "")
        audio_url = response.get("audio_url")
        topic = response.get("session_topic", db_session.topic)

        context.append({
            "role": "examiner",
            "text": examiner_reply,
            "audio_url": audio_url,
            "timestamp": payload.exchange_count,
        })

        db_session.conversation_context = json.dumps(context)
        db_session.exchange_count = payload.exchange_count + 1
        db_session.topic = topic
        db.commit()

        return EnhancedTcfConversationResponse(
            session_id=payload.session_id,
            reply=examiner_reply,
            audio_url=audio_url,
            topic=topic,
            exchange_count=payload.exchange_count + 1,
            is_complete=db_session.exchange_count >= 5,
            follow_up_category="follow_up",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audio/store", response_model=UserAudioBlobResponse)
async def store_user_audio(
    payload: UserAudioBlobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> UserAudioBlobResponse:
    """Store user's audio blob from recording during speaking test."""
    try:
        import base64
        from pathlib import Path

        audio_bytes = base64.b64decode(payload.audio_data)

        audio_dir = Path(__file__).parent.parent / "data" / "user_audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        audio_filename = f"session_{payload.session_id}_exchange_{payload.exchange_number}.wav"
        audio_path = audio_dir / audio_filename
        audio_url = f"/audio/user_audio/{audio_filename}"

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        db_session = db.query(SpeakingSession).filter(
            SpeakingSession.session_id == payload.session_id,
            SpeakingSession.user_id == user.id,
        ).first()

        if db_session:
            audio_response = UserAudioResponse(
                user_id=user.id,
                speaking_session_id=db_session.id,
                exchange_number=payload.exchange_number,
                audio_url=audio_url,
                transcript=payload.transcript,
            )
            db.add(audio_response)
            db.commit()

        return UserAudioBlobResponse(
            audio_url=audio_url,
            stored_successfully=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store audio: {str(e)}")


@router.post("/evaluate", response_model=EnhancedSpeakingEvaluationResponse)
async def enhanced_evaluate(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_optional_user),
) -> EnhancedSpeakingEvaluationResponse:
    """Evaluate speaking with realistic scoring based on multiple criteria."""
    try:
        session_id = payload.get("session_id")
        history = payload.get("history", [])
        task_type = payload.get("task_type", "basic_interaction")

        db_session = db.query(SpeakingSession).filter(
            SpeakingSession.session_id == session_id,
            SpeakingSession.user_id == user.id,
        ).first()

        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")

        evaluation = evaluate_tcf_speaking_conversation(
            history=history,
            task_type=task_type,
        )

        transcription_accuracy = min(10, float(evaluation.get("grammar", 5)) * 0.8)
        grammar_score = float(evaluation.get("grammar", 5))
        relevance_score = float(evaluation.get("interaction", 5))
        length_score = min(10, len([m for m in history if m.get("role") == "user"]) * 2)

        overall_score = (
            transcription_accuracy * 0.2
            + grammar_score * 0.3
            + relevance_score * 0.3
            + length_score * 0.2
        ) / 10

        db_session.overall_score = overall_score
        db_session.transcription_accuracy = transcription_accuracy
        db_session.grammar_score = grammar_score
        db_session.relevance_score = relevance_score
        db_session.length_score = length_score
        db_session.is_completed = True
        db.commit()

        return EnhancedSpeakingEvaluationResponse(
            transcription_accuracy=transcription_accuracy,
            grammar_score=grammar_score,
            relevance_score=relevance_score,
            length_score=length_score,
            overall_score=overall_score,
            feedback=evaluation.get("feedback", []),
            recommendations=[
                "Focus on clear pronunciation" if transcription_accuracy < 7 else "",
                "Improve grammar accuracy" if grammar_score < 7 else "",
                "Answer more completely" if length_score < 7 else "",
            ],
            should_improve=overall_score < 6,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
