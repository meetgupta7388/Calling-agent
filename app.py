import os
import pandas as pd
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client

app = Flask(__name__)

# Sample inventory (can be loaded from an Excel file)
inventory_file = 'inventory.xlsx'

# Dummy session storage for calls
sessions = {}

# Load inventory from Excel file
def load_inventory():
    return pd.read_excel(inventory_file)

# Groq order parser function
import requests

# Groq API key and model
groq_api_key = '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'
groq_model = "mixtral-8x7b-32768"  # or any supported Groq model

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
        # For now, return a dummy parsed object from text like: "Product: Biscuits, Quantity: 2"
        lines = content.strip().split("\n")
        parsed = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                parsed[key.strip().lower()] = value.strip()
        return parsed
    except Exception as e:
        print("Error parsing Groq response:", e)
        return {"product": "unknown", "quantity": 1}


# Home route to handle Twilio webhook for incoming calls
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get("CallSid")
    sessions[call_sid] = {"orders": []}

    response = VoiceResponse()
    response.say("Welcome to Parag General Store! Please tell me your name.", voice='Polly.Aditi')

    response.gather(input='speech', action="/take_name", speechTimeout='auto')
    return Response(str(response), mimetype='application/xml')

# Route to take the user's name
@app.route("/take_name", methods=["POST"])
def take_name():
    call_sid = request.form.get("CallSid")
    user_name = request.form.get("SpeechResult", "")

    # Confirm user name
    response = VoiceResponse()
    response.say(f"Hello, {user_name}. What would you like to order?", voice='Polly.Aditi')

    sessions[call_sid]["user_name"] = user_name
    response.gather(input='speech', action="/take_order", speechTimeout='auto')
    return Response(str(response), mimetype='application/xml')

# Route to take order
@app.route("/take_order", methods=["POST"])
def take_order():
    call_sid = request.form.get("CallSid")
    order_text = request.form.get("SpeechResult", "")
    sessions[call_sid]["last_order"] = order_text

    # Parse the order using Groq
    parsed_order = parse_order_with_groq(order_text)
    print(f"Parsed Order: {parsed_order}")

    # Assuming parsed_order is a list of dicts with 'product' and 'quantity'
    product = parsed_order.get("product")
    quantity = parsed_order.get("quantity", 1)

    inventory = load_inventory()
    matched = False

    # Check inventory
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
            else:
                response = VoiceResponse()
                response.say(f"Sorry, {product} is currently out of stock. It will be available soon.", voice='Polly.Aditi')
                response.say("Would you like to order something else?", voice='Polly.Aditi')
                response.gather(input='speech', action="/take_order", speechTimeout='auto')
                return Response(str(response), mimetype='application/xml')

    if not matched:
        response = VoiceResponse()
        response.say(f"Sorry, I couldn't find {product} in our inventory. Could you please say it again?", voice='Polly.Aditi')
        response.gather(input='speech', action="/take_order", speechTimeout='auto')
        return Response(str(response), mimetype='application/xml')

# Route to confirm the order
@app.route("/confirm_order", methods=["POST"])
def confirm_order():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "").lower()

    if 'yes' in user_input:
        # Proceed to next step
        response = VoiceResponse()
        response.say(f"Your order has been confirmed. Do you want to order something else?", voice='Polly.Aditi')
        response.gather(input='speech', action="/take_order", speechTimeout='auto')
        return Response(str(response), mimetype='application/xml')
    
    elif 'no' in user_input:
        # Repeat the order and confirm
        order_summary = ", ".join(sessions[call_sid]["orders"])
        response = VoiceResponse()
        response.say(f"Your order: {order_summary}. Is that correct?", voice='Polly.Aditi')
        response.gather(input='speech', action="/final_confirmation", speechTimeout='auto')
        return Response(str(response), mimetype='application/xml')

# Route to finalize confirmation
@app.route("/final_confirmation", methods=["POST"])
def final_confirmation():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "").lower()

    if 'yes' in user_input:
        # Send SMS/WhatsApp to both user and store owner
        send_order_confirmation(call_sid)
        response = VoiceResponse()
        response.say("Thank you for your order. We'll process it shortly.", voice='Polly.Aditi')
        return Response(str(response), mimetype='application/xml')
    else:
        response = VoiceResponse()
        response.say("Okay, feel free to call us anytime to place your order.", voice='Polly.Aditi')
        return Response(str(response), mimetype='application/xml')
    
@app.route("/")
def home():
    return "<h2>👋 Welcome to Parag General Store Calling Agent Backend!</h2><p>This server is working correctly.</p>"

# Function to send SMS/WhatsApp messages
def send_order_confirmation(call_sid):
    user_name = sessions[call_sid]["user_name"]
    orders = ", ".join(sessions[call_sid]["orders"])

    # Use Twilio API to send SMS/WhatsApp
    client = Client()

    # User's phone number (replace with actual)
    user_phone = "+1XXXXXXXXXX"

    # Store owner's phone number (replace with actual)
    store_phone = "+1XXXXXXXXXX"

    message = f"Order Confirmation:\nCustomer: {user_name}\nItems: {orders}"

    # Send to User
    client.messages.create(
        body=message,
        from_='+1XXXXXXX',  # Your Twilio number
        to=user_phone
    )

    # Send to Store Owner
    client.messages.create(
        body=message,
        from_='+1XXXXXXX',  # Your Twilio number
        to=store_phone
    )

if __name__ == "__main__":
    app.run(debug=True)
