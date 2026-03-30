#!/usr/bin/env python3

import os
import json
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
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return None
    except Exception as e:
        return None

# ─── GraphQL Query for Fields ───────────────────────────────────────────────
GET_PROJECT_COLUMNS = """
query($owner: String!, $number: Int!) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 20) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
        }
      }
    }
  }
}
"""

def fetch_columns():
    env = load_env()
    owner = env.get("GITHUB_USER")
    number = int(env.get("PROJECT_NUMBER", "2"))
    token = env.get("GITHUB_TOKEN")

    print(f"Fetching Details for Project #{number} layout...")
    res = query_graphql(GET_PROJECT_COLUMNS, {"owner": owner, "number": number}, token)
    if not res or "data" not in res:
        print("Failed to fetch.")
        print(json.dumps(res, indent=2))
        return

    project = res["data"]["user"]["projectV2"]
    if not project:
        print("Project node None.")
        return

    print(f"Project ID: {project['id']}")
    for field in project["fields"]["nodes"]:
        if "name" in field:
            print(f"\nField: {field['name']} ({field['id']})")
            if "options" in field:
                for opt in field["options"]:
                    print(f"  - [{opt['name']}]  ID: {opt['id']}")

if __name__ == "__main__":
    fetch_columns()
