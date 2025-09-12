from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os, json, datetime

app = Flask(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("⚠️ GOOGLE_API_KEY is not set.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
chat = model.start_chat()

LOG_FILE = "chat_log.txt"
USER_DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"profile": {}, "appointments": [], "emergency": []}

def save_user_data(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    user_input = request.json.get("message")
    try:
        response = chat.send_message(user_input)
        bot_text = getattr(response, "text", "") or getattr(response, "last", "")

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.datetime.now()}]\nYou: {user_input}\nHealthBot: {bot_text}\n\n")

    except Exception:
        bot_text = "Sorry, something went wrong."
    
    return jsonify({"reply": bot_text})

@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = load_user_data()
    data["profile"] = request.json
    save_user_data(data)
    return jsonify({"status": "success", "message": "Profile saved!"})

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = load_user_data()
    appointment = request.json
    data["appointments"].append(appointment)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Appointment added!"})

@app.route("/save_emergency", methods=["POST"])
def save_emergency():
    data = load_user_data()
    emergency = request.json
    data["emergency"].append(emergency)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Emergency saved!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)