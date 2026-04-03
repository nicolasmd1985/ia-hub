import urllib.request
import json
import os

def check_gateway():
    url = "http://localhost:18789/api/v1/run"
    token = "my-local-hub-2026"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'bearer {token}'
    }
    payload = {
        "agent": "backend",
        "message": "ping",
        "json": True
    }
    
    print(f"Connecting to {url}...")
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"Status: {response.getcode()}")
            print(f"Body: {response.read().decode('utf-8')}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    check_gateway()
