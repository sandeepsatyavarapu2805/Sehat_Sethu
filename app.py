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
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"profile": {}, "appointments": [], "emergency": [], "medications": []}
    return {"profile": {}, "appointments": [], "emergency": [], "medications": []}

def save_user_data(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

user_data = load_user_data()

# Create the detailed system instruction after loading data
def create_system_instruction(user_data):
    profile_text = ""
    if user_data.get('profile'):
        profile = user_data['profile']
        profile_text = f"The user's health profile includes: Name - {profile.get('name', 'N/A')}, Age - {profile.get('age', 'N/A')}, Gender - {profile.get('gender', 'N/A')}, Blood Group - {profile.get('blood_group', 'N/A')}, Known Conditions - {profile.get('conditions', 'N/A')}."
    
    medications_text = ""
    if user_data.get('medications'):
        med_list = [f"{m['name']} ({m['dosage']}, {m['schedule']})" for m in user_data['medications']]
        medications_text = f"The user is currently taking the following medications: {', '.join(med_list)}."

    emergency_text = ""
    if user_data.get('emergency_contacts'):
        contact_list = [f"{c['name']} ({c['number']})" for c in user_data['emergency_contacts']]
        emergency_text = f"The user's emergency contacts are: {', '.join(contact_list)}."

    # A more robust and structured system instruction
    instruction = (
        "You are HealthBot, a friendly, helpful, and empathetic AI health assistant. Your main purpose is to provide **general health and wellness information**, tips, and motivation. You can discuss workout routines, nutrition, and general well-being. "
        "**Never give specific medical diagnoses, treatments, or remedies.** Always start your response with a clear and prominent disclaimer stating that you are not a medical professional. "
        "When a user asks for advice on a health issue, provide a structured, multi-point response that includes:\n"
        "1.  **A list of non-medical, at-home measures** they can take (e.g., rest, hydration, stress reduction). Use bullet points to make this information easy to read.\n"
        "2.  **A clear and explicit section on when to seek professional medical help.** Use a bold heading and a new paragraph for this section to emphasize its importance. List symptoms that require a doctor's visit using bullet points.\n"
        "3.  **A closing statement** that reiterates your purpose and offers further general assistance.\n"
        "Your responses should be conversational, empathetic, and easy to understand. "
        f"Here is some information about the user to help you personalize your responses: {profile_text} {medications_text} {emergency_text}"
    )
    return instruction

chat = model.start_chat(
    history=[
        {"role": "user", "parts": [create_system_instruction(user_data)]},
        {"role": "model", "parts": ["I understand my purpose. I'm ready to help!"]}
    ]
)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    user_input = request.json.get("message")
    
    # Reload user data to get the latest profile information
    current_user_data = load_user_data()
    system_instruction = create_system_instruction(current_user_data)
    
    try:
        # Send the user's message along with the personalized system instruction
        response = chat.send_message(f"**User:** {user_input}\n\n**HealthBot, remember your instructions:** {system_instruction}")
        bot_text = getattr(response, "text", "") or getattr(response, "last", "")

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.datetime.now()}]\nYou: {user_input}\nHealthBot: {bot_text}\n\n")

    except Exception as e:
        bot_text = f"Sorry, something went wrong: {e}"
    
    return jsonify({"reply": bot_text})

@app.route("/get_user_data", methods=["GET"])
def get_user_data():
    data = load_user_data()
    return jsonify(data)

@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = load_user_data()
    profile_data = request.json
    
    # Ensure custom fields are handled correctly
    profile_data['custom_fields'] = profile_data.get('custom_fields', [])
    
    data["profile"] = profile_data
    save_user_data(data)
    return jsonify({"status": "success", "message": "Profile saved!", "data": profile_data})

@app.route("/save_medication", methods=["POST"])
def save_medication():
    data = load_user_data()
    medication = request.json
    if "medications" not in data:
        data["medications"] = []
    data["medications"].append(medication)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Medication added!"})

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

@app.route("/delete_emergency_contact/<int:index>", methods=["DELETE"])
def delete_emergency_contact(index):
    data = load_user_data()
    if 0 <= index < len(data.get("emergency_contacts", [])):
        data["emergency_contacts"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Emergency contact not found."}), 404

@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = load_user_data()
    appointment = request.json
    if "appointments" not in data:
        data["appointments"] = []
    data["appointments"].append(appointment)
    save_user_data(data)
    return jsonify({"status": "success", "message": "Appointment added!"})

@app.route("/delete_appointment/<int:index>", methods=["DELETE"])
def delete_appointment(index):
    data = load_user_data()
    if 0 <= index < len(data.get("appointments", [])):
        data["appointments"].pop(index)
        save_user_data(data)
        return jsonify({"status": "success", "message": "Appointment deleted."})
    return jsonify({"status": "error", "message": "Appointment not found."}), 404

@app.route("/health-tips")
def health_tips():
    return render_template("health_tips.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)