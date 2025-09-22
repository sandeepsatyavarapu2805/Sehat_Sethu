from flask import Flask, render_template, request, jsonify, session, send_from_directory
import google.generativeai as genai
import os, json, datetime
from google_trans_new import google_translator
from flask_cors import CORS
from werkzeug.utils import secure_filename
import traceback
import uuid
import re

# ---------------------------
# Configuration
# ---------------------------
# Use a single, consistent filename for user data
USER_DATA_FILE = "user_data.json"
# Directory to store uploaded files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
# File for chat logs
LOG_FILE = os.path.join(os.path.dirname(__file__), "chat_log.json")

# Create directories if they don't exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

# Initialize Flask
app = Flask(__name__)
# Needed for session
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
# Allow all origins for development
CORS(app)

# Google API Key
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("⚠️ GOOGLE_API_KEY is not set.")

# Initialize Generative AI
genai.configure(api_key=API_KEY)
# Using Gemini 1.5 Flash for chat and vision tasks
model = genai.GenerativeModel("gemini-1.5-flash")
vision_model = genai.GenerativeModel("gemini-1.5-flash")

# Initialize translator
translator = google_translator()

# Mock doctor directory and schedules
DOCTOR_DIRECTORY = [
    {"id": 1, "name": "Dr. Asha Varma", "specialty": "Cardiology", "location": "Hyderabad", "hospital": "Sunshine Hospitals", "phone": "+91 40 1111 2222"},
    {"id": 2, "name": "Dr. Rohan Iyer", "specialty": "Neurology", "location": "Hyderabad", "hospital": "Yashoda Hospitals", "phone": "+91 40 3333 4444"},
    {"id": 3, "name": "Dr. Kavya Rao", "specialty": "Orthopedics", "location": "Secunderabad", "hospital": "KIMS", "phone": "+91 40 5555 6666"},
    {"id": 4, "name": "Dr. Manoj Menon", "specialty": "Dermatology", "location": "Bengaluru", "hospital": "Apollo Hospitals", "phone": "+91 80 1111 2222"},
    {"id": 5, "name": "Dr. Neha Shah", "specialty": "Pediatrics", "location": "Mumbai", "hospital": "Fortis", "phone": "+91 22 1234 5678"},
    {"id": 6, "name": "Dr. Vikram Patel", "specialty": "Cardiology", "location": "Mumbai", "hospital": "Lilavati", "phone": "+91 22 9876 5432"},
    {"id": 7, "name": "Dr. Ananya Gupta", "specialty": "Neurology", "location": "Delhi", "hospital": "AIIMS", "phone": "+91 11 2461 0000"},
    {"id": 8, "name": "Dr. Suresh Reddy", "specialty": "Orthopedics", "location": "Hyderabad", "hospital": "Care Hospitals", "phone": "+91 40 7777 8888"},
]

DOCTOR_SCHEDULES = {
    1: ["09:00 AM", "11:00 AM", "02:00 PM"],
    2: ["10:00 AM", "01:00 PM", "04:00 PM"],
    3: ["08:30 AM", "12:30 PM"],
    4: ["09:15 AM", "03:15 PM"],
    5: ["11:00 AM", "05:00 PM"],
    6: ["09:45 AM", "01:45 PM"],
    7: ["10:30 AM", "02:30 PM"],
    8: ["08:00 AM", "01:00 PM"],
}

# ---------------------------
# Helpers
# ---------------------------
def load_user_data():
    """Load user data from JSON file."""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []}
    return {"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []}

def save_user_data(data):
    """Save user data to JSON file."""
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def update_log(edit_id: str, user_input: str, bot_text: str):
    """Update or append chat log entries."""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                chat_history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            chat_history = []
    else:
        chat_history = []

    found = False
    for entry in chat_history:
        if entry.get("id") == edit_id:
            entry["user"] = user_input
            entry["bot"] = bot_text
            entry["timestamp"] = datetime.datetime.now().isoformat()
            found = True
            break

    if not found:
        chat_history.append({
            "id": edit_id,
            "user": user_input,
            "bot": bot_text,
            "timestamp": datetime.datetime.now().isoformat()
        })

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)

def save_message(user_input, bot_text):
    """Append a new message to the chat log."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        history = []

    history.append({
        "id": str(uuid.uuid4()),  # Use UUID for a unique ID
        "user": user_input,
        "bot": bot_text,
        "timestamp": datetime.datetime.now().isoformat()
    })

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def create_system_instruction(user_data):
    """Generate personalized system instruction for AI."""
    profile_text = ""
    if user_data.get('profile'):
        profile = user_data['profile']
        profile_details = [
            f"Name - {profile.get('name', 'N/A')}",
            f"Date of Birth - {profile.get('dob', 'N/A')}",
            f"Gender - {profile.get('gender', 'N/A')}",
            f"Blood Group - {profile.get('blood_group', 'N/A')}",
            f"Known Conditions - {profile.get('conditions', 'N/A')}"
        ]
        for key, value in profile.items():
            if key not in ['name', 'dob', 'gender', 'blood_group', 'conditions']:
                profile_details.append(f"{key} - {value}")
        profile_text = f"The user's health profile includes: {', '.join(profile_details)}."

    medications_text = ""
    if user_data.get('medications'):
        med_list = [f"{m['name']} ({m['dosage']}, {m['schedule']})" for m in user_data['medications']]
        medications_text = f"The user is currently taking the following medications: {', '.join(med_list)}."

    emergency_text = ""
    if user_data.get('emergency_contacts'):
        contact_list = []
        for c in user_data['emergency_contacts']:
            contact_details = [f"{k}: {v}" for k, v in c.items()]
            contact_list.append(f"({', '.join(contact_details)})")
        emergency_text = f"The user's emergency contacts are: {', '.join(contact_list)}."

    instruction = (
        "You are HealthBot, a friendly, helpful, and empathetic AI health assistant. "
        "Your main purpose is to provide **general health and wellness information**, tips, and motivation. "
        "You can discuss workout routines, nutrition, and general well-being. "
        "Always start your response with a clear and prominent disclaimer stating that you are not a medical professional. "
        "When a user asks for advice on a health issue, provide a structured, multi-point response that includes:\n"
        "1. **A list of non-medical, at-home measures** they can take (e.g., rest, hydration, stress reduction). Use bullet points to make this information easy to read.\n"
        "2. **A clear and explicit section on when to seek professional medical help.** Use a bold heading and a new paragraph for this section to emphasize its importance. List symptoms that require a doctor's visit using bullet points.\n"
        "3. **A closing statement** that reiterates your purpose and offers further general assistance.\n"
        "Your responses should be conversational, empathetic, and easy to understand. "
        f"Here is some information about the user to help you personalize your responses: {profile_text} {medications_text} {emergency_text}"
    )
    return instruction

# Helper to find appointment by its UUID
def find_appointment_index_by_id(appointments, appt_id):
    for idx, appt in enumerate(appointments):
        if appt.get("id") == appt_id:
            return idx
    return None

# Initialize Chat with system instruction
def get_chat_model():
    user_data = load_user_data()
    system_instruction = create_system_instruction(user_data)
    return model.start_chat(
        history=[
            {"role": "user", "parts": [system_instruction]},
            {"role": "model", "parts": ["I understand my purpose. I'm ready to help!"]}
        ]
    )

# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    try:
        user_input = request.json.get("message", "").strip()
        incoming_edit_id = request.json.get("edit_id")
        edit_id = str(incoming_edit_id) if incoming_edit_id else None
        
        # Reload chat model with updated user data for each request
        chat = get_chat_model()
        lang = session.get("lang", "en")
        
        # Translate input if not English
        if lang != "en":
            try:
                user_input_en = translator.translate(user_input, lang_tgt='en')
            except Exception as e:
                print(f"Translation error: {e}")
                user_input_en = user_input
        else:
            user_input_en = user_input

        bot_text = ""
        user_input_lower = user_input_en.lower()

        # Emergency keywords
        emergency_keywords = ["chest pain", "shortness of breath", "accident", "bleeding", "heart attack"]
        if any(re.search(r'\b' + word + r'\b', user_input_lower) for word in emergency_keywords):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is in an emergency situation. "
                "Provide **3 immediate emergency tips** based on the input, each 1-2 sentences. "
                "Do not repeat previous tips. "
                "Add a friendly tone and include a disclaimer: "
                "'This is general advice, not a substitute for professional help.'"
            )
            bot_text = "⚠️ Emergency detected! Please call 108 immediately for an ambulance. "
            try:
                response = chat.send_message(prompt + f"\nUser input: {user_input_en}")
                bot_text += response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text += " I'm sorry, I'm having trouble providing more details right now. Please seek immediate professional help."
        
        # Mental health keywords
        elif any(re.search(r'\b' + word + r'\b', user_input_lower) for word in ["stress", "anxious", "depressed", "sad", "low mood"]):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is feeling stressed or anxious. "
                "Provide **3 practical mental health tips** based on the input, each 1-2 sentences. "
                "Do not repeat previous tips. "
                "Add a friendly tone and include a disclaimer: "
                "'This is general advice, not a substitute for professional help.'"
                f"\nUser input: {user_input_en}"
            )
            try:
                response = chat.send_message(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."
        
        # Nutrition and lifestyle keywords
        elif any(re.search(r'\b' + word + r'\b', user_input_lower) for word in ["diet", "food", "nutrition", "exercise", "diabetic"]):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user asked about nutrition or healthy lifestyle. "
                "Provide **3 practical tips** based on the input. "
                "Include simple advice suitable for everyday life. "
                "Add a friendly disclaimer: 'This is general advice, not a substitute for professional help.'"
                f"\nUser input: {user_input_en}"
            )
            try:
                response = chat.send_message(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Quiz and tips keywords
        elif "quiz" in user_input_lower or "tip" in user_input_lower:
            prompt = (
                "You are HealthBot. Provide a **new health quiz question or tip** for the user. "
                "Keep it engaging, educational, and safe. "
                "Do not repeat previous questions. "
                "Add a short disclaimer if necessary."
                f"\nUser input: {user_input_en}"
            )
            try:
                response = chat.send_message(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."
        
        # Medicine info keywords
        elif any(re.search(r'\b' + word + r'\b', user_input_lower) for word in ["medicine", "drug", "tablet", "capsule", "paracetamol", "ibuprofen"]):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is asking about a medicine. "
                "Provide general information about the medicine, including uses, common dosage ranges, side effects, and precautions. "
                "Do not repeat previous information. "
                "Add a friendly tone and include a disclaimer: "
                "'This is general information, not a substitute for professional medical advice. Always consult a doctor or pharmacist before taking any medication.'"
                f"\nUser question: {user_input_en}"
            )
            try:
                response = chat.send_message(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Symptom checker keywords
        elif any(re.search(r'\b' + word + r'\b', user_input_lower) for word in ["symptom", "fever", "headache", "cough", "nausea", "fatigue"]):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is asking about symptoms. "
                "Provide general information about possible causes and safe home remedies based on the symptoms. "
                "Do not make a definitive diagnosis. "
                "Add a friendly tone and include a disclaimer: "
                "'This is general information, not a substitute for professional medical advice. If symptoms persist, consult a doctor.'"
                f"\nUser symptoms: {user_input_en}"
            )
            try:
                response = chat.send_message(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."
        
        # Default chat
        else:
            try:
                response = chat.send_message(user_input_en)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Translate back to Telugu if needed
        if lang != "en":
            try:
                bot_text = translator.translate(bot_text, lang_tgt=lang)
            except Exception as e:
                print(f"Translation error: {e}")
                # Keep English text if translation fails

        if edit_id:
            update_log(edit_id, user_input, bot_text)
        else:
            save_message(user_input, bot_text)

        return jsonify({"reply": bot_text})

    except Exception as e:
        print(f"Error in ask route: {e}")
        print(traceback.format_exc())
        return jsonify({"reply": "I'm sorry, I'm experiencing technical difficulties. Please try again later."}), 500

@app.route("/get_user_data", methods=["GET"])
def get_user_data():
    return jsonify(load_user_data())

@app.route("/get_doctors", methods=["GET"])
def get_doctors():
    doctors = []
    for doc in DOCTOR_DIRECTORY:
        doc_info = doc.copy()
        doc_info["times"] = DOCTOR_SCHEDULES.get(doc["id"], [])
        doctors.append(doc_info)
    return jsonify(doctors)

@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = load_user_data()
    profile_data = request.json
    data["profile"] = profile_data
    save_user_data(data)
    return jsonify({"status": "success", "message": "Profile saved!"})

@app.route("/save_medication", methods=["POST"])
def save_medication():
    data = load_user_data()
    medication = request.json
    if "medications" not in data:
        data["medications"] = []
    data["medications"].append(medication)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Medication added!"})

@app.route("/update_medication/<int:index>", methods=["PUT"])
def update_medication(index):
    data = load_user_data()
    updated_medication = request.json
    if 0 <= index < len(data.get("medications", [])):
        data["medications"][index] = updated_medication
        save_user_data(data)
        return jsonify({"status": "success", "message": "Medication updated."})
    return jsonify({"status": "error", "message": "Medication not found."}), 404

@app.route("/delete_medication/<int:index>", methods=["DELETE"])
def delete_medication(index):
    data = load_user_data()
    if 0 <= index < len(data.get("medications", [])):
        data["medications"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Medication deleted."})
    return jsonify({"status": "error", "message": "Medication not found."}), 404

@app.route("/save_emergency_contact", methods=["POST"])
def save_emergency_contact():
    data = load_user_data()
    contact = request.json
    if "emergency_contacts" not in data:
        data["emergency_contacts"] = []
    data["emergency_contacts"].append(contact)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Emergency contact added!"})

@app.route("/update_emergency_contact/<int:index>", methods=["PUT"])
def update_emergency_contact(index):
    data = load_user_data()
    updated_contact = request.json
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"][index] = updated_contact
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact updated."})
    return jsonify({"status": "error", "message": "Emergency contact not found."}), 404

@app.route("/delete_emergency_contact/<int:index>", methods=["DELETE"])
def delete_emergency_contact(index):
    data = load_user_data()
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact deleted."})
    return jsonify({"status": "error", "message": "Emergency contact not found."}), 404

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = load_user_data()
    appointment = request.json
    if "appointments" not in data:
        data["appointments"] = []
    appointment["id"] = str(uuid.uuid4())
    data["appointments"].append(appointment)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Appointment added!", "appointment": appointment})

@app.route("/update_appointment/<appt_id>", methods=["PUT"])
def update_appointment(appt_id):
    data = load_user_data()
    appointments = data.get("appointments", [])
    idx = find_appointment_index_by_id(appointments, appt_id)
    if idx is not None:
        updated_appointment = request.json
        updated_appointment["id"] = appt_id
        appointments[idx] = updated_appointment
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment updated."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404

@app.route("/delete_appointment/<appt_id>", methods=["DELETE"])
def delete_appointment(appt_id):
    data = load_user_data()
    appointments = data.get("appointments", [])
    idx = find_appointment_index_by_id(appointments, appt_id)
    if idx is not None:
        appointments.pop(idx)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment deleted."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404

@app.route("/set_language", methods=["POST"])
def set_language():
    lang = request.json.get("language", "en")
    session["lang"] = lang
    return jsonify({"status": "success", "message": f"Language set to {lang}"})

@app.route("/get_chat_history", methods=["GET"])
def get_chat_history():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        history = []

    greeting = "Hello! I'm Sehat Sethu, your personal health assistant. I can help you manage your health profile, medications, appointments, and more. How can I assist you today?"
    if not history or not any(h.get("bot", "").strip() == greeting.strip() for h in history):
        history.insert(0, {
            "id": str(uuid.uuid4()),
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        })
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    five_days_ago = datetime.datetime.now() - datetime.timedelta(days=5)
    filtered_history = [
        h for h in history 
        if "timestamp" in h and datetime.datetime.fromisoformat(h["timestamp"]) >= five_days_ago
    ]
    
    filtered_history = filtered_history[-50:]
    return jsonify({"status": "success", "history": filtered_history})

@app.route('/uploads/<path:filename>', methods=["GET"])
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    try:
        greeting = "Hello! I'm Sehat Sethu, your personal health assistant. I can help you manage your health profile, medications, appointments, and more. How can I assist you today?"
        
        history = [{
            "id": str(uuid.uuid4()),
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        }]
        
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": "Chat cleared"})
    except Exception as e:
        print(f"Error clearing chat: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_weather_tip", methods=["GET"])
def get_weather_tip():
    tips = {
        'Clear': "It's a beautiful day! Go for a walk and get some natural sunlight. It's great for your mood and Vitamin D.",
        'Clouds': "A cloudy day is perfect for an indoor workout. Try some light stretches or yoga to stay active.",
        'Rain': "Stay indoors and hydrate! A warm cup of herbal tea can be very comforting on a rainy day.",
        'Snow': "If you're going out, remember to bundle up in layers to stay warm. A hot, nutritious soup is a great way to warm up afterwards.",
        'Mist': "Visibility is low. If you're driving, be extra careful. Inside, take some time for mindfulness and deep breathing.",
        'default': "The weather is changing. Remember to drink plenty of water and eat a balanced meal to keep your immune system strong."
    }

    try:
        mock_weather_data = {'weather': [{'main': 'Clear'}]}
        condition = mock_weather_data['weather'][0]['main']
        tip = tips.get(condition, tips['default'])
        return jsonify({"tip": tip})
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return jsonify({"tip": tips['default']}), 500

@app.route("/find_doctors", methods=["GET"])
def find_doctors():
    try:
        specialty = (request.args.get("specialty") or "").strip().lower()
        location = (request.args.get("location") or "").strip().lower()

        if not specialty:
            return jsonify({"status": "error", "message": "specialty is required"}), 400

        if not location:
            user = load_user_data()
            profile_loc = (user.get("profile", {}).get("location") or user.get("profile", {}).get("city") or "").strip().lower()
            location = profile_loc

        matches = []
        for doc in DOCTOR_DIRECTORY:
            doc_specialty = doc["specialty"].lower()
            doc_location = doc["location"].lower()
            
            if doc_specialty.startswith(specialty):
                if location and location in doc_location:
                    matches.append(doc)
                elif not location:
                    matches.append(doc)

        return jsonify({"status": "success", "doctors": matches})
    except Exception as e:
        print(f"/find_doctors error: {e}")
        return jsonify({"status": "error", "message": "Failed to find doctors"}), 500

# ---------------------------
# OCR: Image to text
# ---------------------------
@app.route("/image_to_text", methods=["POST"])
def image_to_text():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image provided"}), 400

        file = request.files['image']
        original_filename = secure_filename(file.filename or "uploaded_image")
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base, ext = os.path.splitext(original_filename)
        safe_filename = f"{base}_{timestamp_str}{ext or '.bin'}"
        saved_path = os.path.join(UPLOAD_DIR, safe_filename)
        content = file.read()
        
        if not content:
            return jsonify({"error": "Empty file"}), 400

        with open(saved_path, "wb") as out_f:
            out_f.write(content)

        parts = [
            {"mime_type": file.mimetype or "image/jpeg", "data": content}
        ]

        prompt = (
            "Extract all readable text from this image."
            " If the image contains tables or receipts, read line-by-line in natural order."
            " Return plain text only, no extra commentary."
        )

        try:
            response = vision_model.generate_content([
                {"text": prompt},
                {"inline_data": parts[0]}
            ])
            extracted = (response.text or "").strip()
        except Exception as e:
            print(f"Vision API error: {e}")
            extracted = ""

        file_location = f"/uploads/{safe_filename}"
        return jsonify({"text": extracted or "", "location": file_location})
    except Exception as e:
        print(f"/image_to_text error: {e}")
        return jsonify({"error": "Failed to process image"}), 500

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    flask_port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=flask_port, debug=False)