import os
import uvicorn
import uuid
import logging
import base64
import math
import httpx
import re
from fastapi import FastAPI, HTTPException, Header, Depends, status, Form, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import database as db
from ragbackend import query_healthbridge, PROJECT_ID, CORPUS_NAME, get_user_analytics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("healthbridge")

db.init_db()

# Tight CORS allow-list loaded from environment or defaults
cors_allowed_origins_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
if cors_allowed_origins_raw:
    origins = [o.strip() for o in cors_allowed_origins_raw.split(",") if o.strip()]
else:
    origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="HealthBridge AI API",
    description="Clinical decision support API with RAG backend and authentication",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
@limiter.limit("5/minute")
async def signup(request: Request, user_data: UserSignup):
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
        logger.warning(f"Signup validation error for {user_data.email}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected signup error for {user_data.email}")
        raise HTTPException(status_code=500, detail="Registration failed: An unexpected error occurred. Please try again later.")

@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, credentials: UserLogin):
    try:
        user = db.verify_user(credentials.email, credentials.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        token = db.create_session(user["id"])
        return {"success": True, "token": token, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected login error for {credentials.email}")
        raise HTTPException(
            status_code=500,
            detail="Login failed: An unexpected error occurred. Please try again later."
        )

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
@limiter.limit("15/minute")
async def send_message(
    request: Request,
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
    
    image_bytes = None
    image_mime_type = None
    if image:
        # Enforce allowed content types (image/jpeg, image/png, etc.)
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"]
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {image.content_type}. Only JPEG, PNG, GIF, WEBP, and BMP images are allowed."
            )
        
        # Read bytes
        image_bytes = await image.read()
        image_mime_type = image.content_type
        
        # Enforce max file size of 5MB
        max_size = 5 * 1024 * 1024
        if len(image_bytes) > max_size:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds the 5MB limit."
            )
            
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
    
    # If image was provided, base64-encode it for this single API response
    image_data_url = None
    if image_bytes and image_mime_type:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:{image_mime_type};base64,{encoded}"
        
    # Store only a marker string indicating an image was uploaded, not the image itself
    image_db_path = "uploaded" if image else None
    
    user_message_content = query_text if query_text else "Uploaded a medical document/prescription."
    db.add_message(
        chat_id=chat_id,
        role="user",
        content=user_message_content,
        query_type="user_query",
        language=lang,
        image_path=image_db_path
    )
    
    cleaned_response = tighten_response_spacing(result["response"])
    db.add_message(
        chat_id=chat_id,
        role="assistant",
        content=cleaned_response,
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
        "response": cleaned_response,
        "query_type": result["query_type"],
        "language": result["language"],
        "error": result["error"],
        "image_data_url": image_data_url
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
@limiter.limit("10/minute")
async def get_my_analytics(request: Request, current_user = Depends(get_current_user)):
    try:
        stats = get_user_analytics(user_id=str(current_user["id"]))
        return {"success": True, "analytics": stats}
    except Exception as e:
        logger.exception(f"Failed to fetch user analytics for user {current_user['id']}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch user analytics: An unexpected error occurred."
        )

def tighten_response_spacing(text: str) -> str:
    # Collapse any blank line(s) between consecutive bullet points into a single newline
    text = re.sub(r'(\n[•\-\*]\s.+?)\n\s*\n(?=[•\-\*]\s)', r'\1\n', text)
    # Collapse 3+ consecutive newlines anywhere down to 2 (paragraph/section breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

def calculate_haversine(lat1, lon1, lat2, lon2):
    """Calculates the distance in kilometers between two points using the Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.get("/api/geocode")
@limiter.limit("20/minute")
async def geocode_address(
    request: Request,
    address: str,
    current_user = Depends(get_current_user)
):
    """Geocodes an address or town name to lat/lng coordinates using Google Geocoding API."""
    if not GOOGLE_PLACES_API_KEY:
        logger.warning("GOOGLE_PLACES_API_KEY environment variable is not set for geocoding.")
        return {"error": "Google Places API Key is not configured on the server"}
        
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": GOOGLE_PLACES_API_KEY
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error(f"Geocoding API returned status code {resp.status_code}")
                return {"error": f"Geocoding API returned status code {resp.status_code}"}
            
            data = resp.json()
            if data.get("status") != "OK":
                logger.error(f"Geocoding failed with status: {data.get('status')}")
                return {"error": f"Geocoding failed with status: {data.get('status')}"}
                
            location = data["results"][0]["geometry"]["location"]
            return {"lat": location["lat"], "lng": location["lng"]}
    except Exception as e:
        logger.exception(f"Error in geocoding address {address}: {e}")
        return {"error": "An unexpected error occurred during geocoding"}

@app.get("/api/nearby-hospitals")
@limiter.limit("20/minute")
async def get_nearby_hospitals(
    request: Request,
    lat: float,
    lng: float,
    current_user = Depends(get_current_user)
):
    """Fetches up to 5 nearby hospitals sorted by distance from the user using Places API (New)."""
    if not GOOGLE_PLACES_API_KEY:
        logger.warning("GOOGLE_PLACES_API_KEY environment variable is not set.")
        return {"error": "Google Places API Key is not configured on the server", "results": []}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.types,places.location,places.nationalPhoneNumber"
    }
    body = {
        "includedTypes": ["hospital"],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": 10000.0
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.error(f"Places API (New) returned status code {resp.status_code}: {resp.text}")
                return {"error": f"Places API returned status code {resp.status_code}", "results": []}
            
            data = resp.json()
            places = data.get("places", [])
            if not places:
                return {"results": []}
            
            hospitals = []
            for p in places:
                loc = p.get("location", {})
                h_lat = loc.get("latitude")
                h_lng = loc.get("longitude")
                if h_lat is None or h_lng is None:
                    continue
                dist = calculate_haversine(lat, lng, h_lat, h_lng)
                
                # Classify type based on heuristics
                display_name_obj = p.get("displayName", {})
                name = display_name_obj.get("text", "")
                name_lower = name.lower()
                
                is_govt = (
                    "govt" in name_lower or
                    "government" in name_lower or
                    "phc" in name_lower or
                    "chc" in name_lower or
                    "district hospital" in name_lower
                )
                hospital_type = "Government" if is_govt else "Private"
                
                phone = p.get("nationalPhoneNumber")
                place_id = p.get("id")
                maps_url = f"https://www.google.com/maps/dir/?api=1&destination={h_lat},{h_lng}&destination_place_id={place_id}"
                
                hospitals.append({
                    "name": name,
                    "place_id": place_id,
                    "lat": h_lat,
                    "lng": h_lng,
                    "distance_km": round(dist, 2),
                    "hospital_type": hospital_type,
                    "phone": phone,
                    "maps_url": maps_url
                })
            
            # Sort by distance and take top 5
            hospitals.sort(key=lambda h: h["distance_km"])
            return {"results": hospitals[:5]}
            
    except Exception as e:
        logger.exception(f"Error fetching nearby hospitals: {e}")
        return {"error": "An unexpected error occurred while fetching hospitals", "results": []}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "project_id": PROJECT_ID,
        "corpus_name": CORPUS_NAME
    }

PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <rect width="100%" height="100%" fill="#F3F4F6" rx="12"/>
  <path d="M70 40h60a10 10 0 0 1 10 10v100a10 10 0 0 1-10 10H70a10 10 0 0 1-10-10V50a10 10 0 0 1 10-10z" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="2"/>
  <path d="M85 30h30a5 5 0 0 1 5 5v10H80V35a5 5 0 0 1 5-5z" fill="#3B82F6"/>
  <line x1="80" y1="70" x2="120" y2="70" stroke="#9CA3AF" stroke-width="3" stroke-linecap="round"/>
  <line x1="80" y1="90" x2="120" y2="90" stroke="#9CA3AF" stroke-width="3" stroke-linecap="round"/>
  <line x1="80" y1="110" x2="110" y2="110" stroke="#9CA3AF" stroke-width="3" stroke-linecap="round"/>
  <text x="100" y="145" font-family="sans-serif" font-size="10" fill="#9CA3AF" text-anchor="middle" font-weight="bold">Medical Image</text>
  <text x="100" y="158" font-family="sans-serif" font-size="8" fill="#9CA3AF" text-anchor="middle">(In-Memory Only)</text>
</svg>"""

@app.get("/placeholder_{filename:path}")
async def serve_placeholder_image(filename: str):
    return Response(content=PLACEHOLDER_SVG, media_type="image/svg+xml")

@app.get("/uploads/{filename:path}")
async def serve_uploads_placeholder(filename: str):
    return Response(content=PLACEHOLDER_SVG, media_type="image/svg+xml")

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
    env = os.getenv("ENV", "production").lower()
    reload = (env == "development")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=reload)
