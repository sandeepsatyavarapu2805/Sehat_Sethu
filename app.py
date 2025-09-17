from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import google.generativeai as genai
import os, json, datetime
from google_trans_new import google_translator
from flask_cors import CORS

# Base directory of your app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# JSON files
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

APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.json")
if not os.path.exists(APPOINTMENTS_FILE):
    with open(APPOINTMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# Doctor data with all major branches
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


# Initialize translator
translator = google_translator()

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")  # Needed for session
CORS(app)  # Allow all origins

# Google API Key
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("⚠️ GOOGLE_API_KEY is not set.")

# Weather API mock key
WEATHER_API_KEY = "your_weather_api_key"

# Configure Generative AI
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Files
BASE_DIR = os.path.dirname(__file__)
LOG_FILE = os.path.join(BASE_DIR, "chat_log.json")
USER_DATA_FILE = os.path.join(BASE_DIR, "user_data.json")

# Ensure files exist
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
if not os.path.exists(USER_DATA_FILE):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []}, f)

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
    """Update or append chat log entries."""
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
    """Append a message to chat history and return the new id."""
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
    """Load user data from JSON file."""
    return safe_load_json(USER_DATA_FILE, {"profile": {}, "appointments": [], "emergency_contacts": [], "medications": []})

def save_user_data(data):
    """Save user data to JSON file."""
    safe_dump_json(USER_DATA_FILE, data)

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
        "Your main purpose is to provide general health and wellness information, tips, and motivation. "
        "Never give specific medical diagnoses, treatments, or prescriptions. "
        "Always start with a clear disclaimer that you are not a medical professional. "
        "When a user asks about a health issue, provide a structured response including:\n"
        "1. A list of non-medical, at-home measures (bullet points).\n"
        "2. A bold section on when to seek professional medical help with bullet points.\n"
        "3. A closing statement that reiterates your purpose.\n"
        f"Personalization context: {profile_text} {medications_text} {emergency_text}"
    )
    return instruction

def translate_to_telugu(text: str) -> str:
    """Enhanced translation with medical context using google_trans_new."""
    try:
        context_text = f"Medical health advice: {text}"
        # google_trans_new returns a plain string
        translated = translator.translate(context_text, lang_tgt='te')
        return translated
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

        # Translate input if Telugu
        try:
            user_input_en = translator.translate(user_input, lang_tgt='en') if lang == "te" else user_input
        except Exception:
            user_input_en = user_input

        user_lower = user_input_en.lower()

        # --- Emergency check (real-life, specific guidance) ---
        emergency_keywords = [
            "chest pain", "shortness of breath", "accident", "bleeding", "heart attack",
            "unconscious", "stroke", "seizure", "poison", "severe burn", "heavy bleeding"
        ]
        if any(word in user_lower for word in emergency_keywords):
            prompt = (
                "Act as a medical emergency assistant for the general public (India).\n"
                "Write a short, urgent, practical response with three sections:\n"
                "1) Immediate actions (clear bullet points, no medical jargon).\n"
                "2) Call 108 now (ambulance) and why.\n"
                "3) While waiting: simple safety steps, what to prepare (medications, records, unlocked door).\n"
                "Keep it concise and compassionate. Do not give diagnoses or drug dosing.\n\n"
                f"User described: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                emergency_message = response.text
            except Exception as e:
                print(f"Emergency generation error: {e}")
                emergency_message = (
                    "⚠️ This may be an emergency. Call 108 now for an ambulance.\n\n"
                    "Immediate actions:\n"
                    "- Stay with the person. Keep them safe and calm.\n"
                    "- If bleeding: apply firm pressure with a clean cloth.\n"
                    "- If unconscious but breathing: place in recovery position.\n\n"
                    "While waiting for help:\n"
                    "- Keep phone nearby, unlock the door, and have ID/medicines ready.\n"
                    "- Do not give food, drink, or medicine unless told by a professional."
                )
            if lang == "te":
                emergency_message = translate_to_telugu(emergency_message)
            return jsonify({"reply": emergency_message})

        # --- Mental health support (non-crisis) ---
        if any(word in user_lower for word in ["stress", "anxious", "depressed", "sad", "low mood", "overwhelmed", "panic"]):
            prompt = (
                "You are HealthBot. The user feels stressed/anxious/low mood.\n"
                "Provide exactly 3 practical tips (1-2 sentences each), grounded in everyday actions (breathing, routine, social support, sleep, activity).\n"
                "Avoid repeating tips within this conversation.\n"
                "End with: 'This is general guidance, not a substitute for professional care.'\n\n"
                f"User input: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Mental health generation error: {e}")
                bot_text = (
                    "• Try a slow-breathing routine: inhale 4s, hold 4s, exhale 6s for 3–5 minutes.\n"
                    "• Set one small task you can complete today (e.g., a short walk or tidying a corner).\n"
                    "• Talk to someone you trust and keep a regular sleep schedule.\n\n"
                    "This is general guidance, not a substitute for professional care."
                )

        # --- Nutrition and lifestyle ---
        elif any(word in user_lower for word in ["diet", "food", "nutrition", "exercise", "workout", "diabetic", "diabetes"]):
            prompt = (
                "You are HealthBot. The user asked about nutrition/lifestyle.\n"
                "Give 3 concise, practical tips for everyday life (food choices, hydration, activity, consistency).\n"
                "End with a short disclaimer that this is general guidance.\n\n"
                f"User input: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Nutrition generation error: {e}")
                bot_text = (
                    "• Aim for half your plate vegetables, a quarter protein, and a quarter whole grains.\n"
                    "• Hydrate regularly and limit sugary drinks; choose water most of the time.\n"
                    "• Do at least 30 minutes of moderate activity most days.\n\n"
                    "General guidance only; consult a professional for personalized advice."
                )

        # --- Quiz or tip ---
        elif "quiz" in user_lower or "tip" in user_lower:
            prompt = (
                "You are HealthBot. Provide a fresh health quiz question OR a short health tip.\n"
                "Keep it engaging, factual, and under 50 words."
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Quiz/tip generation error: {e}")
                bot_text = "Tip: A 10-minute walk after meals can help control blood sugar and improve digestion."

        # --- Medicine info ---
        elif any(word in user_lower for word in ["medicine", "drug", "tablet", "capsule", "paracetamol", "ibuprofen", "antibiotic"]):
            prompt = (
                "You are HealthBot. Provide general, non-prescriptive medicine information in 5 short sections:\n"
                "1) What it is commonly used for\n"
                "2) Common side effects\n"
                "3) Safety warnings (who should avoid, allergies, interactions in general terms)\n"
                "4) When to stop and seek medical care\n"
                "5) General storage/usage notes (no dosages).\n"
                "Do NOT provide doses or personalize treatment.\n\n"
                f"User question: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Medicine info generation error: {e}")
                bot_text = (
                    "General info: I can share typical uses, common side effects, and safety notes, but not dosing.\n"
                    "- Uses: pain, fever, or as directed by a doctor (depends on the medicine).\n"
                    "- Side effects: usually mild; stop if rash, swelling, or breathing trouble.\n"
                    "- Safety: avoid if allergic; be careful with liver/kidney problems and other medicines.\n"
                    "- Seek care: severe reactions, worsening symptoms, or no improvement.\n"
                    "- Storage: keep in a cool, dry place away from children."
                )

        # --- Symptom check ---
        elif ("symptom" in user_lower) or any(sym in user_lower for sym in ["fever", "headache", "cough", "nausea", "fatigue", "vomit", "pain", "sore throat"]):
            prompt = (
                "You are HealthBot. Provide a brief, structured response for common symptoms.\n"
                "Include: (A) Simple at-home care steps; (B) What to monitor; (C) Red flags that need in-person care; (D) 3 follow-up questions to better understand.\n"
                "Avoid diagnosis and dosing. Keep it practical and plain language.\n\n"
                f"User symptoms: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Symptom generation error: {e}")
                bot_text = (
                    "At-home: rest, hydrate, and use light meals; track temperature and symptoms.\n"
                    "Monitor: duration, severity, new symptoms.\n"
                    "Red flags: trouble breathing, persistent high fever, severe pain, confusion, dehydration.\n"
                    "Questions: When did it start? Any other symptoms? Any chronic conditions or new medicines?"
                )

        # --- Default chat ---
        else:
            prompt = (
                "You are HealthBot, a friendly non-clinical health assistant.\n"
                "Provide practical, real-world advice without diagnosing.\n"
                "Structure: (1) Simple tips; (2) When to seek help; (3) Next steps or questions for the user.\n\n"
                f"System instruction:\n{system_instruction}\n\nUser: {user_input_en}"
            )
            try:
                response = model.generate_content(prompt)
                bot_text = response.text
            except Exception as e:
                print(f"Default generation error: {e}")
                bot_text = (
                    "Here are some general tips based on what you shared.\n"
                    "- Start with simple, consistent habits.\n"
                    "- Watch how your body responds and adjust.\n"
                    "Seek help if symptoms persist or worsen."
                )

        # Translate back if Telugu
        if lang == "te":
            bot_text = translate_to_telugu(bot_text)

        # Save message
        if edit_id:
            update_log(edit_id, user_input, bot_text)
        else:
            save_message(user_input, bot_text)

        return jsonify({"reply": bot_text})

    except Exception as e:
        print(f"Error in ask route: {e}")
        error_message = "⚠️ Technical error, please try again later."
        if session.get("lang") == "te":
            error_message = translate_to_telugu(error_message)
        return jsonify({"reply": error_message}), 500

@app.route("/get_user_data", methods=["GET"])
def get_user_data():
    return jsonify(load_user_data())

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

@app.route("/get_appointments")
def get_appointments():
    data = safe_load_json(APPOINTMENTS_FILE, {})
    # convert dict to list for JS
    appointments = list(data.values())
    return jsonify({"appointments": appointments})

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = safe_load_json(APPOINTMENTS_FILE, {})
    appointment = request.json
    key = str(len(data))
    data[key] = appointment
    safe_dump_json(APPOINTMENTS_FILE, data)
    return jsonify({"status": "success", "message": "Appointment added!"})

@app.route("/update_appointment/<int:index>", methods=["PUT"])
def update_appointment(index):
    data = safe_load_json(APPOINTMENTS_FILE, {})
    key = str(index)
    if key in data:
        data[key] = request.json
        safe_dump_json(APPOINTMENTS_FILE, data)
        return jsonify({"status": "success", "message": "Appointment updated."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404

@app.route("/delete_appointment/<int:index>", methods=["DELETE"])
def delete_appointment(index):
    data = safe_load_json(APPOINTMENTS_FILE, {})
    key = str(index)
    if key in data:
        del data[key]
        safe_dump_json(APPOINTMENTS_FILE, data)
        return jsonify({"status": "success", "message": "Appointment deleted."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404

@app.route("/set_language", methods=["POST"])
def set_language():
    """Set the language preference for the session."""
    lang = request.json.get("language", "en")
    session["lang"] = lang
    return jsonify({"status": "success", "message": f"Language set to {lang}"})

@app.route("/get_chat_history", methods=["GET"])
def get_chat_history():
    history = safe_load_json(LOG_FILE, [])
    greeting = "👋 Hello! I'm Sehat Sethu, your health assistant. How can I help you today?"

    # Add greeting once
    if not any(h.get("id") == "greeting" for h in history):
        history.insert(0, {
            "id": "greeting",
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        })
        safe_dump_json(LOG_FILE, history)

    five_days_ago = datetime.datetime.now() - datetime.timedelta(days=5)
    filtered_history = [
        h for h in history
        if h.get("id") == "greeting" or (
            "timestamp" in h and datetime.datetime.fromisoformat(h["timestamp"]) >= five_days_ago
        )
    ]
    filtered_history = filtered_history[-50:]
    return jsonify({"status": "success", "history": filtered_history})

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    """Clear chat history and start new chat."""
    try:
        greeting = "👋 Hello! I'm Sehat Sethu, your health assistant. How can I help you today?"
        history = [{
            "id": "greeting",
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        }]
        safe_dump_json(LOG_FILE, history)
        return jsonify({"status": "success", "message": "Chat cleared"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/clear_chat_history", methods=["POST"])
def clear_chat_history():
    """Clear entire chat history (used by history page)."""
    try:
        safe_dump_json(LOG_FILE, [])
        return jsonify({"status": "success", "message": "Chat history cleared"})
    except Exception as e:
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
# ---------------------------
# Appointments Section
# ---------------------------

# Ensure the appointments file exists
APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.json")
if not os.path.exists(APPOINTMENTS_FILE):
    with open(APPOINTMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# Show appointments page
@app.route("/appointments")
def appointments():
    # Remove the unused variable entirely
    return render_template("appointments.html", doctors=DOCTORS)

# Save appointment (HTML form submission)
@app.route("/save_appointment_form", methods=["POST"])
def save_appointment_form():
    data = safe_load_json(APPOINTMENTS_FILE, {})
    appointment_id = str(len(data) + 1)
    appointment = {
        "department": request.form.get("department", ""),
        "doctor": request.form.get("doctor", ""),
        "issue": request.form.get("issue", ""),
        "date": request.form.get("date", ""),
        "time": request.form.get("time", "")
    }
    data[appointment_id] = appointment
    safe_dump_json(APPOINTMENTS_FILE, data)
    return redirect(url_for("appointments"))

# Edit appointment (HTML form submission)
@app.route("/appointments/edit/<appointment_id>", methods=["POST"])
def edit_appointment(appointment_id):
    data = safe_load_json(APPOINTMENTS_FILE, {})
    if appointment_id in data:
        data[appointment_id] = {
            "department": request.form.get("department", ""),
            "doctor": request.form.get("doctor", ""),
            "issue": request.form.get("issue", ""),
            "date": request.form.get("date", ""),
            "time": request.form.get("time", "")
        }
        safe_dump_json(APPOINTMENTS_FILE, data)
    return redirect(url_for("appointments"))

# Cancel appointment
@app.route("/appointments/cancel/<appointment_id>", methods=["POST"])
def cancel_appointment(appointment_id):
    data = safe_load_json(APPOINTMENTS_FILE, {})
    if appointment_id in data:
        del data[appointment_id]
        safe_dump_json(APPOINTMENTS_FILE, data)
    return redirect(url_for("appointments"))

# Check available slots (AJAX call)
@app.route("/available_slots/<department>/<doctor>/<date>")
def available_slots(department, doctor, date):
    all_slots = DOCTORS.get(department, {}).get(doctor, [])
    booked_slots = []
    data = safe_load_json(APPOINTMENTS_FILE, {})
    for _, app in data.items():
        if app.get("doctor") == doctor and app.get("date") == date:
            booked_slots.append(app.get("time"))
    return jsonify({"all_slots": all_slots, "booked_slots": booked_slots})

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    Flask_port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=Flask_port, debug=False)