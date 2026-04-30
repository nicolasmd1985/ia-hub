import os
import sys
import json
import subprocess

def load_env():
    env = {}
    ai_hub_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(ai_hub_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    env[key] = value.strip('"\' \r\n')
    return env

def run_curl(method, url, data=None, headers=None):
    cmd = ["curl", "-s", "-X", method, url]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if data:
        cmd += ["-d", json.dumps(data)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None

def create_github_issue(title, body, env):
    owner = env.get("GITHUB_USER")
    repo = env.get("GITHUB_REPO")
    token = env.get("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }
    data = {"title": title, "body": body}
    return run_curl("POST", url, data, headers)

def add_issue_to_project(issue_id, env):
    token = env.get("GITHUB_TOKEN")
    project_id = "PVT_kwHOATWBuM4BQ0Pm" # Hardcoded from mission_control.py
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 1. Add to project
    query = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item { id }
      }
    }
    """
    res = run_curl("POST", url, {"query": query, "variables": {"projectId": project_id, "contentId": issue_id}}, headers)
    if not res or "errors" in res:
        print(f"Error adding to project: {res}")
        return None
    
    item_id = res["data"]["addProjectV2ItemById"]["item"]["id"]
    
    # 2. Set Status to "To Do"
    field_id = "PVTSSF_lAHOATWBuM4BQ0Pmzg-0748"
    option_id = "f75ad846" # "To Do" option ID from mission_control.py
    
    query_status = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId,
        value: { singleSelectOptionId: $optionId }
      }) { clientMutationId }
    }
    """
    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "optionId": option_id
    }
    run_curl("POST", url, {"query": query_status, "variables": variables}, headers)
    return item_id

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 create_task.py <title> <body>")
        sys.exit(1)
    
    title = sys.argv[1]
    body = sys.argv[2]
    env = load_env()
    
    print(f"Creating issue: {title}")
    issue = create_github_issue(title, body, env)
    if issue and "node_id" in issue:
        print(f"Issue created: {issue['html_url']}")
        item_id = add_issue_to_project(issue["node_id"], env)
        if item_id:
            print(f"Successfully added to project board in 'To Do'.")
        else:
            print("Failed to add to project board.")
    else:
        print(f"Failed to create issue: {issue}")
