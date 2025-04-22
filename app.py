import os
import pandas as pd
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
import requests

app = Flask(__name__)

# Sample inventory (can be loaded from Excel)
inventory_file = 'inventory.xlsx'
sessions = {}

# Load inventory from Excel file
def load_inventory():
    return pd.read_excel(inventory_file)

# Groq order parser
groq_api_key = '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'
groq_model = "mixtral-8x7b-32768"

def parse_order_with_groq(order_text):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": groq_model,
        "messages": [
            {
                "role": "system",
                "content": "You are an order parser for a general store. Extract product name and quantity from user's order."
            },
            {
                "role": "user",
                "content": order_text
            }
        ],
        "temperature": 0.2
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()
    try:
        content = result["choices"][0]["message"]["content"]
        parsed = {}
        for line in content.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                parsed[key.strip().lower()] = value.strip()
        return parsed
    except Exception as e:
        print("Error parsing Groq response:", e)
        return {"product": "unknown", "quantity": 1}

# Home route
@app.route("/")
def home():
    return "<h2>👋 Welcome to Parag General Store Calling Agent Backend!</h2><p>This server is working correctly.</p>"

# Entry route: starts interaction and gathers speech
@app.route("/voice", methods=["GET", "POST"])
def voice():
    if request.method == "GET":
        return "<h1>Voice Webhook Ready</h1>"

    call_sid = request.form.get("CallSid")
    sessions[call_sid] = {"orders": []}

    response = VoiceResponse()
    gather = response.gather(input='speech', action="/take_order", speechTimeout='auto')
    gather.say("Welcome to Parag General Store. What would you like to order?", voice='Polly.Aditi')

    response.say("Sorry, I didn't catch that. Goodbye.")
    return Response(str(response), mimetype='application/xml')

# Take order
@app.route("/take_order", methods=["POST"])
def take_order():
    call_sid = request.form.get("CallSid")
    order_text = request.form.get("SpeechResult", "")
    sessions[call_sid]["last_order"] = order_text

    parsed_order = parse_order_with_groq(order_text)
    print(f"Parsed Order: {parsed_order}")

    product = parsed_order.get("product")
    quantity = int(parsed_order.get("quantity", 1))

    inventory = load_inventory()
    matched = False

    for _, row in inventory.iterrows():
        if product.lower() in row['Product'].lower():
            matched = True
            if row['Quantity'] >= quantity:
                sessions[call_sid]["orders"].append(f"{product} x{quantity}")
                response = VoiceResponse()
                response.say(f"We have {product} in stock. Shall I confirm this order?", voice='Polly.Aditi')
                response.gather(input='speech', action="/confirm_order", speechTimeout='auto')
                return Response(str(response), mimetype='application/xml')
            elif row['Quantity'] < quantity:
                response = VoiceResponse()
                response.say(f"We only have {row['Quantity']} {product}s in stock. Would you like to take them?", voice='Polly.Aditi')
                response.gather(input='speech', action="/confirm_order", speechTimeout='auto')
                return Response(str(response), mimetype='application/xml')

    if not matched:
        response = VoiceResponse()
        response.say(f"Sorry, I couldn't find {product} in our inventory. Could you please say it again?", voice='Polly.Aditi')
        response.gather(input='speech', action="/take_order", speechTimeout='auto')
        return Response(str(response), mimetype='application/xml')

# Confirm order
@app.route("/confirm_order", methods=["POST"])
def confirm_order():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "").lower()

    response = VoiceResponse()
    if 'yes' in user_input:
        response.say("Your order has been confirmed. Do you want to order something else?", voice='Polly.Aditi')
        response.gather(input='speech', action="/take_order", speechTimeout='auto')
    elif 'no' in user_input:
        order_summary = ", ".join(sessions[call_sid]["orders"])
        response.say(f"Your order: {order_summary}. Is that correct?", voice='Polly.Aditi')
        response.gather(input='speech', action="/final_confirmation", speechTimeout='auto')
    else:
        response.say("I didn't understand that. Please say yes or no.", voice='Polly.Aditi')
        response.gather(input='speech', action="/confirm_order", speechTimeout='auto')

    return Response(str(response), mimetype='application/xml')

# Final confirmation and SMS
@app.route("/final_confirmation", methods=["POST"])
def final_confirmation():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "").lower()

    response = VoiceResponse()
    if 'yes' in user_input:
        send_order_confirmation(call_sid)
        response.say("Thank you for your order. We'll process it shortly.", voice='Polly.Aditi')
    else:
        response.say("Okay, feel free to call us anytime to place your order.", voice='Polly.Aditi')

    return Response(str(response), mimetype='application/xml')

# Send SMS to store + user
def send_order_confirmation(call_sid):
    orders = ", ".join(sessions[call_sid]["orders"])
    user_name = sessions[call_sid].get("user_name", "Customer")

    message = f"Order Confirmation:\nCustomer: {user_name}\nItems: {orders}"

    client = Client()

    # Replace with actual numbers
    user_phone = "+919129823355"
    store_phone = "+917388508018"
    from_number = "+19787805377"  # Your Twilio number

    client.messages.create(body=message, from_=from_number, to=user_phone)
    client.messages.create(body=message, from_=from_number, to=store_phone)

if __name__ == "__main__":
    app.run(debug=True)
