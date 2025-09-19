from flask import Flask, render_template, request, jsonify, session
import google.generativeai as genai
import os, json, datetime
from google_trans_new import google_translator
from flask_cors import CORS
import traceback
import speech_recognition as sr
from pydub import AudioSegment
import tempfile

# Initialize translator
translator = google_translator()

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")  # Needed for session
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
vision_model = genai.GenerativeModel("gemini-1.5-flash")

LOG_FILE = os.path.join(os.path.dirname(__file__), "chat_log.json")

# Auto-create chat_log.json if missing
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

USER_DATA_FILE = "user_data.json"

# ---------------------------
# Helpers
# ---------------------------
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


def create_system_instruction(user_data):
    """Generate personalized system instruction for AI."""
    profile_text = ""
    if user_data.get('profile'):
        profile = user_data['profile']
        profile_details = [f"Name - {profile.get('name', 'N/A')}", f"Date of Birth - {profile.get('dob', 'N/A')}", f"Gender - {profile.get('gender', 'N/A')}", f"Blood Group - {profile.get('blood_group', 'N/A')}", f"Known Conditions - {profile.get('conditions', 'N/A')}"]
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
        "**Never give specific medical diagnoses, treatments, or remedies.** "
        "Always start your response with a clear and prominent disclaimer stating that you are not a medical professional. "
        "When a user asks for advice on a health issue, provide a structured, multi-point response that includes:\n"
        "1. **A list of non-medical, at-home measures** they can take (e.g., rest, hydration, stress reduction). Use bullet points to make this information easy to read.\n"
        "2. **A clear and explicit section on when to seek professional medical help.** Use a bold heading and a new paragraph for this section to emphasize its importance. List symptoms that require a doctor's visit using bullet points.\n"
        "3. **A closing statement** that reiterates your purpose and offers further general assistance.\n"
        "Your responses should be conversational, empathetic, and easy to understand. "
        f"Here is some information about the user to help you personalize your responses: {profile_text} {medications_text} {emergency_text}"
    )
    return instruction


# Initialize Chat
user_data = load_user_data()
chat = model.start_chat(
    history=[
        {"role": "user", "parts": [create_system_instruction(user_data)]},
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

        current_user_data = load_user_data()
        system_instruction = create_system_instruction(current_user_data)

        lang = session.get("lang", "en")

        # Translate input if Telugu
        try:
            user_input_en = translator.translate(user_input, lang_tgt='en') if lang == "te" else user_input
        except Exception as e:
            print(f"Translation error: {e}")
            user_input_en = user_input  # Fallback to original input

        # Emergency check
        emergency_keywords = ["chest pain", "shortness of breath", "accident", "bleeding", "heart attack"]
        if any(word in user_input_en.lower() for word in emergency_keywords):
            emergency_message = (
                "⚠️ Emergency detected!\n"
                "Please call 108 immediately for an ambulance.\n"
                "You are HealthBot, a friendly AI assistant. "
                "The user is in am emergency situation "
                "Provide **3 practical emergency tips**, each 1-2 sentences. "
                "Do not repeat previous tips. "
                "And give the user tips to decrease the emergency"
                "'This is general advice, not a substitute for professional help.'"
            )
            if lang == "te":
                try:
                    emergency_message = translator.translate(emergency_message, lang_tgt='te')
                except Exception as e:
                    pass  # Use English if translation fails
            return jsonify({"reply": emergency_message})

        # Mental health check
        if any(word.lower() in user_input_en.lower() for word in ["stress", "anxious", "depressed", "sad", "low mood"]):
            prompt = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is feeling stressed or anxious. "
                "Provide **3 practical mental health tips**, each 1-2 sentences. "
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
        
        # Nutrition and lifestyle check
        if any(word.lower() in user_input_en.lower() for word in ["diet", "food", "nutrition", "exercise", "diabetic"]):
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

        # Quiz and tips check
        if "quiz" in user_input_en.lower() or "tip" in user_input_en.lower():
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
        
        # Medicine info check
        medicine_keywords = ["medicine", "drug", "tablet", "capsule", "syrup", "injection", "dose"]
        if any(word.lower() in user_input_en.lower() for word in medicine_keywords):
            disclaimer = (
                "⚠️ I can share general information about medicines, "
                "like their usual uses, side effects, and precautions. "
                "This is **full information, side effects and uses of the medicine with caution**. Please talk to a doctor or pharmacist "
                "before taking anything."
            )
            formatted_input = (
                f"{disclaimer}\n\n"
                f"User question: {user_input_en}\n"
                "Answer in clear, everyday language."
            )
            try:
                response = chat.send_message(formatted_input)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Symptom checker
        elif "symptom" in user_input_en.lower() or any(symptom_word in user_input_en.lower() for symptom_word in ["fever","headache","cough","nausea","fatigue","symptom", "pain", "ache", "rash", "dizziness", "weakness", "cold", "flu", "vomiting"]):
            disclaimer = (
                "You are HealthBot, a friendly AI assistant. "
                "The user is feeling something wrong with his body like stressed "
                "Provide **5 practical diseases or infection he is suffering from according **, each 2-3 sentences. "
                "Do not repeat previous tips. "
                "Add a friendly tone and include a disclaimer: "
                "'This is general advice, not a substitute for professional help.'"
            )
            formatted_input = (
                f"{disclaimer}\n\n"
                f"User symptoms: {user_input_en}\n"
                "Explain possible common causes and simple home care in a friendly way."
            )
            try:
                response = chat.send_message(formatted_input)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Default chat
        else:
            formatted_input = f"User: {user_input_en}\nHealthBot instructions: {system_instruction}"
            try:
                response = chat.send_message(formatted_input)
                bot_text = response.text
            except Exception as e:
                print(f"AI response error: {e}")
                bot_text = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

        # Translate back to Telugu if needed
        if lang == "te":
            try:
                bot_text = translator.translate(bot_text, lang_tgt='te')
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
    
def save_message(user_input, bot_text):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except:
        history = []

    history.append({
        "id": str(datetime.datetime.now().timestamp()),
        "user": user_input,
        "bot": bot_text,
        "timestamp": datetime.datetime.now().isoformat()
    })

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


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
    """Adds a new medication."""
    data = load_user_data()
    medication = request.json
    if "medications" not in data:
        data["medications"] = []
    data["medications"].append(medication)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Medication added!"})


@app.route("/update_medication/<int:index>", methods=["PUT"])
def update_medication(index):
    """Updates an existing medication by its index."""
    data = load_user_data()
    updated_medication = request.json
    if 0 <= index < len(data.get("medications", [])):
        data["medications"][index] = updated_medication
        save_user_data(data)
        return jsonify({"status": "success", "message": "Medication updated."})
    return jsonify({"status": "error", "message": "Medication not found."}), 404


@app.route("/delete_medication/<int:index>", methods=["DELETE"])
def delete_medication(index):
    """Deletes a medication by its index."""
    data = load_user_data()
    if 0 <= index < len(data.get("medications", [])):
        data["medications"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Medication deleted."})
    return jsonify({"status": "error", "message": "Medication not found."}), 404


@app.route("/save_emergency_contact", methods=["POST"])
def save_emergency_contact():
    """Adds a new emergency contact, including custom fields."""
    data = load_user_data()
    contact = request.json
    if "emergency_contacts" not in data:
        data["emergency_contacts"] = []
    data["emergency_contacts"].append(contact)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Emergency contact added!"})


@app.route("/update_emergency_contact/<int:index>", methods=["PUT"])
def update_emergency_contact(index):
    """Updates an existing emergency contact by its index."""
    data = load_user_data()
    updated_contact = request.json
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"][index] = updated_contact
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact updated."})
    return jsonify({"status": "error", "message": "Emergency contact not found."}), 404


@app.route("/delete_emergency_contact/<int:index>", methods=["DELETE"])
def delete_emergency_contact(index):
    """Deletes an emergency contact by its index."""
    data = load_user_data()
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact deleted."})
    return jsonify({"status": "error", "message": "Emergency contact not found."}), 404


@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    """Adds a new appointment."""
    data = load_user_data()
    appointment = request.json
    if "appointments" not in data:
        data["appointments"] = []
    data["appointments"].append(appointment)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Appointment added!"})


@app.route("/update_appointment/<int:index>", methods=["PUT"])
def update_appointment(index):
    """Updates an existing appointment by its index."""
    data = load_user_data()
    updated_appointment = request.json
    if 0 <= index < len(data.get("appointments", [])):
        data["appointments"][index] = updated_appointment
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment updated."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404


@app.route("/delete_appointment/<int:index>", methods=["DELETE"])
def delete_appointment(index):
    """Deletes an appointment by its index."""
    data = load_user_data()
    if 0 <= index < len(data.get("appointments", [])):
        data["appointments"].pop(index)
        save_user_data(data)
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
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except:
        history = []

    greeting = "Hello! I'm Sehat Sethu, your personal health assistant. I can help you manage your health profile, medications, appointments, and more. How can I assist you today?"

    # Append greeting only if no messages or no existing greeting
    if len(history) == 0 or not any(h.get("bot") == greeting for h in history):
        history.append({
            "id": str(datetime.datetime.now().timestamp()),
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        })
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    # Filter the chats from last 5 days
    five_days_ago = datetime.datetime.now() - datetime.timedelta(days=5)
    filtered_history = [h for h in history if "timestamp" in h and datetime.datetime.fromisoformat(h["timestamp"]) >= five_days_ago]
    
    # Limit to last 50 messages
    filtered_history = filtered_history[-50:]
    return jsonify({"status": "success", "history": filtered_history})

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    """Clear chat history and start new chat."""
    try:
        greeting = "Hello! I'm Sehat Sethu, your personal health assistant. I can help you manage your health profile, medications, appointments, and more. How can I assist you today?"
        
        history = [{
            "id": str(datetime.datetime.now().timestamp()),
            "user": "",
            "bot": greeting,
            "timestamp": datetime.datetime.now().isoformat()
        }]

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        return jsonify({"status": "success", "message": "Chat cleared"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_weather_tip", methods=["GET"])
def get_weather_tip():
    """Fetches weather data for a location and provides a relevant health tip."""
    tips = {
        'Clear': "It's a beautiful day! Go for a walk and get some natural sunlight. It's great for your mood and Vitamin D.",
        'Clouds': "A cloudy day is perfect for an indoor workout. Try some light stretches or yoga to stay active.",
        'Rain': "Stay indoors and hydrate! A warm cup of herbal tea can be very comforting on a rainy day.",
        'Snow': "If you're going out, remember to bundle up in layers to stay warm. A hot, nutritious soup is a great way to warm up afterwards.",
        'Mist': "Visibility is low. If you're driving, be extra careful. Inside, take some time for mindfulness and deep breathing.",
        'default': "The weather is changing. Remember to drink plenty of water and eat a balanced meal to keep your immune system strong."
    }

    try:
        # Mocking a real weather API call for a simple example.
        # In a real app, you would use a service like OpenWeatherMap
        # and get the user's location.
        mock_weather_data = {'weather': [{'main': 'Clear'}]}
        condition = mock_weather_data['weather'][0]['main']
        tip = tips.get(condition, tips['default'])
        return jsonify({"tip": tip})
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return jsonify({"tip": tips['default']}), 500


# ---------------------------
# OCR: Image to text
# ---------------------------
@app.route("/image_to_text", methods=["POST"])
def image_to_text():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image provided"}), 400

        file = request.files['image']
        content = file.read()
        if not content:
            return jsonify({"error": "Empty file"}), 400

        # Gemini expects inline data parts for images
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

        return jsonify({"text": extracted or ""})
    except Exception as e:
        print(f"/image_to_text error: {e}")
        return jsonify({"error": "Failed to process image"}), 500

@app.route("/image_identify", methods=["POST"])
def image_identify():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image provided"}), 400
        file = request.files['image']
        content = file.read()
        if not content:
            return jsonify({"error": "Empty file"}), 400

        parts = [{"mime_type": file.mimetype or "image/jpeg", "data": content}]
        prompt = (
            "Describe concisely what is visible in this image. "
            "List main objects, the setting (indoor/outdoor), and any noteworthy details. "
            "Return plain text only, no advice or safety instructions."
        )

        try:
            response = vision_model.generate_content([
                {"text": prompt},
                {"inline_data": parts[0]}
            ])
            description = (response.text or "").strip()
        except Exception as e:
            print(f"Vision API error (identify): {e}")
            description = ""

        return jsonify({"description": description or "No description available."})
    except Exception as e:
        print(f"/image_identify error: {e}")
        return jsonify({"error": "Failed to identify image"}), 500

@app.route("/audio_to_text", methods=["POST"])
def audio_to_text():
    """Accepts an audio file and returns recognized text (uses Google Web Speech via SpeechRecognition)."""
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400

        file = request.files['audio']
        if file.filename == "":
            return jsonify({"error": "Empty filename"}), 400

        # Save incoming file to a temp file
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file.filename)[1], delete=False) as tmp_in:
            tmp_in.write(file.read())
            tmp_in.flush()
            in_path = tmp_in.name

        # Convert to WAV for SpeechRecognition if necessary
        wav_path = in_path + ".wav"
        try:
            audio = AudioSegment.from_file(in_path)
            audio.export(wav_path, format="wav")
        except Exception as e:
            print(f"Audio conversion error: {e}")
            return jsonify({"error": "Failed to convert audio"}), 500

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        try:
            # This uses Google Web Speech - no API key required but has quotas.
            text = recognizer.recognize_google(audio_data)
        except sr.UnknownValueError:
            text = ""
        except Exception as e:
            print(f"Speech recognition error: {e}")
            text = ""

        # Cleanup temp files
        try:
            os.remove(in_path)
            os.remove(wav_path)
        except:
            pass

        return jsonify({"text": text})
    except Exception as e:
        print(f"/audio_to_text error: {e}")
        return jsonify({"error": "Failed to process audio"}), 500

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    Flask_port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=Flask_port, debug=False)