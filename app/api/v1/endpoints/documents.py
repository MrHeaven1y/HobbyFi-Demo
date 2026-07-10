from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.ingestion_service import IngestionService
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger("app.api.documents")

@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Uploads a document for asynchronous ingestion into the RAG vector database.
    Returns 202 Accepted immediately.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # We pass the file to the background task.
    # Note: For very large files or high traffic, you would push this to a 
    # Celery/Redis queue instead of FastAPI's native BackgroundTasks.
    
    # We must read the file into memory or save it before passing to background task
    # because UploadFile stream closes after the response is sent.
    # The service handles saving the temp file.
    
    async def run_ingestion():
        # Create a new DB session for the background thread
        # (FastAPI's get_db yields a session scoped to the request, which closes after response)
        from app.database.session import SessionLocal
        bg_db = SessionLocal()
        try:
            service = IngestionService(bg_db)
            await service.process_upload(file)
        finally:
            bg_db.close()

    background_tasks.add_task(run_ingestion)
    
    return {
        "status": "accepted",
        "message": f"File '{file.filename}' is processing.",
        "filename": file.filename
    }