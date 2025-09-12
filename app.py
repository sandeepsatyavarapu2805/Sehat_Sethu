from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os, json, datetime

app = Flask(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("⚠️ GOOGLE_API_KEY is not set.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

LOG_FILE = "chat_log.txt"
USER_DATA_FILE = "user_data.json"

# Move the load and save functions to the top
# so they are defined before being called.
def load_user_data():
    # ... (Your existing code for this function)
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"profile": {}, "appointments": [], "emergency": []}
    return {"profile": {}, "appointments": [], "emergency": []}

def save_user_data(data):
    # ... (Your existing code for this function)
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

user_data = load_user_data()

# Create the detailed system instruction after loading data
user_profile_text = ""
if user_data['profile']:
    profile = user_data['profile']
    user_profile_text = f"The user's name is {profile.get('name', 'N/A')}. Their age is {profile.get('age', 'N/A')}. Their known health conditions are: {profile.get('conditions', 'N/A')}."

system_instruction = (
    # ... (Your existing system instruction text)
    "You are HealthBot, a friendly, helpful, and empathetic AI health assistant. Your main purpose is to provide general health and wellness information, tips, and motivation. You can discuss workout routines, nutrition, and general well-being. Always maintain a positive and encouraging tone. Never give specific medical diagnoses, treatments, or remedies. When a user asks for medical advice, gently remind them that you are an AI and not a substitute for a medical professional. "
    "Your responses should be conversational and easy to understand. "
    f"Here is some information about the user to help you personalize your responses: {user_profile_text}"
)

# Start the chat with the system instruction
chat = model.start_chat(
    history=[
        {"role": "user", "parts": [system_instruction]},
        {"role": "model", "parts": ["I understand my purpose. I'm ready to help!"]}
    ]
)

@app.route("/")
def home():
    # ... (Your existing code)
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    # ... (Your existing code)
    user_input = request.json.get("message")
    try:
        response = chat.send_message(user_input)
        bot_text = getattr(response, "text", "") or getattr(response, "last", "")

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.datetime.now()}]\nYou: {user_input}\nHealthBot: {bot_text}\n\n")

    except Exception as e:
        bot_text = f"Sorry, something went wrong: {e}"
    
    return jsonify({"reply": bot_text})

@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = load_user_data()
    data["profile"] = request.json
    save_user_data(data)  # This will now be correctly linked
    
    # ... (Your existing code to reset the chat context)
    global chat
    user_profile_text = ""
    if data['profile']:
        profile = data['profile']
        user_profile_text = f"The user's name is {profile.get('name', 'N/A')}. They are {profile.get('age', 'N/A')} years old. Their known health conditions are: {profile.get('conditions', 'N/A')}."
        
    system_instruction = (
        "You are HealthBot, a friendly, helpful, and empathetic AI health assistant. Your main purpose is to provide general health and wellness information, tips, and motivation. You can discuss workout routines, nutrition, and general well-being. Always maintain a positive and encouraging tone. Never give specific medical diagnoses, treatments, or remedies. When a user asks for medical advice, gently remind them that you are an AI and not a substitute for a medical professional. "
        "Your responses should be conversational and easy to understand. "
        f"Here is some information about the user to help you personalize your responses: {user_profile_text}"
    )
    
    chat = model.start_chat(
        history=[
            {"role": "user", "parts": [system_instruction]},
            {"role": "model", "parts": ["I understand my purpose. I'm ready to help!"]}
        ]
    )
    return jsonify({"status": "success", "message": "Profile saved!"})

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = load_user_data()
    appointment = request.json
    data["appointments"].append(appointment)
    save_user_data(data)  # This will now be correctly linked
    return jsonify({"status": "success", "message": "Appointment added!"})

@app.route("/save_emergency", methods=["POST"])
def save_emergency():
    data = load_user_data()
    emergency = request.json
    data["emergency"].append(emergency)
    save_user_data(data)  # This will now be correctly linked
    return jsonify({"status": "success", "message": "Emergency saved!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)