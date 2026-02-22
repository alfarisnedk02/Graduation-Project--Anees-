#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from dotenv import load_dotenv
from risk import CriticalRiskDetector
# ---------------------------------------------------------------
# Welcome tooo Setup
# ---------------------------------------------------------------

logging.basicConfig(level=logging.WARNING) # Changed from INFO to WARNING
logger = logging.getLogger("integrated_chatbot")
logging.getLogger("httpx").setLevel(logging.WARNING) # Silence OpenAI API lo

load_dotenv()  # Load OPENAI_API_KEY etc.

# ---------------------------------------------------------------
# Core RAG Chatbot (Internal Logic)
# ---------------------------------------------------------------

class IntegratedRAGChatbot:
    def __init__(
        self,
        chroma_db_path: str = "./chroma_db_pdf",
        collection_name: str = "documents",
        embedding_model: str = "BAAI/bge-m3",
        openai_model: str = "gpt-4o-mini",
    ):
        self.chroma_db_path = chroma_db_path
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model
        self.openai_model = openai_model

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")

        self._init_chroma()
        self._init_embedder()
        self._init_openai(api_key)

    # ---------------- Chroma / Embedding / OpenAI ----------------

    def _init_chroma(self):
        self.client = chromadb.PersistentClient(path=self.chroma_db_path)
        self.collection = self.client.get_collection(self.collection_name)
        logger.info(
            f"Connected to ChromaDB collection '{self.collection_name}' "
            f"at '{self.chroma_db_path}'"
        )

    def _init_embedder(self):
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self.embedder = SentenceTransformer(self.embedding_model_name)
        logger.info("Embedding model loaded.")

    def _init_openai(self, api_key: str):
        self.openai = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized.")

    # ---------------- Retrieval ----------------

    def retrieve(self, query: str, n_results: int = 15):
        """
        Retrieve most relevant chunks from DSM-5 + MBTI.
        Optionally bias query text (e.g., for MBTI or DSM focus).
        """
        # Always refresh collection reference
        self.collection = self.client.get_collection(self.collection_name)

        query_embedding = self.embedder.encode([query]).tolist()
        n_results = max(8, min(n_results, 40))

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        return results

    def build_context(self, results, min_sim: float = 0.03, max_chunks: int = 8) -> str:
        """Turn retrieval output into text context for GPT."""
        if (
            not results
            or not results.get("documents")
            or not results["documents"][0]
        ):
            return "No relevant content found in DSM-5 / MBTI documents."

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        scored = []
        for doc, meta, dist in zip(docs, metas, dists):
            sim = 1 - dist
            scored.append((sim, str(doc), meta))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)

        parts = []
        for sim, doc, meta in scored:
            if sim < min_sim:
                continue

            source = meta.get("source_file") or meta.get("document") or "Unknown"
            clean_doc = doc.strip().replace("\n\n", "\n")

            parts.append(
                f"[SOURCE: {source} | similarity={sim:.3f}]\n{clean_doc}"
            )
            if len(parts) >= max_chunks:
                break

        if not parts:
            return "No strong matches in DSM-5 / MBTI documents."

        return "\n\n---\n\n".join(parts)

    # ---------------- Question Generation (MBTI) ----------------

    def generate_mbti_question(self, history, personality_answers, index: int, skip_history=None, decline=False):
        """
        Use GPT to generate ONE MBTI-style, multiple-choice personality question.
        Output format (from GPT) must be JSON.
        skip_history: list of previously asked questions to avoid repetition
        decline: if True, generate a question from a new category
        """
        
        # (Keep the context retrieval code the same as before...)
        mbti_query = (
            "Myers-Briggs personality types preferences extraversion introversion "
            "sensing intuition thinking feeling judging perceiving"
        )
        results = self.retrieve(mbti_query, n_results=12)
        context = self.build_context(results, min_sim=0.02, max_chunks=5)

        # --- UPDATED SYSTEM PROMPT ---
        system_prompt = (
            "You are creating a multiple-choice question to explore a teen's MBTI-style "
            "personality preferences. You MUST:\n"
            "- Use ONLY information consistent with MBTI theory.\n"
            "- Ask on everyday situations (university, friends, hobbies, energy, decisions).\n"
            "- Avoid clinical or mental health language in this part.\n"
            "- USE VARIETY OF QUESTION STYLES. \n"
            "- Make the question simple and culture-appropriate.\n"
            "- Ensure the questions categories are diverse. \n"
            "- Provide exactly 3-4 options.\n"
            "- IMPORTANT: The 'options' list MUST include the letter AND the text description.\n"
            "  CORRECT JSON Example: { \"question\": \"...\", \"options\": [\"A) I like to plan ahead\", \"B) I go with the flow\"] }\n"
            "  INCORRECT JSON Example: { \"options\": [\"A\", \"B\"] }\n"
            "- Each question explores at least one MBTI dimension.\n"
        )
        
        # Add instructions for decline (new category) vs skip (same category)
        if skip_history:
            system_prompt += "\n- Do NOT repeat or create similar questions to these:\n"
            for q in skip_history:
                system_prompt += f"  - '{q}'\n"
        
        if decline:
            system_prompt += "\n- Generate a question from a DIFFERENT CATEGORY than previously asked questions.\n"
            system_prompt += "- Focus on a NEW MBTI dimension or situation type.\n"

        # Short summary of previous answers
        prev_summary = ""
        if personality_answers:
            prev_summary = "Previous personality answers:\n"
            for i, entry in enumerate(personality_answers, start=1):
                prev_summary += f"{i}. Q: {entry['question']} | A: {entry['answer']}\n"

        user_prompt = {
            "context": context,
            "instructions": (
                "Generate ONE new MBTI-style multiple-choice question in JSON form. "
                "Ensure options contain full text descriptions. "
                "Return ONLY valid JSON."
            ),
            "index": index,
            "previous_answers_summary": prev_summary,
        }

        try:
            resp = self.openai.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt)},
                ],
                temperature=0.4,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content.strip()
            
            # Clean up potential markdown formatting (```json ... ```)
            if raw.startswith("```json"):
                raw = raw.replace("```json", "").replace("```", "")
            
            parsed = json.loads(raw)
            question = parsed.get("question", "").strip()
            options = parsed.get("options", [])

            # Fallback if options are empty
            if not question or not options:
                raise ValueError("Missing question/options in JSON.")

            return question, options

        except Exception as e:
            logger.error(f"Error generating MBTI question, using fallback. Details: {e}")
            question = "When you have free time, what sounds more fun?"
            options = [
                "A) Hanging out with a group of friends or going to a busy place",
                "B) Doing something calm alone, like reading, gaming, or drawing",
                "C) Spending time with one or two close friends",
                "D) Trying something new or spontaneous"
            ]
            return question, options

    # ---------------- Question Generation (Mental Health) ----------------

    def generate_mental_health_question(self, history, mental_answers, index: int, skip_history=None, decline=False):
        """
        Use GPT to generate ONE open-ended mental health question,
        grounded in DSM-5 style themes, but non-diagnostic and safe.
        skip_history: list of previously asked questions to avoid repetition
        decline: if True, generate a question from a new category
        """

        dsm_query = (
            "DSM-5 mood anxiety stress sleep concentration personality functioning "
            "coping social relationships university functioning"
        )
        results = self.retrieve(dsm_query, n_results=15)
        context = self.build_context(results, min_sim=0.02, max_chunks=6)

        system_prompt = (
            "You are creating an open-ended mental health check-in question for a university student.\n"
            "Use DSM-5 concepts to inspire the topic (mood, anxiety, sleep, energy, "
            "concentration, relationships, stress, coping) BUT:\n"
            "- Do NOT diagnose.\n"
            "- Do NOT use clinical labels like 'major depressive disorder' or 'generalized anxiety disorder'.\n"
            "- Do NOT ask about self-harm methods, suicide plans, or anything graphic.\n"
            "- You MAY gently ask about safety, like 'Do you feel safe right now?', but keep it simple.\n"
            "- Ask in a kind, non-judgmental, conversational way.\n"
            "- Make the next question adaptive: use what the user has already shared.\n"
            "- Return ONLY the question text, no JSON, no explanations."
        )
        
        # Add instructions to avoid repeating questions
        if skip_history:
            system_prompt += f"\nCRITICAL: Do not repeat or ask something similar to these questions:\n"
            for q in skip_history:
                system_prompt += f"- '{q}'\n"
        
        if decline:
            system_prompt += "\n- Generate a question from a DIFFERENT CATEGORY than previously asked questions.\n"
            system_prompt += "- Focus on a NEW mental health theme (e.g., if previous was about mood, now ask about sleep or relationships).\n"

        prev_summary = ""
        if mental_answers:
            prev_summary = "Previous mental health answers (short summary):\n"
            for i, entry in enumerate(mental_answers[-5:], start=1):
                prev_summary += f"{i}. Q: {entry['question']} | A: {entry['answer'][:80]}...\n"

        user_prompt = (
            f"DOCUMENT CONTEXT (DSM-5 themes):\n{context}\n\n"
            f"CONVERSATION SUMMARY:\n{prev_summary}\n\n"
            f"Now generate a single open-ended question number {index} that helps understand "
            f"how this student is feeling, coping, or functioning day-to-day."
        )

        try:
            resp = self.openai.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=200,
            )
            question = resp.choices[0].message.content.strip()
            return question
        except Exception as e:
            logger.error(f"Error generating mental health question, using fallback. Details: {e}")
            return "How have you been feeling emotionally most days recently?"

    # ---------------- Final Integrated Summary ----------------

    def generate_final_report(self, personality_answers, mental_answers, history):
        """
        Create an integrated summary using MBTI + DSM-style context and the user's answers.
        This is educational, not diagnostic.
        """

        # Build a compact summary of the answers
        perso_summary = "Personality-related answers:\n"
        for i, p in enumerate(personality_answers, start=1):
            perso_summary += f"{i}. Q: {p['question']} | A: {p['answer']}\n"

        mental_summary = "Mental health-related answers:\n"
        for i, m in enumerate(mental_answers, start=1):
            shortened = m["answer"].replace("\n", " ")
            if len(shortened) > 160:
                shortened = shortened[:160] + "..."
            mental_summary += f"{i}. Q: {m['question']} | A: {shortened}\n"

        overall_summary = perso_summary + "\n" + mental_summary

        # Retrieve broad DSM + MBTI context
        integration_query = (
            "Myers-Briggs personality types traits coping styles and DSM-5 concepts "
            "about mood, anxiety, stress, personality functioning and resilience."
        )
        results = self.retrieve(integration_query, n_results=20)
        context = self.build_context(results, min_sim=0.02, max_chunks=10)

        system_prompt = (
            "You are an mental health assistant for university student's.\n"
            "You have:\n"
            "- A summary of the university student's answers to personality-style questions (MBTI-like).\n"
            "- A summary of the university student's answers to mental-health-style questions.\n"
            "- Reference excerpts from DSM-5 and MBTI documents.\n\n"
            "Your job:\n"
            "- Provide a clear, kind, and NON-DIAGNOSTIC overview of patterns.\n"
            "- Explain how certain personality traits (introversion/extraversion, sensing/intuition, "
            "thinking/feeling, judging/perceiving) *might* relate to how they experience stress, mood, "
            "relationships, and university life.\n"
            "- Use DSM-5 concepts to describe general themes (like anxiety, low mood, difficulty concentrating) "
            "without naming specific disorders but giving indications.\n"
            "- Suggest healthy coping strategies (sleep, routines, physical activity, hobbies, social support, "
            "emotion regulation, CBT-style thinking, asking for help, etc.).\n"
            "- Encourage them to talk with a trusted professional (a licensed mental health professional)"
            " if they are struggling.\n"
            "- If their answers sound like they might be in significant distress, gently recommend reaching out "
            "for professional help. Do NOT give any self-harm instructions or anything unsafe.\n"
            "- Keep the tone supportive, non-judgmental, and easy to understand.\n"
            "Format the response using clear section headers:\n"
            "- Important Notice"
            "- Symptom Indicator Overview"
            "- DSM-Informed Themes"
            "- Personality Profile (MBTI)"
            "- Personality & Coping Link"
            "- What This Means"
            "- What Helps"
            "- When to Seek Support"
            "- Final Reassurance"

            "Do NOT write a long essay."
            "Use short paragraphs and bullet points."
        )

        user_prompt = (
            f"DOCUMENT CONTEXT (DSM-5 + MBTI):\n{context}\n\n"
            f"USER ANSWER SUMMARY:\n{overall_summary}\n\n"
            "Now write an integrated explanation that:\n"
            "- Talks about their possible personality patterns and their personality type.\n"
            "- Connects that to how they might experience stress or emotional ups and downs.\n"
            "- Offers concrete, realistic suggestions they can try.\n"
            "- Reminds them that this is not a diagnosis and that professionals can help."
        )

        try:
            resp = self.openai.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=900,
            )
            final_report = resp.choices[0].message.content
            
            # INTERNAL: Automatically save to JSON (users don't see this)
            self._save_report_internal(personality_answers, mental_answers, final_report)
            
            return final_report
            
        except Exception as e:
            logger.error(f"Error generating final report: {e}")
            return (
                "I had trouble generating the final summary. "
                "But from what you've shared, it could really help to talk to a trusted adult "
                "or a mental health professional about how you're feeling."
            )

    # ---------------- INTERNAL JSON SAVING (Not accessible to users) ----------------
    
    def _save_report_internal(self, personality_answers, mental_answers, final_report, filename="final_summary.json"):
        """
        INTERNAL METHOD: Save session data to JSON file in the 'conclusion' folder.
        Called automatically from generate_final_report().
        Users cannot access this method.
        """
        try:
            # Create the 'conclusion' folder if it doesn't exist
            conclusion_folder = "conclusion"
            if not os.path.exists(conclusion_folder):
                os.makedirs(conclusion_folder)
                logger.info(f"Created folder: {conclusion_folder}")
            
            # Create the full file path
            file_path = os.path.join(conclusion_folder, filename)
            
            # Generate timestamp for unique filename (optional)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            # If you want unique filenames, uncomment the line below:
            # file_path = os.path.join(conclusion_folder, f"final_summary_{timestamp}.json")
            
            session_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "personality_answers": personality_answers,
                "mental_health_answers": mental_answers,
                "final_report": final_report
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Session data saved internally to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving session data: {e}")
            return False


# ---------------------------------------------------------------
# CONVERSATION MANAGER (API Gateway for Android) - UPDATED TO MATCH CLI
# ---------------------------------------------------------------
class ConversationManager:
    """
    API Gateway for Android users.
    Manages user sessions and provides a clean interface.
    Users only interact with questions and see final summary.
    Updated to match exact CLI output format.
    """
    def __init__(self):
        # Initialize the core chatbot engine
        self.bot = IntegratedRAGChatbot()
        # Session storage: { "user_id": { session_data } }
        self.sessions = {}
        # Risk detector for safety
        self.detector = CriticalRiskDetector()

    def _get_session(self, user_id):
        """Get or create a session for a user."""
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                "step": "intro",
                "personality_answers": [],
                "mental_answers": [],
                "history": [],
                "personality_skip_history": [],
                "mental_skip_history": [],
                "current_question_data": None,
                "last_mental_question": "",
                "risk_session_id": self.detector.new_session_id(),
                "show_header": True,  # Flag to show Anees header
                "phase": None  # "personality" or "mental_health"
            }
        return self.sessions[user_id]

    def _check_safety(self, text, session_id):
        """Check if user input is safe."""
        result = self.detector.decide(text, rag_client=None, session_id=session_id)
        return result.action not in ("pause_and_refer", "stop_and_refer")

    def _get_empathy_response(self, feeling_text):
        """Generate empathetic response like CLI does."""
        try:
            bot = IntegratedRAGChatbot()  # Create temporary bot for this
            empathetic_resp = bot.openai.chat.completions.create(
                model=bot.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Anees, a gentle, supportive assistant. "
                            "Your job is to respond empathetically to how the user feels. "
                            "Do NOT give diagnoses, medical instructions, or self-harm guidance. "
                            "Just validate, reassure, and be warm."
                            "You are mental health professional assistant."
                            "Your answers should not include any questions."
                            "Your answers should be in simple English."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"The user says they feel: {feeling_text}"
                    }
                ],
                temperature=0.6,
                max_tokens=150
            )
            return empathetic_resp.choices[0].message.content.strip()
        except Exception:
            return "I'm really glad you shared that with me. Thank you for being open."

    def process_user_message(self, user_id, message):
        """
        Main API endpoint for Android.
        Processes user message and returns bot response.
        
        Returns: dict with {
            "response": str,           # Bot's response text (EXACTLY like CLI)
            "options": list,           # For personality questions (empty for mental health)
            "question_number": int,    # Current question number (1-10)
            "phase": str,              # "personality" or "mental_health"
            "is_finished": bool,       # True if assessment complete
            "final_report": str,       # Final summary (only if is_finished=True)
            "error": str               # Error message if any
        }
        """
        session = self._get_session(user_id)
        
        # Check safety first
        if not self._check_safety(message, session["risk_session_id"]):
            result = self.detector.decide(message, rag_client=None, session_id=session["risk_session_id"])
            referral_msg = self.detector.format_referral_message(result)
            del self.sessions[user_id]  # Clean up session
            return {
                "response": referral_msg,
                "options": [],
                "question_number": 0,
                "phase": "error",
                "is_finished": True,
                "final_report": None,
                "error": "safety_concern"
            }
        
        response_data = {
            "response": "",
            "options": [],
            "question_number": 0,
            "phase": None,
            "is_finished": False,
            "final_report": None,
            "error": None
        }
        
        step = session["step"]
        msg = message.strip()
        
        # 1. INTRO STEP - Initial greeting (matches CLI)
        if step == "intro":
            session["show_header"] = True
            response_data["response"] = (
                "\n Hello, I'm Anees. Think of me as your supportive guide and companion "
                "on the journey to understanding yourself better and finding inner balance.\n\n"
                "To help us get settled, how are you feeling right now?"
            )
            session["step"] = "feeling_check"
            response_data["phase"] = "intro"
        
        # 2. FEELING CHECK - Ask how they feel (matches CLI)
        elif step == "feeling_check":
            feeling = msg
            
            # Validate feeling input like CLI does
            if feeling.replace('.','',1).isdigit():
                response_data["response"] = "I'd like to hear about your feelings in words, rather than numbers. How are you doing?"
                return response_data
            elif len(feeling) < 2:
                response_data["response"] = "Feel free to share a bit more with me."
                return response_data
            
            # Generate empathetic response like CLI does
            anees_reply = self._get_empathy_response(feeling)
            response_data["response"] = f"{anees_reply}\n\n" + \
                "I'd like to guide you through a gentle discovery session. " + \
                "This will help us understand exactly where you are emotionally and how I can best support you.\n\n" + \
                "Are you ready to begin? (yes/no)"
            session["step"] = "ready_check"
            response_data["phase"] = "intro"
        
        # 3. READY CHECK - Ask if ready to begin
        elif step == "ready_check":
            ready = msg.lower()
            if ready not in ["yes", "y"]:
                response_data["response"] = "That's completely okay. Whenever you're ready, you can come back and we'll begin. 💛"
                response_data["is_finished"] = True
                if user_id in self.sessions:
                    del self.sessions[user_id]
                return response_data
            
            response_data["response"] = "Great. We'll begin gently, starting with some personality reflections.\n"
            session["step"] = "waiting_for_start"
            session["phase"] = "personality"
            response_data["phase"] = "personality"
        
        # 4. WAITING FOR START - Start personality questions
        elif step == "waiting_for_start":
            if msg.lower() in ["ready", "yes", "start"] or step == "waiting_for_start":
                # Start with first personality question (Question 1/5)
                question, options = self.bot.generate_mbti_question(
                    session["history"],
                    session["personality_answers"],
                    1,
                    skip_history=session["personality_skip_history"],
                    decline=False
                )
                
                # Format options exactly like CLI
                formatted_options = []
                alphabet = ["A", "B", "C", "D"]
                for idx, opt in enumerate(options):
                    current_letter = alphabet[idx]
                    if not opt.strip().upper().startswith(current_letter):
                        opt = f"{current_letter}) {opt}"
                    formatted_options.append(opt)
                
                session["current_question_data"] = {
                    "question": question,
                    "options": formatted_options,
                    "type": "personality",
                    "number": 1
                }
                
                # Build response exactly like CLI
                response_text = f"[Personality Question 1/5]\n {question}\n"
                for opt in formatted_options:
                    response_text += f"  {opt}\n"
                response_text += f"\nYour choice ({'/'.join(alphabet[:len(formatted_options)])}), 'skip', 'decline', or 'exit': "
                
                response_data["response"] = response_text
                response_data["options"] = formatted_options
                response_data["question_number"] = 1
                response_data["phase"] = "personality"
                session["step"] = "personality_1"
            else:
                response_data["response"] = "Whenever you're ready, just type 'ready' to begin."
        
        # 5. PERSONALITY QUESTIONS (1-5) - Match CLI format exactly
        elif step.startswith("personality_"):
            q_num = int(step.split("_")[1])
            response_data["question_number"] = q_num
            response_data["phase"] = "personality"
            
            # Get valid letters for display
            alphabet = ["A", "B", "C", "D"]
            valid_letters = alphabet[:len(session["current_question_data"]["options"])]
            
            # Handle skip/decline - with CLI-style messages
            if msg.upper() == "SKIP":
                # Add to skip history
                session["personality_skip_history"].append(session["current_question_data"]["question"])
                
                # Generate new question from same category
                question, options = self.bot.generate_mbti_question(
                    session["history"],
                    session["personality_answers"],
                    q_num,
                    skip_history=session["personality_skip_history"],
                    decline=False
                )
                
                # Format options
                formatted_options = []
                for idx, opt in enumerate(options):
                    current_letter = alphabet[idx]
                    if not opt.strip().upper().startswith(current_letter):
                        opt = f"{current_letter}) {opt}"
                    formatted_options.append(opt)
                
                session["current_question_data"] = {
                    "question": question,
                    "options": formatted_options,
                    "type": "personality",
                    "number": q_num
                }
                
                # Build CLI-style response
                response_text = "Okay, let's try another question on a similar topic.\n"
                response_text += f"{question}\n"
                for opt in formatted_options:
                    response_text += f"  {opt}\n"
                response_text += f"\nYour choice ({'/'.join(alphabet[:len(formatted_options)])}), 'skip', 'decline', or 'exit': "
                
                response_data["response"] = response_text
                response_data["options"] = formatted_options
                
            elif msg.upper() == "DECLINE":
                # Add to skip history
                session["personality_skip_history"].append(session["current_question_data"]["question"])
                
                # Generate new question from NEW category
                question, options = self.bot.generate_mbti_question(
                    session["history"],
                    session["personality_answers"],
                    q_num,
                    skip_history=session["personality_skip_history"],
                    decline=True
                )
                
                # Format options
                formatted_options = []
                for idx, opt in enumerate(options):
                    current_letter = alphabet[idx]
                    if not opt.strip().upper().startswith(current_letter):
                        opt = f"{current_letter}) {opt}"
                    formatted_options.append(opt)
                
                session["current_question_data"] = {
                    "question": question,
                    "options": formatted_options,
                    "type": "personality",
                    "number": q_num
                }
                
                # Build CLI-style response
                response_text = "I understand. Let's move to a different type of question.\n"
                response_text += f"{question}\n"
                for opt in formatted_options:
                    response_text += f"  {opt}\n"
                response_text += f"\nYour choice ({'/'.join(alphabet[:len(formatted_options)])}), 'skip', 'decline', or 'exit': "
                
                response_data["response"] = response_text
                response_data["options"] = formatted_options
                
            elif msg.upper() == "EXIT":
                response_data["response"] = "\nNo worries. We can pause here. Take care 💛"
                response_data["is_finished"] = True
                if user_id in self.sessions:
                    del self.sessions[user_id]
                return response_data
                
            else:
                # Handle answer (A, B, C, D)
                if msg and msg[0].upper() in ["A", "B", "C", "D"]:
                    # Save answer
                    selected_option = next(
                        (opt for opt in session["current_question_data"]["options"] 
                         if opt.startswith(msg[0].upper())),
                        msg
                    )
                    
                    session["personality_answers"].append({
                        "question": session["current_question_data"]["question"],
                        "answer": selected_option
                    })
                    session["history"].append({
                        "role": "user",
                        "content": f"For the personality question '{session['current_question_data']['question']}', my answer is: {selected_option}."
                    })
                    
                    # Move to next question or switch to mental health
                    next_q = q_num + 1
                    if next_q <= 5:
                        question, options = self.bot.generate_mbti_question(
                            session["history"],
                            session["personality_answers"],
                            next_q,
                            skip_history=session["personality_skip_history"],
                            decline=False
                        )
                        
                        # Format options
                        formatted_options = []
                        for idx, opt in enumerate(options):
                            current_letter = alphabet[idx]
                            if not opt.strip().upper().startswith(current_letter):
                                opt = f"{current_letter}) {opt}"
                            formatted_options.append(opt)
                        
                        session["current_question_data"] = {
                            "question": question,
                            "options": formatted_options,
                            "type": "personality",
                            "number": next_q
                        }
                        
                        # Build CLI-style response
                        response_text = f" [Personality Question {next_q}/5]\n{question}\n"
                        for opt in formatted_options:
                            response_text += f"  {opt}\n"
                        response_text += f"\nYour choice ({'/'.join(alphabet[:len(formatted_options)])}), 'skip', 'decline', or 'exit': "
                        
                        response_data["response"] = response_text
                        response_data["options"] = formatted_options
                        response_data["question_number"] = next_q
                        session["step"] = f"personality_{next_q}"
                    else:
                        # Switch to mental health - exactly like CLI
                        response_data["response"] = "\n Thank you. Now we'll shift gently into understanding your emotional world a bit better.\n"
                        session["step"] = "mental_1"
                        session["phase"] = "mental_health"
                        response_data["phase"] = "mental_health"
                else:
                    # Invalid input - show error like CLI
                    if session["current_question_data"]:
                        response_text = f"Please choose one of: {', '.join(valid_letters)}, or type 'skip' or 'decline'\n\n"
                        response_text += f"[Personality Question {q_num}/5]\n{session['current_question_data']['question']}\n"
                        for opt in session["current_question_data"]["options"]:
                            response_text += f"  {opt}\n"
                        response_text += f"\nYour choice ({'/'.join(valid_letters)}), 'skip', 'decline', or 'exit': "
                        
                        response_data["response"] = response_text
                        response_data["options"] = session["current_question_data"]["options"]
                    else:
                        response_data["response"] = f"Please choose one of: {', '.join(valid_letters)}, or type 'skip' or 'decline'"
        
        # 6. MENTAL HEALTH QUESTIONS (6-10) - Match CLI format exactly
        elif step.startswith("mental_"):
            q_num = int(step.split("_")[1])
            mental_q_num = q_num  # 1-5 for mental health phase
            response_data["question_number"] = q_num + 5  # 6-10 overall
            response_data["phase"] = "mental_health"
            
            # Handle skip/decline/exit - with CLI-style messages
            if msg.lower() == "skip":
                if session["last_mental_question"]:
                    session["mental_skip_history"].append(session["last_mental_question"])
                
                # Generate new question from same category
                question = self.bot.generate_mental_health_question(
                    session["history"],
                    session["mental_answers"],
                    q_num + 5,  # Offset
                    skip_history=session["mental_skip_history"],
                    decline=False
                )
                
                session["last_mental_question"] = question
                
                # Build CLI-style response
                response_text = "Okay, let's try another question on a similar topic.\n"
                response_text += f"[Mental Health Question {mental_q_num}/5]\n {question}\n"
                response_text += "(or type 'skip', 'decline', 'exit'): "
                
                response_data["response"] = response_text
                
            elif msg.lower() == "decline":
                if session["last_mental_question"]:
                    session["mental_skip_history"].append(session["last_mental_question"])
                
                # Generate new question from NEW category
                question = self.bot.generate_mental_health_question(
                    session["history"],
                    session["mental_answers"],
                    q_num + 5,  # Offset
                    skip_history=session["mental_skip_history"],
                    decline=True
                )
                
                session["last_mental_question"] = question
                
                # Build CLI-style response
                response_text = " I understand. Let's move to a different type of question.\n"
                response_text += f"[Mental Health Question {mental_q_num}/5]\n{question}\n"
                response_text += "\n(or type 'skip', 'decline', 'exit'): "
                
                response_data["response"] = response_text
                
            elif msg.lower() == "exit":
                response_data["response"] = "\nThank you for sharing what you could. Take care of yourself 💛"
                response_data["is_finished"] = True
                if user_id in self.sessions:
                    del self.sessions[user_id]
                return response_data
                
            else:
                # Save answer and move to next
                if q_num == 1:
                    # First mental health question - generate it
                    question = self.bot.generate_mental_health_question(
                        session["history"],
                        session["mental_answers"],
                        6,  # Question 6 overall
                        skip_history=session["mental_skip_history"],
                        decline=False
                    )
                    session["last_mental_question"] = question
                    
                    # Save answer to previous question (if any)
                    if msg:
                        session["mental_answers"].append({
                            "question": session["last_mental_question"],
                            "answer": msg
                        })
                        session["history"].append({
                            "role": "user",
                            "content": f"Answer: {msg}"
                        })
                    
                    # Move to next question
                    next_q = q_num + 1
                    if next_q <= 5:
                        question = self.bot.generate_mental_health_question(
                            session["history"],
                            session["mental_answers"],
                            next_q + 5,  # Offset
                            skip_history=session["mental_skip_history"],
                            decline=False
                        )
                        
                        session["last_mental_question"] = question
                        
                        # Build CLI-style response
                        response_text = f"\nAnees [Mental Health Question {next_q}/5]\n{question}\n"
                        response_text += "\nYou (or type 'skip', 'decline', 'exit'): "
                        
                        response_data["response"] = response_text
                        response_data["question_number"] = next_q + 5
                        session["step"] = f"mental_{next_q}"
                    else:
                        # Generate final report
                        response_data["response"] = "\n Thank you for completing all 10 questions. " + \
                                                  "Let me take a moment to reflect on everything you shared.\n"
                        session["step"] = "generating_report"
                        # Don't return yet - go to generating report
                else:
                    # Not first question - save answer and generate next
                    if session["last_mental_question"] and msg:
                        session["mental_answers"].append({
                            "question": session["last_mental_question"],
                            "answer": msg
                        })
                        session["history"].append({
                            "role": "user",
                            "content": f"Answer: {msg}"
                        })
                    
                    next_q = q_num + 1
                    if next_q <= 5:
                        question = self.bot.generate_mental_health_question(
                            session["history"],
                            session["mental_answers"],
                            next_q + 5,  # Offset
                            skip_history=session["mental_skip_history"],
                            decline=False
                        )
                        
                        session["last_mental_question"] = question
                        
                        # Build CLI-style response
                        response_text = f"\nAnees [Mental Health Question {next_q}/5]\n {question}\n"
                        response_text += "\nYou (or type 'skip', 'decline', 'exit'): "
                        
                        response_data["response"] = response_text
                        response_data["question_number"] = next_q + 5
                        session["step"] = f"mental_{next_q}"
                    else:
                        # Generate final report
                        response_data["response"] = "\nThank you for completing all 10 questions. " + \
                                                  "Let me take a moment to reflect on everything you shared.\n"
                        session["step"] = "generating_report"
                        # Don't return yet - go to generating report
        
        # 7. GENERATING FINAL REPORT - Match CLI format exactly
        elif step == "generating_report":
            # Generate final report
            final_report = self.bot.generate_final_report(
                session["personality_answers"],
                session["mental_answers"],
                session["history"]
            )
            
            # Build CLI-style response
            response_text = "Anees – Your Integrated Summary :\n\n"
            response_text += final_report
            response_text += "\n\n Remember, this is not a diagnosis. If you're having a tough time, "
            response_text += "speaking with a trusted mental health professional can be incredibly helpful. 💛"
            
            response_data["response"] = response_text
            response_data["final_report"] = final_report
            response_data["is_finished"] = True
            response_data["phase"] = "completed"
            
            # Clean up session
            if user_id in self.sessions:
                del self.sessions[user_id]
        
        return response_data


# ---------------------------------------------------------------
# ORIGINAL CLI RUNNER (Kept for testing on PC)
# ---------------------------------------------------------------
def run_assessment():
    """Original CLI function for PC testing - kept unchanged"""
    bot = IntegratedRAGChatbot()

    # ---------------- CRITICAL RISK GATE (HARD STOP) ----------------
    detector = CriticalRiskDetector() 
    session_id = detector.new_session_id() 
    def risk_gate(text: str) -> bool:
         """ 
         Returns True if safe to continue. 
         Returns False if we must STOP and show referrals.
           """ 
         result = detector.decide(text, rag_client=None, session_id=session_id) 
         if result.action in ("pause_and_refer", "stop_and_refer"): 
            print("\n" + "="*60) 
            print(detector.format_referral_message(result)) 
            print("="*60 + "\n") 
            return False 
         
         return True

    print("\nAnees:Hello, I'm Anees. Think of me as your supportive guide and companion on the journey to understanding yourself better and finding inner balance.")

    # Ask how they feel
    while True:
        feeling = input("To help us get settled, how are you feeling right now?\nYou: ").strip()

    # If the empathy step happened for any reason, still enforce safety
        if not risk_gate(feeling): 
            import sys 
            sys.exit(0)

        if feeling.replace('.','',1).isdigit():
            print("Anees: I'd like to hear about your feelings in words, rather than numbers. How are you doing?")
        elif len(feeling) < 2:
            print("Anees: Feel free to share a bit more with me.")
        else:
        # CRITICAL: Detect risk from the very first message 
            if not risk_gate(feeling):
                import sys 
                sys.exit(0) 
        break

    # Generate an empathetic response using GPT
    try:
        # Re-instantiating bot here isn't strictly necessary since we have 'bot' above, 
        # but we use the existing instance to call openai.
        empathetic_resp = bot.openai.chat.completions.create(
            model=bot.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Anees, a gentle, supportive assistant. "
                        "Your job is to respond empathetically to how the user feels. "
                        "Do NOT give diagnoses, medical instructions, or self-harm guidance. "
                        "Just validate, reassure, and be warm."
                        "You are mental health professional assistant."
                        "Your answers should mot include any questions."
                        "Your answers should be in simple English."
                         )
                },
                {
                    "role": "user",
                    "content": f"The user says they feel: {feeling}"
                }
            ],
            temperature=0.6,
            max_tokens=150
        )
        Anees_reply = empathetic_resp.choices[0].message.content.strip()

    except Exception:
        Anees_reply = "I'm really glad you shared that with me. Thank you for being open."

    print(f"\nAnees: {Anees_reply}\n")

    # Continue introduction
    print("Anees: I'd like to guide you through a gentle discovery session. "
          "This will help us understand exactly where you are emotionally and how I can best support you.")

    # Ask if they are ready
    ready = input("\nAnees: Are you ready to begin? (yes/no)\nYou: ").strip().lower()
    if ready not in ["yes", "y"]:
        print("\nAnees:That's completely okay. Whenever you're ready, you can come back and we'll begin. 💛")
        return

    print("\nAnees:Great. We'll begin gently, starting with some personality reflections.\n")

    # ------------------------------------------------------------
    # Continue with the original assessment logic
    # ------------------------------------------------------------

    personality_answers = []
    mental_answers = []
    history = []
    
    # Track skipped/declined questions to avoid repetition
    personality_skip_history = []
    mental_skip_history = []

# ---------------- Personality Phase (1–5) ----------------
    i = 1
    while i <= 5:
        print(f"\nAnees [Personality Question {i}/5]")
        
        # Generate question with skip history
        question, options = bot.generate_mbti_question(
            history, 
            personality_answers, 
            i, 
            skip_history=personality_skip_history,
            decline=False  # Only set to True when user chooses "Decline"
        )

        print("Anees:", question)
        
        # Determine valid letters based on the options provided
        valid_letters = []
        clean_options = []
        
        alphabet = ["A", "B", "C", "D"]
        
        for idx, opt in enumerate(options):
            # Safe logic: If option starts with "A)", keep it. If not, add "A) " to it.
            current_letter = alphabet[idx]
            if not opt.strip().upper().startswith(current_letter):
                opt = f"{current_letter}) {opt}"
            
            print(f"  {opt}")
            clean_options.append(opt)
            valid_letters.append(current_letter)

        selected_full_text = ""

        while True:
            user_input = input(f"Your choice ({'/'.join(valid_letters)}), 'skip', 'decline', or 'exit': ").strip().upper()
            
            if user_input == "EXIT":
                print("Anees:No worries. We can pause here. Take care 💛")
                return
            
            elif user_input == "SKIP":
                print("Anees: Okay, let's try another question on a similar topic.")
                # Add to skip history to avoid repetition
                personality_skip_history.append(question)
                # Generate new question from same category
                question, options = bot.generate_mbti_question(
                    history, 
                    personality_answers, 
                    i, 
                    skip_history=personality_skip_history,
                    decline=False  # Same category
                )
                print("Anees:", question)
                # Re-display options
                valid_letters = []
                clean_options = []
                for idx, opt in enumerate(options):
                    current_letter = alphabet[idx]
                    if not opt.strip().upper().startswith(current_letter):
                        opt = f"{current_letter}) {opt}"
                    print(f"  {opt}")
                    clean_options.append(opt)
                    valid_letters.append(current_letter)
                continue  # Stay in the same question loop
            
            elif user_input == "DECLINE":
                print("Anees: I understand. Let's move to a different type of question.")
                # Add to skip history
                personality_skip_history.append(question)
                # Generate new question from NEW category
                question, options = bot.generate_mbti_question(
                    history, 
                    personality_answers, 
                    i, 
                    skip_history=personality_skip_history,
                    decline=True  # New category
                )
                print("Anees:", question)
                # Re-display options
                valid_letters = []
                clean_options = []
                for idx, opt in enumerate(options):
                    current_letter = alphabet[idx]
                    if not opt.strip().upper().startswith(current_letter):
                        opt = f"{current_letter}) {opt}"
                    print(f"  {opt}")
                    clean_options.append(opt)
                    valid_letters.append(current_letter)
                continue  # Stay in the same question loop

            # Check if input is a valid letter
            if user_input in valid_letters:
                # Find the full text corresponding to this letter
                for opt in clean_options:
                    if opt.startswith(user_input):
                        selected_full_text = opt
                        break
                break # Exit the while loop
            
            print(f"Anees: Please choose one of: {', '.join(valid_letters)}, or type 'skip' or 'decline'")

        # Store answer with full text
        personality_answers.append({
            "question": question,
            "options": clean_options,
            "answer": selected_full_text
        })

        # Store conversation memory
        history.append({
            "role": "user",
            "content": f"For the personality question '{question}', my answer is: {selected_full_text}."
        })
        
        # Add to skip history to avoid repeating this question later
        personality_skip_history.append(question)
        
        i += 1  # Move to next question

    # ---------------- Mental Health Phase (6–10) ----------------
    print("\nAnees: Thank you. Now we'll shift gently into understanding your emotional world a bit better.\n")

    i = 6
    while i <= 10:
        print(f"\nAnees [Mental Health Question {i-5}/5]")
        
        # Generate question with skip history
        question = bot.generate_mental_health_question(
            history, 
            mental_answers, 
            i, 
            skip_history=mental_skip_history,
            decline=False  # Only set to True when user chooses "Decline"
        )

        print("\nAnees:", question)
        
        while True:
            user_answer = input("You (or type 'skip', 'decline', 'exit'): ").strip()
            
            if user_answer.lower() == "exit":
                print("\nAnees:Thank you for sharing what you could. Take care of yourself 💛")
                return
            
            elif user_answer.lower() == "skip":
                print("Anees: Okay, let's try another question on a similar topic.")
                # Add to skip history
                mental_skip_history.append(question)
                # Generate new question from same category
                question = bot.generate_mental_health_question(
                    history, 
                    mental_answers, 
                    i, 
                    skip_history=mental_skip_history,
                    decline=False  # Same category
                )
                print("Anees:", question)
                continue  # Stay in the same question loop
            
            elif user_answer.lower() == "decline":
                print("Anees: I understand. Let's move to a different type of question.")
                # Add to skip history
                mental_skip_history.append(question)
                # Generate new question from NEW category
                question = bot.generate_mental_health_question(
                    history, 
                    mental_answers, 
                    i, 
                    skip_history=mental_skip_history,
                    decline=True  # New category
                )
                print("Anees:", question)
                continue  # Stay in the same question loop
            
            # CRITICAL: Detect risk during the session too 
            if not risk_gate(user_answer):
                return

            break  # Valid answer given

        # Store answer
        mental_answers.append({
            "question": question,
            "answer": user_answer
        })

        history.append({
            "role": "user",
            "content": f"Answer: {user_answer}"
        })
        
        # Add to skip history to avoid repeating this question later
        mental_skip_history.append(question)
        
        i += 1  # Move to next question

    # ---------------- Final Integrated Summary ----------------
    print("\nAnees: Thank you for completing all 10 questions. "
          "Let me take a moment to reflect on everything you shared.\n")

    final_report = bot.generate_final_report(personality_answers, mental_answers, history)

    print("Anees – Your Integrated Summary :\n")
    print(final_report)
    
    print("\nAnees: Remember, this is not a diagnosis. If you're having a tough time, "
          "speaking with a trusted mental health professional can be incredibly helpful. 💛")


if __name__ == "__main__":
    # Note: Android app would use ConversationManager, not run_assessment()
    run_assessment()