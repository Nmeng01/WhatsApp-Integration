from quart import Quart, request, jsonify
import httpx
import logging
from dotenv import load_dotenv
import os
import asyncio
from datetime import date
import time

app = Quart(__name__)

VERIFY_TOKEN = 'blvs123'
logging.basicConfig(
    filename='error_log.txt',  
    filemode='a',              
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)

# Verification Endpoint
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    token_sent = request.args.get('hub.verify_token')
    if token_sent == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return 'Invalid verification token', 403

# Webhook to receive messages
@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        data = await request.json
        load_dotenv()
        subdomain = os.getenv('SUBDOMAIN')
        phone = data['entry'][0]['changes'][0]['value']['messages'][0]['from']
        # Search for user
        user_url = f'https://{subdomain}.zendesk.com/api/v2/users/search.json?query={phone}'
        async with httpx.AsyncClient() as client:
            response = await client.get(user_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')))
        if response.status_code == 200:
            user_data = response.json()
            users = user_data.get('users', [])
            if users:
                requester_id = users[0]['id']
            else:
                # If user does not exist, create a new user
                user_url = f'https://{subdomain}.zendesk.com/api/v2/users.json'
                payload = {
                    "user": {
                        "phone": f'{phone}'
                    }
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(user_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')), headers={'Content-Type': 'application/json'}, json=payload)
                if response.status_code == 201:
                    user_data = response.json()
                    requester_id = user_data['user']['id']
                else:
                    logging.error('Failed to create user in Zendesk')
                    return jsonify({'error': 'Failed to create user in Zendesk'}), 500
        else:
            logging.error('Failed to search user in Zendesk')
            return jsonify({'error': 'Failed to search user in Zendesk'}), 500
        
        # Check if current ticket exists
        today = date.today()
        dst = time.localtime().tm_isdst
        if dst > 0:
            start_time = f'{today}T13:00:00Z'
            end_time = f'{today}T22:00:00Z'
        else:
            start_time = f'{today}T14:00:00Z'
            end_time = f'{today}T23:00:00Z'

        search_url = f'https://{subdomain}.zendesk.com/api/v2/search.json'
        query = f'type:ticket subject:\"{f"WhatsApp message from {phone}"}\" created>{start_time} created<{end_time}'
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params={"query": query}, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')))
        if response.status_code == 200:
            results = response.json().get('results', [])
            # If current ticket exists, update that ticket, otherwise create a new ticket
            if results:
                ticket_id = results[0]['id'] 
                ticket_url = f'https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}.json'
                payload = {
                    "ticket": {
                        "comment": {
                            "body": f"{data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']}",
                            "public": True,
                            "author_id": requester_id
                        }
                    }
                }
                async with httpx.AsyncClient() as client:
                    response = await client.put(ticket_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')), json=payload)
                if response.status_code == 200:
                    return jsonify({"status": "success", "message": "Message processed successfully"}), 200
                else:
                    logging.error(f'Failed to update ticket {ticket_id} in Zendesk')
                    return jsonify({'error': 'Failed to update ticket in Zendesk'}), 500
            else:
                ticket_url = f'https://{subdomain}.zendesk.com/api/v2/tickets'
                payload = {
                    "ticket": {
                        "requester_id": requester_id,
                        "subject": f"WhatsApp message from {phone}",
                        "comment": {
                            "body": f"{data['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']}",
                            "public": True
                        }
        
                    }
                }
        
                async with httpx.AsyncClient() as client:
                    response = await client.post(ticket_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')), headers={'Content-Type': 'application/json'}, json=payload)
                if response.status_code == 201:
                    await asyncio.sleep(10)
                    delete_id = response.json()['ticket']['id'] + 1
                    delete_url = f'https://{subdomain}.zendesk.com/api/v2/tickets/{delete_id}.json'
                    async with httpx.AsyncClient() as client:
                        response = await client.delete(delete_url, auth=(os.getenv('Z_EMAIL'), os.getenv('Z_TOKEN')))
                    if response.status_code == 204:
                        return jsonify({"status": "success", "message": "Message processed successfully"}), 200
                    else:
                        logging.error(f"Failed to delete ticket {delete_id}. Status code: {response.status_code}")
                        return jsonify({'error': 'Failed to delete ticket in Zendesk'}), 200
                else:
                    logging.error('Failed to create new ticket in Zendesk')
                    return jsonify({'error': 'Failed to create ticket in Zendesk'}), 500
        else:
            logging.error(f"Failed to search for existing ticket to update. Status code: {response.status_code}")
            return jsonify({'error': 'Failed to search for existing ticket to update.'}), 500
        
    except httpx.RequestError as e:
        logging.error(f'Request failed: {str(e)}')
        return jsonify({'error': 'Request failed'}), 500
    except Exception as e:
        logging.error(f'An unexpected error occurred: {str(e)}')
        return jsonify({'error': 'Unexpected error'}), 500

if __name__ == '__main__':
    app.run(port=5000)
