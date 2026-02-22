# # api_chatbot.py
# from fastapi import FastAPI, HTTPException, Header, Depends
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# import uuid
# import logging
# from typing import Optional, Dict
# from datetime import datetime
# import requests  # Add this import
# import json      # Add this import

# # Import the ConversationManager from your existing code
# from chatbotR import ConversationManager  

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("chatbot_api")

# # Initialize FastAPI app
# app = FastAPI(
#     title="Anees Mental Health Chatbot API",
#     description="API for Android app to interact with Anees mental health assessment chatbot",
#     version="1.0.0",
#     docs_url="/docs",  # Swagger UI at http://localhost:8000/docs
#     redoc_url="/redoc"  # ReDoc at http://localhost:8000/redoc
# )

# # Add CORS middleware for Android app
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # In production, restrict to your Android app domain
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Initialize ConversationManager
# conversation_manager = ConversationManager()

# # PDF Generation Server URL
# PDF_SERVER_URL = "http://localhost:5000"  # Change if different port

# # Request/Response Models
# class ChatRequest(BaseModel):
#     message: str
#     user_id: Optional[str] = None  # If not provided, will generate new

# class ChatResponse(BaseModel):
#     response: str
#     options: list[str] = []
#     question_number: int = 0
#     phase: str = "intro"  # "intro", "personality", "mental_health", "completed", "error"
#     is_finished: bool = False
#     final_report: Optional[str] = None
#     pdf_data: Optional[Dict] = None  # Add PDF generation data
#     user_id: str
#     timestamp: str
#     error: Optional[str] = None

# class SessionInfo(BaseModel):
#     user_id: str
#     created_at: str
#     current_step: str
#     current_phase: str
#     questions_answered: int

# class PDFGenerationRequest(BaseModel):
#     user_id: str
#     final_report: str
#     personality_answers: list
#     mental_answers: list

# # In-memory user sessions (for demo - use Redis/DB in production)
# user_sessions: Dict[str, Dict] = {}

# # Helper functions
# def get_or_create_user_id(user_id: Optional[str] = None) -> str:
#     """Get existing user_id or create new one"""
#     if user_id and user_id in user_sessions:
#         return user_id
    
#     new_id = str(uuid.uuid4())
#     user_sessions[new_id] = {
#         "created_at": datetime.now().isoformat(),
#         "last_activity": datetime.now().isoformat(),
#         "current_phase": "intro",
#         "personality_answers": [],
#         "mental_answers": [],
#         "final_report": None
#     }
#     return new_id

# def generate_pdf_data(user_id: str, final_report: str, personality_answers: list, mental_answers: list) -> Optional[Dict]:
#     """
#     Generate PDF using the PDF server
#     Returns: dict with pdf_url, qr_image, html_content or None if failed
#     """
#     try:
#         # Prepare the data to save to conclusion.txt
#         conclusion_text = format_report_for_pdf(final_report, personality_answers, mental_answers)
        
#         # Save to conclusion.txt in the conclusion folder
#         conclusion_folder = "conclusion"
#         os.makedirs(conclusion_folder, exist_ok=True)
        
#         conclusion_file = os.path.join(conclusion_folder, "conclusion.txt")
#         with open(conclusion_file, 'w', encoding='utf-8') as f:
#             f.write(conclusion_text)
        
#         logger.info(f"Saved conclusion text to {conclusion_file}")
        
#         # Call PDF server to generate PDF
#         pdf_server_url = f"{PDF_SERVER_URL}/api/generate"
#         response = requests.get(pdf_server_url)  # or POST depending on your server
        
#         if response.status_code == 200:
#             pdf_data = response.json()
#             logger.info(f"PDF generated successfully for user {user_id}")
#             return pdf_data
#         else:
#             logger.error(f"PDF generation failed: {response.status_code} - {response.text}")
#             return None
            
#     except Exception as e:
#         logger.error(f"Error generating PDF: {e}")
#         return None

# def format_report_for_pdf(final_report: str, personality_answers: list, mental_answers: list) -> str:
#     """
#     Format the final report for PDF generation
#     """
#     # Create a structured report
#     report_lines = []
    
#     # Add timestamp
#     report_lines.append(f"Assessment Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
#     report_lines.append("=" * 50)
#     report_lines.append("")
    
#     # Add personality assessment section
#     report_lines.append("PERSONALITY ASSESSMENT (MBTI Style)")
#     report_lines.append("-" * 30)
#     for i, answer in enumerate(personality_answers, 1):
#         report_lines.append(f"Q{i}: {answer.get('question', 'N/A')}")
#         report_lines.append(f"Answer: {answer.get('answer', 'N/A')}")
#         report_lines.append("")
    
#     # Add mental health assessment section
#     report_lines.append("MENTAL HEALTH CHECK-IN")
#     report_lines.append("-" * 30)
#     for i, answer in enumerate(mental_answers, 1):
#         report_lines.append(f"Q{i}: {answer.get('question', 'N/A')}")
#         # Truncate long answers for PDF
#         answer_text = answer.get('answer', 'N/A')
#         if len(answer_text) > 200:
#             answer_text = answer_text[:197] + "..."
#         report_lines.append(f"Answer: {answer_text}")
#         report_lines.append("")
    
#     # Add final report summary
#     report_lines.append("INTEGRATED SUMMARY")
#     report_lines.append("-" * 30)
#     report_lines.append(final_report)
    
#     return "\n".join(report_lines)

# # API Endpoints
# @app.get("/")
# async def root():
#     """Root endpoint - API status"""
#     return {
#         "status": "online",
#         "service": "Anees Mental Health Chatbot API",
#         "pdf_server": PDF_SERVER_URL,
#         "version": "1.0.0",
#         "endpoints": {
#             "POST /chat": "Send a message to the chatbot",
#             "GET /sessions": "Get all active sessions (admin)",
#             "DELETE /sessions/{user_id}": "Delete a session",
#             "GET /health": "Health check",
#             "POST /generate-pdf": "Generate PDF report"
#         }
#     }

# @app.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(request: ChatRequest):
#     """
#     Main chat endpoint for Android app
    
#     - Send user message
#     - Get chatbot response
#     - Supports skip/decline commands
#     - Returns exact CLI format for Android display
#     """
#     try:
#         # Get or create user ID
#         user_id = get_or_create_user_id(request.user_id)
        
#         # Update session activity
#         user_sessions[user_id]["last_activity"] = datetime.now().isoformat()
        
#         # Process message through ConversationManager
#         result = conversation_manager.process_user_message(user_id, request.message)
        
#         # If this is the final report, store it in session
#         if result.get("final_report"):
#             user_sessions[user_id]["final_report"] = result["final_report"]
        
#         # Update current phase in session
#         if "phase" in result:
#             user_sessions[user_id]["current_phase"] = result["phase"]
        
#         # Store answers if available in ConversationManager session
#         try:
#             if hasattr(conversation_manager, 'sessions') and user_id in conversation_manager.sessions:
#                 session_data = conversation_manager.sessions[user_id]
#                 user_sessions[user_id]["personality_answers"] = session_data.get("personality_answers", [])
#                 user_sessions[user_id]["mental_answers"] = session_data.get("mental_answers", [])
#         except:
#             pass
        
#         # Prepare response
#         response_data = {
#             "user_id": user_id,
#             "response": result.get("response", ""),
#             "options": result.get("options", []),
#             "question_number": result.get("question_number", 0),
#             "phase": result.get("phase", "intro"),
#             "is_finished": result.get("is_finished", False),
#             "final_report": result.get("final_report"),
#             "pdf_data": None,  # Will be populated if needed
#             "error": result.get("error"),
#             "timestamp": datetime.now().isoformat()
#         }
        
#         # If assessment is completed, generate PDF
#         if result.get("is_finished") and result.get("final_report"):
#             try:
#                 pdf_data = generate_pdf_data(
#                     user_id=user_id,
#                     final_report=result["final_report"],
#                     personality_answers=user_sessions[user_id].get("personality_answers", []),
#                     mental_answers=user_sessions[user_id].get("mental_answers", [])
#                 )
#                 if pdf_data:
#                     response_data["pdf_data"] = pdf_data
#             except Exception as pdf_error:
#                 logger.error(f"PDF generation error: {pdf_error}")
#                 # Don't fail the request if PDF generation fails
        
#         # Update session info
#         if result.get("is_finished"):
#             # Remove finished session
#             if user_id in user_sessions:
#                 user_sessions.pop(user_id, None)
#         else:
#             # Update current step in session
#             current_step = f"Question {result.get('question_number', 0)}"
#             if result.get("phase") == "intro":
#                 current_step = "Introduction"
#             elif result.get("phase") == "personality":
#                 current_step = f"Personality Q{result.get('question_number', 0)}"
#             elif result.get("phase") == "mental_health":
#                 current_step = f"Mental Health Q{result.get('question_number', 0)-5}"
            
#             user_sessions[user_id]["current_step"] = current_step
#             user_sessions[user_id]["current_phase"] = result.get("phase", "intro")
        
#         logger.info(f"Processed message for user {user_id} (phase: {result.get('phase', 'intro')})")
#         return ChatResponse(**response_data)
        
#     except Exception as e:
#         logger.error(f"Error processing chat: {e}")
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# @app.post("/generate-pdf")
# async def generate_pdf_endpoint(request: PDFGenerationRequest):
#     """
#     Generate PDF report for a completed assessment
#     Useful if PDF wasn't generated during the chat flow
#     """
#     try:
#         pdf_data = generate_pdf_data(
#             user_id=request.user_id,
#             final_report=request.final_report,
#             personality_answers=request.personality_answers,
#             mental_answers=request.mental_answers
#         )
        
#         if pdf_data:
#             return {
#                 "success": True,
#                 "message": "PDF generated successfully",
#                 "data": pdf_data
#             }
#         else:
#             return {
#                 "success": False,
#                 "message": "Failed to generate PDF"
#             }
            
#     except Exception as e:
#         logger.error(f"PDF generation error: {e}")
#         raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# @app.get("/sessions")
# async def get_sessions(admin_key: Optional[str] = Header(None)):
#     """
#     Get all active sessions (Admin only)
    
#     Requires admin_key header
#     """
#     # Simple admin check (use proper auth in production)
#     if admin_key != "YOUR_ADMIN_KEY_HERE":
#         raise HTTPException(status_code=403, detail="Unauthorized")
    
#     sessions_info = []
#     for user_id, session_data in user_sessions.items():
#         # Count questions answered
#         questions_answered = 0
#         try:
#             # Try to get actual count from ConversationManager
#             if hasattr(conversation_manager, 'sessions') and user_id in conversation_manager.sessions:
#                 session = conversation_manager.sessions[user_id]
#                 questions_answered = len(session.get("personality_answers", [])) + len(session.get("mental_answers", []))
#         except:
#             pass
        
#         sessions_info.append(SessionInfo(
#             user_id=user_id,
#             created_at=session_data.get("created_at", ""),
#             current_step=session_data.get("current_step", "unknown"),
#             current_phase=session_data.get("current_phase", "unknown"),
#             questions_answered=questions_answered
#         ))
    
#     return {
#         "total_sessions": len(sessions_info),
#         "sessions": sessions_info
#     }

# @app.delete("/sessions/{user_id}")
# async def delete_session(user_id: str, admin_key: Optional[str] = Header(None)):
#     """
#     Delete a specific session
    
#     Requires admin_key header
#     """
#     if admin_key != "YOUR_ADMIN_KEY_HERE":
#         raise HTTPException(status_code=403, detail="Unauthorized")
    
#     # Remove from our session storage
#     if user_id in user_sessions:
#         user_sessions.pop(user_id)
    
#     # Also remove from ConversationManager if it has its own storage
#     if hasattr(conversation_manager, 'sessions') and user_id in conversation_manager.sessions:
#         conversation_manager.sessions.pop(user_id, None)
    
#     return {"message": f"Session {user_id} deleted"}

# @app.get("/health")
# async def health_check():
#     """Health check endpoint"""
#     # Check PDF server health too
#     pdf_server_health = "unknown"
#     try:
#         response = requests.get(f"{PDF_SERVER_URL}/api/generate", timeout=5)
#         pdf_server_health = "healthy" if response.status_code == 200 else "unhealthy"
#     except:
#         pdf_server_health = "unreachable"
    
#     return {
#         "status": "healthy",
#         "timestamp": datetime.now().isoformat(),
#         "active_sessions": len(user_sessions),
#         "conversation_manager_ready": True,
#         "pdf_server": pdf_server_health
#     }

# @app.get("/start_new")
# async def start_new_session():
#     """
#     Start a new session and get initial greeting
#     Useful for Android app to get initial message without user input
#     """
#     try:
#         user_id = str(uuid.uuid4())
#         user_sessions[user_id] = {
#             "created_at": datetime.now().isoformat(),
#             "last_activity": datetime.now().isoformat(),
#             "current_phase": "intro"
#         }
        
#         # Get initial message by sending empty message
#         result = conversation_manager.process_user_message(user_id, "")
        
#         response = ChatResponse(
#             user_id=user_id,
#             response=result.get("response", ""),
#             options=result.get("options", []),
#             question_number=result.get("question_number", 0),
#             phase=result.get("phase", "intro"),
#             is_finished=result.get("is_finished", False),
#             final_report=result.get("final_report"),
#             pdf_data=result.get("pdf_data"),
#             error=result.get("error"),
#             timestamp=datetime.now().isoformat()
#         )
        
#         return response
        
#     except Exception as e:
#         logger.error(f"Error starting new session: {e}")
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(
#         app, 
#         host="0.0.0.0",  # Listen on all interfaces
#         port=8000,
#         log_level="info"
#     )






# without server2


# api_server.py
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import logging
from typing import Optional, Dict
from datetime import datetime

# Import the ConversationManager from your existing code
from chatbotR import ConversationManager  

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot_api")

# Initialize FastAPI app
app = FastAPI(
    title="Anees Mental Health Chatbot API",
    description="API for Android app to interact with Anees mental health assessment chatbot",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at http://localhost:8000/docs
    redoc_url="/redoc"  # ReDoc at http://localhost:8000/redoc
)

# Add CORS middleware for Android app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your Android app domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ConversationManager
conversation_manager = ConversationManager()

# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None  # If not provided, will generate new

class ChatResponse(BaseModel):
    response: str
    options: list[str] = []
    question_number: int = 0
    phase: str = "intro"  # New: "intro", "personality", "mental_health", "completed", "error"
    is_finished: bool = False
    final_report: Optional[str] = None
    user_id: str
    timestamp: str
    error: Optional[str] = None

class SessionInfo(BaseModel):
    user_id: str
    created_at: str
    current_step: str
    current_phase: str
    questions_answered: int

# In-memory user sessions (for demo - use Redis/DB in production)
user_sessions: Dict[str, Dict] = {}

# Helper functions
def get_or_create_user_id(user_id: Optional[str] = None) -> str:
    """Get existing user_id or create new one"""
    if user_id and user_id in user_sessions:
        return user_id
    
    new_id = str(uuid.uuid4())
    user_sessions[new_id] = {
        "created_at": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat(),
        "current_phase": "intro"
    }
    return new_id

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "status": "online",
        "service": "Anees Mental Health Chatbot API",
        "version": "1.0.0",
        "endpoints": {
            "POST /chat": "Send a message to the chatbot",
            "GET /sessions": "Get all active sessions (admin)",
            "DELETE /sessions/{user_id}": "Delete a session",
            "GET /health": "Health check"
        }
    }

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for Android app
    
    - Send user message
    - Get chatbot response
    - Supports skip/decline commands
    - Returns exact CLI format for Android display
    """
    try:
        # Get or create user ID
        user_id = get_or_create_user_id(request.user_id)
        
        # Update session activity
        user_sessions[user_id]["last_activity"] = datetime.now().isoformat()
        
        # Process message through ConversationManager
        result = conversation_manager.process_user_message(user_id, request.message)
        
        # Update current phase in session
        if "phase" in result:
            user_sessions[user_id]["current_phase"] = result["phase"]
        
        # Prepare response
        response = ChatResponse(
            user_id=user_id,
            response=result.get("response", ""),
            options=result.get("options", []),
            question_number=result.get("question_number", 0),
            phase=result.get("phase", "intro"),
            is_finished=result.get("is_finished", False),
            final_report=result.get("final_report"),
            error=result.get("error"),
            timestamp=datetime.now().isoformat()
        )
        
        # Update session info
        if result.get("is_finished"):
            # Remove finished session
            if user_id in user_sessions:
                user_sessions.pop(user_id, None)
        else:
            # Update current step in session
            current_step = f"Question {result.get('question_number', 0)}"
            if result.get("phase") == "intro":
                current_step = "Introduction"
            elif result.get("phase") == "personality":
                current_step = f"Personality Q{result.get('question_number', 0)}"
            elif result.get("phase") == "mental_health":
                current_step = f"Mental Health Q{result.get('question_number', 0)-5}"
            
            user_sessions[user_id]["current_step"] = current_step
            user_sessions[user_id]["current_phase"] = result.get("phase", "intro")
        
        logger.info(f"Processed message for user {user_id} (phase: {result.get('phase', 'intro')})")
        return response
        
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/sessions")
async def get_sessions(admin_key: Optional[str] = Header(None)):
    """
    Get all active sessions (Admin only)
    
    Requires admin_key header
    """
    # Simple admin check (use proper auth in production)
    if admin_key != "YOUR_ADMIN_KEY_HERE":
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    sessions_info = []
    for user_id, session_data in user_sessions.items():
        # Count questions answered
        questions_answered = 0
        try:
            # Try to get actual count from ConversationManager
            if hasattr(conversation_manager, 'sessions') and user_id in conversation_manager.sessions:
                session = conversation_manager.sessions[user_id]
                questions_answered = len(session.get("personality_answers", [])) + len(session.get("mental_answers", []))
        except:
            pass
        
        sessions_info.append(SessionInfo(
            user_id=user_id,
            created_at=session_data.get("created_at", ""),
            current_step=session_data.get("current_step", "unknown"),
            current_phase=session_data.get("current_phase", "unknown"),
            questions_answered=questions_answered
        ))
    
    return {
        "total_sessions": len(sessions_info),
        "sessions": sessions_info
    }

@app.delete("/sessions/{user_id}")
async def delete_session(user_id: str, admin_key: Optional[str] = Header(None)):
    """
    Delete a specific session
    
    Requires admin_key header
    """
    if admin_key != "YOUR_ADMIN_KEY_HERE":
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Remove from our session storage
    if user_id in user_sessions:
        user_sessions.pop(user_id)
    
    # Also remove from ConversationManager if it has its own storage
    if hasattr(conversation_manager, 'sessions') and user_id in conversation_manager.sessions:
        conversation_manager.sessions.pop(user_id, None)
    
    return {"message": f"Session {user_id} deleted"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(user_sessions),
        "conversation_manager_ready": True
    }

@app.get("/start_new")
async def start_new_session():
    """
    Start a new session and get initial greeting
    Useful for Android app to get initial message without user input
    """
    try:
        user_id = str(uuid.uuid4())
        user_sessions[user_id] = {
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "current_phase": "intro"
        }
        
        # Get initial message by sending empty message
        result = conversation_manager.process_user_message(user_id, "")
        
        response = ChatResponse(
            user_id=user_id,
            response=result.get("response", ""),
            options=result.get("options", []),
            question_number=result.get("question_number", 0),
            phase=result.get("phase", "intro"),
            is_finished=result.get("is_finished", False),
            final_report=result.get("final_report"),
            error=result.get("error"),
            timestamp=datetime.now().isoformat()
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error starting new session: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Listen on all interfaces
        port=8000,
        log_level="info"
    )