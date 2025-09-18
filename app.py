from flask import Flask, render_template, request, jsonify, session
import google.generativeai as genai
import os, json, datetime, traceback
from google_trans_new import google_translator
from flask_cors import CORS

# ---------------------------
# Setup
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "chat_log.json")
USER_DATA_FILE = os.path.join(BASE_DIR, "user_data.json")
APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.json")

# Ensure files exist
for file_path, default_data in [
    (LOG_FILE, []),
    (USER_DATA_FILE, {"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []}),
    (APPOINTMENTS_FILE, {})
]:
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default_data, f)

# Doctor data
DOCTORS = {
    "Cardiology": {
        "Dr. A. Sharma": ["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "04:00 PM"],
        "Dr. B. Mehta": ["10:00 AM", "01:00 PM", "03:00 PM"]
    },
    "Neurology": {
        "Dr. C. Reddy": ["09:30 AM", "11:30 AM", "02:30 PM", "05:00 PM"],
        "Dr. D. Gupta": ["10:30 AM", "12:30 PM", "03:30 PM"]
    },
    "Orthopedics": {
        "Dr. E. Patel": ["09:00 AM", "11:00 AM", "01:00 PM", "03:00 PM"],
        "Dr. F. Nair": ["10:00 AM", "12:00 PM", "02:00 PM", "04:00 PM"]
    },
    "Dermatology": {
        "Dr. G. Khan": ["09:30 AM", "11:30 AM", "01:30 PM", "03:30 PM"],
        "Dr. H. Das": ["10:30 AM", "12:30 PM", "02:30 PM", "04:30 PM"]
    },
    "Pediatrics": {
        "Dr. I. Singh": ["09:00 AM", "10:30 AM", "12:00 PM", "02:00 PM"],
        "Dr. J. Verma": ["11:00 AM", "01:00 PM", "03:00 PM", "05:00 PM"]
    },
    "General Medicine": {
        "Dr. K. Roy": ["09:00 AM", "11:00 AM", "01:00 PM", "03:00 PM"],
        "Dr. L. Menon": ["10:00 AM", "12:00 PM", "02:00 PM", "04:00 PM"]
    }
}

# Translator
translator = google_translator()

# Flask
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
CORS(app)

# Google API
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("⚠️ GOOGLE_API_KEY is not set.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ---------------------------
# Helpers
# ---------------------------
def safe_load_json(path, default):
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"JSON read error from {path}: {e}")
    return default

def safe_dump_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"JSON write error to {path}: {e}")

def update_log(edit_id: str, user_input: str, bot_text: str):
    chat_history = safe_load_json(LOG_FILE, [])
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
    safe_dump_json(LOG_FILE, chat_history)

def save_message(user_input: str, bot_text: str):
    chat_history = safe_load_json(LOG_FILE, [])
    new_id = str(datetime.datetime.now().timestamp())
    chat_history.append({
        "id": new_id,
        "user": user_input,
        "bot": bot_text,
        "timestamp": datetime.datetime.now().isoformat()
    })
    safe_dump_json(LOG_FILE, chat_history)
    return new_id

def load_user_data():
    return safe_load_json(USER_DATA_FILE, {"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []})

def save_user_data(data):
    safe_dump_json(USER_DATA_FILE, data)

def create_system_instruction(user_data):
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
        profile_text = f"User profile: {', '.join(profile_details)}."
    meds = ""
    if user_data.get('medications'):
        meds = "Medications: " + ", ".join([f"{m['name']} ({m['dosage']}, {m['schedule']})" for m in user_data['medications']])
    emergency = ""
    if user_data.get('emergency_contacts'):
        emergency = "Emergency contacts: " + ", ".join([str(c) for c in user_data['emergency_contacts']])
    return (
        "You are HealthBot, a friendly, helpful health assistant. Provide general health and wellness tips. "
        "Never give medical diagnoses or prescriptions. Always disclaim that you are not a medical professional. "
        f"{profile_text} {meds} {emergency}"
    )

def translate_to_telugu(text: str) -> str:
    try:
        return translator.translate(text, lang_tgt='te')
    except Exception as e:
        print(f"Translation failed: {e}")
        return text

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

        current_user_data = load_user_data()
        system_instruction = create_system_instruction(current_user_data)
        lang = session.get("lang", "en")

        try:
            user_input_en = translator.translate(user_input, lang_tgt='en') if lang == "te" else user_input
        except Exception:
            user_input_en = user_input

        user_lower = user_input_en.lower()

        # Emergency check
        emergency_keywords = ["chest pain", "shortness of breath", "accident", "bleeding", "heart attack", "unconscious", "stroke", "seizure", "poison", "severe burn", "heavy bleeding"]
        if any(word in user_lower for word in emergency_keywords):
            emergency_message = (
                "⚠️ This may be an emergency. Call 108 now.\n"
                "Immediate actions:\n- Stay with the person. Keep them safe and calm.\n- If bleeding: apply pressure with clean cloth.\n- If unconscious but breathing: recovery position.\n\n"
                "While waiting:\n- Keep phone nearby, unlock door, have ID/medicines ready.\n- Do not give food, drink, or medicine unless told."
            )
            if lang == "te":
                emergency_message = translate_to_telugu(emergency_message)
            return jsonify({"reply": emergency_message})

        # Mental health
        if any(w in user_lower for w in ["stress", "anxious", "depressed", "sad", "low mood", "overwhelmed", "panic"]):
            prompt = (
                "Provide 3 practical mental health tips (1–2 sentences each). End with 'This is general guidance, not a substitute for professional care.'\n"
                f"User: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception:
                bot_text = "• Try deep breathing. • Set small daily goals. • Talk to a trusted person. This is general guidance, not a substitute for professional care."
        elif any(w in user_lower for w in ["diet", "food", "nutrition", "exercise", "workout", "diabetic", "diabetes"]):
            prompt = (
                "Provide 3 practical diet/lifestyle tips. End with a disclaimer that this is general guidance.\n"
                f"User: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception:
                bot_text = "• Eat balanced meals. • Stay hydrated. • Move 30 mins daily. General guidance only."
        elif "quiz" in user_lower or "tip" in user_lower:
            try:
                response = model.generate_content("Give a short health quiz or tip (under 50 words).")
                bot_text = response.text
            except Exception:
                bot_text = "Tip: A 10-minute walk after meals helps digestion."
        elif any(w in user_lower for w in ["medicine", "drug", "tablet", "capsule", "paracetamol", "ibuprofen", "antibiotic"]):
            prompt = (
                "Provide general medicine info: uses, common side effects, safety warnings, red flags, and storage (no dosages).\n"
                f"User: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception:
                bot_text = "General medicine info: used for relief, mild side effects possible, avoid if allergic, seek care if severe, store cool/dry."
        elif ("symptom" in user_lower) or any(sym in user_lower for sym in ["fever", "headache", "cough", "nausea", "fatigue", "vomit", "pain", "sore throat"]):
            prompt = (
                "Provide structured advice for symptoms: (A) home care, (B) monitor, (C) red flags, (D) 3 follow-up questions. Avoid diagnosis/dosing.\n"
                f"User: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception:
                bot_text = "Home: rest/hydrate. Monitor: duration/severity. Red flags: breathing issues, high fever, severe pain. Questions: When started? Other symptoms? Chronic issues?"
        else:
            prompt = f"User: {user_input_en}\nSystem: {system_instruction}"
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception:
                bot_text = "Sorry, I’m having trouble answering now."

        if lang == "te":
            bot_text = translate_to_telugu(bot_text)

        if edit_id:
            update_log(edit_id, user_input, bot_text)
        else:
            save_message(user_input, bot_text)

        return jsonify({"reply": bot_text})

    except Exception as e:
        print(f"Error in ask: {e}")
        print(traceback.format_exc())
        return jsonify({"reply": "Technical error, please try again."}), 500

# ---------------------------
# User Data Routes
# ---------------------------
@app.route("/get_user_data")
def get_user_data():
    return jsonify(load_user_data())

@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = load_user_data()
    data["profile"] = request.json
    save_user_data(data)
    return jsonify({"status": "success", "message": "Profile saved!"})

@app.route("/save_medication", methods=["POST"])
def save_medication():
    data = load_user_data()
    if "medications" not in data:
        data["medications"] = []
    data["medications"].append(request.json)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Medication added!"})

@app.route("/update_medication/<int:index>", methods=["PUT"])
def update_medication(index):
    data = load_user_data()
    if 0 <= index < len(data.get("medications", [])):
        data["medications"][index] = request.json
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
    if "emergency_contacts" not in data:
        data["emergency_contacts"] = []
    data["emergency_contacts"].append(request.json)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Emergency contact added!"})

@app.route("/update_emergency_contact/<int:index>", methods=["PUT"])
def update_emergency_contact(index):
    data = load_user_data()
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"][index] = request.json
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact updated."})
    return jsonify({"status": "error", "message": "Contact not found."}), 404

@app.route("/delete_emergency_contact/<int:index>", methods=["DELETE"])
def delete_emergency_contact(index):
    data = load_user_data()
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact deleted."})
    return jsonify({"status": "error", "message": "Contact not found."}), 404

# ---------------------------
# Appointment Routes
# ---------------------------
@app.route("/get_doctors")
def get_doctors():
    return jsonify(DOCTORS)

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = load_user_data()
    if "appointments" not in data:
        data["appointments"] = []
    data["appointments"].append(request.json)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Appointment saved!"})

@app.route("/update_appointment/<int:index>", methods=["PUT"])
def update_appointment(index):
    data = load_user_data()
    if 0 <= index < len(data.get("appointments", [])):
        data["appointments"][index] = request.json
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment updated."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404


@app.route("/delete_appointment/<int:index>", methods=["DELETE"])
def delete_appointment(index):
    data = load_user_data()
    if 0 <= index < len(data.get("appointments", [])):
        data["appointments"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment deleted."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404


# ---------------------------
# Chat History Routes
# ---------------------------
@app.route("/get_chat_history")
def get_chat_history():
    history = safe_load_json(LOG_FILE, [])
    return jsonify({"status": "success", "history": history})


@app.route("/clear_chat_history", methods=["POST"])
def clear_chat_history():
    safe_dump_json(LOG_FILE, [])
    return jsonify({"status": "success", "message": "Chat history cleared."})

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)