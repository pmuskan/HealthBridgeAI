import os
import uvicorn
import uuid
from fastapi import FastAPI, HTTPException, Header, Depends, status, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

import database as db
from ragbackend import query_healthbridge, PROJECT_ID, CORPUS_NAME, get_user_analytics

db.init_db()

app = FastAPI(
    title="HealthBridge AI API",
    description="Clinical decision support API with RAG backend and authentication",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format. Must be Bearer <token>"
        )
    
    token = authorization.split(" ")[1]
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token"
        )
    
    # Add token to the user object for convenience (e.g. logout)
    user["token"] = token
    return user

class UserSignup(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    role: Optional[str] = "ASHA Worker"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ChatCreate(BaseModel):
    language: Optional[str] = "English"
    title: Optional[str] = "New Conversation"

class MessageSend(BaseModel):
    query: str
    language: Optional[str] = "English"

@app.post("/api/auth/signup")
async def signup(user_data: UserSignup):
    try:
        user = db.create_user(
            name=user_data.name,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role
        )
        token = db.create_session(user["id"])
        return {"success": True, "token": token, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    user = db.verify_user(credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    token = db.create_session(user["id"])
    return {"success": True, "token": token, "user": user}

@app.post("/api/auth/logout")
async def logout(current_user = Depends(get_current_user)):
    db.delete_session(current_user["token"])
    return {"success": True, "detail": "Logged out successfully"}

@app.get("/api/auth/me")
async def get_me(current_user = Depends(get_current_user)):
    # Remove session token from returned profile data
    profile = {k: v for k, v in current_user.items() if k != "token"}
    return {"success": True, "user": profile}

@app.get("/api/chats")
async def get_chats(current_user = Depends(get_current_user)):
    chats = db.get_user_chats(current_user["id"])
    return {"success": True, "chats": chats}

@app.post("/api/chats")
async def create_new_chat(chat_data: ChatCreate, current_user = Depends(get_current_user)):
    chat = db.create_chat(
        user_id=current_user["id"],
        title=chat_data.title,
        language=chat_data.language
    )
    return {"success": True, "chat": chat}

@app.get("/api/chats/{chat_id}")
async def get_messages(chat_id: str, current_user = Depends(get_current_user)):
    chats = db.get_user_chats(current_user["id"])
    user_chat_ids = [c["id"] for c in chats]
    if chat_id not in user_chat_ids:
        raise HTTPException(status_code=403, detail="Access denied to this chat history")
        
    messages = db.get_chat_messages(chat_id)
    return {"success": True, "messages": messages}

@app.post("/api/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    query: Optional[str] = Form(None),
    language: Optional[str] = Form("English"),
    image: Optional[UploadFile] = File(None),
    current_user = Depends(get_current_user)
):
    chats = db.get_user_chats(current_user["id"])
    user_chat_ids = [c["id"] for c in chats]
    if chat_id not in user_chat_ids:
        raise HTTPException(status_code=403, detail="Access denied to this chat session")
    
    query_text = (query or "").strip()
    if not query_text and not image:
        raise HTTPException(status_code=400, detail="Query text or image is required")
        
    lang = language or "English"
    
    image_path = None
    image_bytes = None
    image_mime_type = None
    if image:
        ext = os.path.splitext(image.filename)[1]
        unique_filename = f"{uuid.uuid4()}{ext}"
        image_path = f"uploads/{unique_filename}"
        
        image_bytes = await image.read()
        image_mime_type = image.content_type
        
        with open(image_path, "wb") as f:
            f.write(image_bytes)
            
    history_messages = db.get_chat_messages(chat_id)
    
    # Extract only user queries for RAG context, matching app.py logic
    user_history = [m["content"] for m in history_messages if m["role"] == "user"]
    
    result = query_healthbridge(
        user_query=query_text,
        language=lang,
        chat_history=user_history,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        user_id=str(current_user["id"])
    )
    
    user_message_content = query_text if query_text else "Uploaded a medical document/prescription."
    db.add_message(
        chat_id=chat_id,
        role="user",
        content=user_message_content,
        query_type="user_query",
        language=lang,
        image_path=image_path
    )
    
    db.add_message(
        chat_id=chat_id,
        role="assistant",
        content=result["response"],
        query_type=result["query_type"],
        language=result["language"]
    )
    
    # Auto-update title if it's the first message
    if not history_messages:
        title_source = query_text if query_text else "Medical Document Analysis"
        new_title = title_source[:30] + ("..." if len(title_source) > 30 else "")
        db.update_chat_title(chat_id, new_title)
        
    return {
        "success": result["success"],
        "response": result["response"],
        "query_type": result["query_type"],
        "language": result["language"],
        "error": result["error"]
    }

@app.delete("/api/chats/{chat_id}")
async def delete_chat_thread(chat_id: str, current_user = Depends(get_current_user)):
    chats = db.get_user_chats(current_user["id"])
    user_chat_ids = [c["id"] for c in chats]
    if chat_id not in user_chat_ids:
        raise HTTPException(status_code=403, detail="Access denied to this chat session")
        
    db.delete_chat(current_user["id"], chat_id)
    return {"success": True, "detail": "Chat session deleted successfully"}

@app.get("/api/analytics/me")
async def get_my_analytics(current_user = Depends(get_current_user)):
    try:
        stats = get_user_analytics(user_id=str(current_user["id"]))
        return {"success": True, "analytics": stats}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user analytics: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "project_id": PROJECT_ID,
        "corpus_name": CORPUS_NAME
    }

if os.path.exists("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")
    
    @app.get("/{fallback_path:path}")
    async def serve_react_app(fallback_path: str):
        # Let's ensure we don't intercept API paths
        if fallback_path.startswith("api/") or fallback_path.startswith("docs") or fallback_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        return FileResponse("frontend/dist/index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
