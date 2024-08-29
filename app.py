from flask import Flask, request
import requests
import json
from dotenv import load_dotenv
import os

app = Flask(__name__)

VERIFY_TOKEN = 'blvs123'

# Verification Endpoint
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    token_sent = request.args.get('hub.verify_token')
    if token_sent == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return 'Invalid verification token', 403

# Webhook to receive messages
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    load_dotenv()
    subdomain = os.getenv('SUBDOMAIN')
    phone = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
    user_url = f'https://{subdomain}.zendesk.com/api/v2/users/search.json?query={phone}'
    response = requests.get(user_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')))
    if response.status_code == 200:
        user_data = response.json()
        users = user_data.get('users', [])
        if users:
            requester_id = users[0]['id']
        else:
            user_url = f'https://{subdomain}.zendesk.com/api/v2/users.json'
            payload = {
                "user": {
                    "phone": f'{phone}'
                }
            }
            response = requests.post(user_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')), headers={'Content-Type': 'application/json'}, json=payload)
            user_data = response.json()
            requester_id = user_data['user']['id']
    else:
        print('Something wrong with the query for users')

    ticket_url = f'https://{subdomain}.zendesk.com/api/v2/tickets'
    payload = {
        "ticket": {
            "requester_id": requester_id,
            "subject": f"WhatsApp message from {phone}",
            "comment": {
                "body": f"{data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']}"
            }
            
        }
    }

    response = requests.request("POST", ticket_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')), headers={'Content-Type': 'application/json'}, json=payload)

    print("Webhook received:", data)
    # print("Posted to Zendesk", response.status_code)
    return 'Webhook received', 200

if __name__ == '__main__':
    app.run(port=5000)
