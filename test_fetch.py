#!/usr/bin/env python3

import os
import json
import urllib.request
import subprocess

# ─── Load Environment ────────────────────────────────────────────────────────
def load_env():
    env = {}
    env_file = "/home/nicolasmd/Development/agents-developmet/ai-hub/.env"
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    env[key] = value.strip('"\' \r\n')
    return env

# ─── GitHub API Client ───────────────────────────────────────────────────────
def query_graphql(query, variables, token):
    url = "https://api.github.com/graphql"
    headers = [
        "-H", f"Authorization: bearer {token}",
        "-H", "Content-Type: application/json"
    ]
    data = json.dumps({"query": query, "variables": variables})
    cmd = ["curl", "-s", "-X", "POST"] + headers + ["-d", data, url]
    print(f"Executing: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Curl error querying GitHub: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error querying GitHub API with curl: {e}")
        return None

# ─── GraphQL Queries ──────────────────────────────────────────────────────────
GET_PROJECT_ITEMS = """
query($owner: String!, $number: Int!) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      items(first: 20) {
        nodes {
          id
          content {
            ... on Issue {
              title
              body
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2Field {
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

def fetch_todo_items():
    env = load_env()
    owner = env.get("GITHUB_USER")
    number = int(env.get("PROJECT_NUMBER", "2"))
    token = env.get("GITHUB_TOKEN")

    print(f"Querying Project #{number} for user {owner}...")
    res = query_graphql(GET_PROJECT_ITEMS, {"owner": owner, "number": number}, token)
    if not res:
        print("Empty response.")
        return

    if "errors" in res:
        print(f"GraphQL Errors: {json.dumps(res['errors'], indent=2)}")
        return

    if "data" not in res or not res["data"].get("user") or not res["data"]["user"].get("projectV2"):
        print(f"Data node structure missing or not found. Response: {json.dumps(res, indent=2)}")
        return

    project = res["data"]["user"]["projectV2"]
    nodes = project["items"]["nodes"]
    print(f"Found {len(nodes)} total items on board.")

    for node in nodes:
        content = node.get("content")
        if not content:
            continue
        
        title = content.get("title")
        status = "No Status"
        
        for fv in node.get("fieldValues", {}).get("nodes", []):
            if "name" in fv and "field" in fv and "name" in fv["field"]:
                if fv["field"]["name"].lower() == "status":
                    status = fv["name"]

        print(f"- [{status}] {title}")

if __name__ == "__main__":
    fetch_todo_items()
