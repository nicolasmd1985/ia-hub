#!/usr/bin/env python3

import os
import subprocess
import json
import urllib.request
import time

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
    cmd = ["curl", "--connect-timeout", "10", "--max-time", "60", "-s", "-X", "POST"] + headers + ["-d", data, url]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Curl error: {result.stderr}")
            return None
    except Exception as e:
        print(f"Exception during curl query: {e}")
        return None

# ─── Telegram Notifier ────────────────────────────────────────────────────────
def send_telegram(message):
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.com/bot{bot_token}/sendMessage"
    headers = [
        "-H", "Content-Type: application/json"
    ]
    data = json.dumps({"chat_id": chat_id, "text": message})
    cmd = ["curl", "--connect-timeout", "10", "--max-time", "30", "-s", "-X", "POST"] + headers + ["-d", data, url]
    try:
        subprocess.run(cmd, capture_output=True)
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")

# ─── GitHub Project State Manager ──────────────────────────────────────────
def move_task_column(item_id, item_title, status_name, env):
    project_id = "PVT_kwHOATWBuM4BQ0Pm"
    field_id = "PVTSSF_lAHOATWBuM4BQ0Pmzg-0748"
    
    options = {
        "Backlog": "53cd9920",
        "To Do": "f75ad846",
        "In Progress": "47fc9ee4",
        "In Review QA": "0004c560",
        "Pull request Review": "d121c55f",
        "Done": "98236657"
    }
    
    option_id = options.get(status_name)
    if not option_id:
        print(f"Option not found for {status_name}")
        return

    query = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId,
        value: { singleSelectOptionId: $optionId }
      }) {
        clientMutationId
      }
    }
    """
    
    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "optionId": option_id
    }
    
    token = env.get("GITHUB_TOKEN")
    print(f"Moving card '{item_title}' to '{status_name}'...")
    res = query_graphql(query, variables, token)
    if res and "errors" in res:
        print(f"MUTATION ERROR: {json.dumps(res['errors'])}")

def create_pull_request(issue_number, env, branch_name):
    owner = env.get("GITHUB_USER")
    repo = env.get("GITHUB_REPO")
    token = env.get("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    
    headers = [
        "-H", f"Authorization: bearer {token}",
        "-H", "Content-Type: application/json"
    ]
    data = json.dumps({
        "title": f"[{issue_number}] Agent changes for Issue Review",
        "head": branch_name,
        "base": "production",
        "body": f"This PR contains autonomous agent implementations for issue #{issue_number}."
    })
    cmd = ["curl", "--connect-timeout", "10", "--max-time", "60", "-s", "-X", "POST"] + headers + ["-d", data, url]
    try:
        subprocess.run(cmd, capture_output=True)
        print(f"Pull request created on branch {branch_name}!")
    except Exception as e:
         print(f"Error creating PR: {e}")

def close_issue(issue_number, env):
    owner = env.get("GITHUB_USER")
    repo = env.get("GITHUB_REPO")
    token = env.get("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    
    headers = [
        "-H", f"Authorization: bearer {token}",
        "-H", "Content-Type: application/json"
    ]
    data = json.dumps({"state": "closed"})
    cmd = ["curl", "--connect-timeout", "10", "--max-time", "60", "-s", "-X", "PATCH"] + headers + ["-d", data, url]
    print(f"Closing GitHub Issue #{issue_number}...")
    try:
        subprocess.run(cmd, capture_output=True)
    except Exception as e:
        print(f"Error closing issue: {e}")

def comment_on_issue(issue_number, comment_body, env):
    owner = env.get("GITHUB_USER")
    repo = env.get("GITHUB_REPO")
    token = env.get("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    
    headers = [
        "-H", f"Authorization: token {token}",
        "-H", "Content-Type: application/json"
    ]
    data = json.dumps({"body": comment_body})
    cmd = ["curl", "--connect-timeout", "10", "--max-time", "10", "-s", "-X", "POST"] + headers + ["-d", data, url]
    try:
        subprocess.run(cmd, capture_output=True)
    except Exception as e:
        print(f"Error commenting on issue: {e}")

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
              url
              number
              state
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
                  ... on ProjectV2SingleSelectField {
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

def fetch_todo_items(env):
    owner = env.get("GITHUB_USER")
    number = int(env.get("PROJECT_NUMBER", "2"))
    token = env.get("GITHUB_TOKEN")

    res = query_graphql(GET_PROJECT_ITEMS, {"owner": owner, "number": number}, token)
    if not res or "data" not in res:
        print("Failed to fetch project data.")
        return []

    project = res["data"]["user"]["projectV2"]
    if not project:
        print(f"Project #{number} not found for user {owner}")
        return []

    items = []
    for node in project["items"]["nodes"]:
        content = node.get("content")
        if not content or content.get("state") == "CLOSED":
            continue
        
        title = content.get("title")
        body = content.get("body")
        status = "Todo"  # Default
        
        for fv in node.get("fieldValues", {}).get("nodes", []):
            if "name" in fv and "field" in fv and "name" in fv["field"]:
                fieldName = fv["field"]["name"]
                fieldValue = fv["name"]
                if fieldName.lower() == "status":
                    status = fieldValue

        if status in ["To Do", "Todo"]:
            items.append({
                "id": node["id"],
                "title": title,
                "body": body,
                "url": content.get("url"),
                "number": content.get("number")
            })

    return items

# ─── Agent Actions & Fallback System ─────────────────────────────────────────
def safe_clear_locks(agent_id=None):
    """Clear OpenClaw session locks safely with a strict timeout."""
    try:
        if agent_id:
            cmd = ["docker", "exec", "openclaw-gateway",
                   "sh", "-c",
                   f"find /root/.openclaw/state/agents/{agent_id}/sessions -name '*.lock' -delete 2>/dev/null; "
                   f"find /root/.openclaw/state/agents/{agent_id}/sessions -name '*.jsonl' -delete 2>/dev/null; "
                   f"echo done"]
        else:
            cmd = ["docker", "exec", "openclaw-gateway",
                   "sh", "-c",
                   "find /root/.openclaw/state -name '*.lock' -delete 2>/dev/null; "
                   "find /root/.openclaw/state -name '*.jsonl' -delete 2>/dev/null; "
                   "echo done"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            label = f"[{agent_id}]" if agent_id else "[all]"
            print(f"🔓 Locks/sessions cleared for {label}")
        else:
            print(f"⚠️  Lock clear warning: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("⚠️  Lock clear timed out after 20s — continuing anyway.")
    except Exception as e:
        print(f"⚠️  Lock clear error: {e}")

def restart_gateway_and_cleanup():
    """Forcibly restart the gateway to kill zombie processes and clear stale state."""
    print("🚨 DEADLOCK DETECTED: Forcibly restarting openclaw-gateway...")
    send_telegram("🚨 Mission Control: Deadlock detected. Restarting OpenClaw Gateway...")
    
    subprocess.run(["docker", "restart", "openclaw-gateway"], capture_output=True)
    
    # Wait for health recovery (up to 2 minutes)
    print("⏳ Waiting for gateway to reach healthy state...")
    for i in range(60):
        res = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", "openclaw-gateway"], capture_output=True, text=True)
        if "healthy" in res.stdout:
            print(f"✅ Gateway is healthy after {i*2}s.")
            break
        time.sleep(2)
    
    time.sleep(5) # Extra buffer
    safe_clear_locks()
    print("♻️  Environment recovered.")

def get_latest_io_timestamp(agent_id):
    """Retrieve the most recent file modification timestamp in the agent's state directory."""
    cmd = ["docker", "exec", "openclaw-gateway", "sh", "-c", 
           f"find /root/.openclaw/state/agents/{agent_id} -type f -exec stat -c %Y {{}} + 2>/dev/null | sort -n | tail -1"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = res.stdout.strip()
        return float(output) if output else 0
    except:
        return 0

def trigger_agent(agent_id, message, timeout=86400):
    """Run an agent turn via a direct HTTP API call to the Gateway (bypassing the 60s CLI limit)."""
    env = load_env()
    token = env.get("OPENCLAW_GATEWAY_TOKEN", "my-local-hub-2026")
    
    # We hit the gateway via its internal service name (Docker DNS) or localhost if on host.
    # Since mission_control runs on host, we use localhost or the IP. 
    # Based on docker-compose, matches port 18789.
    url = "http://localhost:18789/api/v1/run"
    
    payload = {
        "agent": agent_id,
        "message": message,
        "json": True
    }
    
    print(f"Triggering [{agent_id.upper()}] via Direct HTTP API (Timeout: {timeout}s)...")
    
    # Initial I/O state (for the 3-hour heartbeat watcher)
    last_io_time = time.time()
    last_io_timestamp = get_latest_io_timestamp(agent_id)
    progress_detected = False
    
    # We use a long-lived HTTP request. 
    # The heartbeat monitor runs in parallel in the loop below.
    # Because urllib.request.urlopen is blocking, we use a small trick: 
    # we don't need Popen if we are just waiting for the final result, 
    # BUT we still want to monitor I/O progress during the wait!
    # To do this safely, we will use a separate thread or just a reasonable timeout in the request?
    # Python's urlopen timeout is for the WHOLE request if it's not streaming.
    
    import threading
    result_container = {"data": None, "error": None}
    
    def perform_request():
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'))
            req.add_header('Content-Type', 'application/json')
            req.add_header('Authorization', f'bearer {token}')
            
            # The actual network timeout is set extremely high.
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result_container["data"] = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            result_container["error"] = str(e)
            
    req_thread = threading.Thread(target=perform_request)
    req_thread.start()
    
    start_time = time.time()
    io_deadlock_threshold = 10800 # 3 hours of silence = deadlock
    
    try:
        while req_thread.is_alive():
            current_time = time.time()
            if current_time - start_time > timeout:
                print(f"🛑 STRIKE 1: Absolute timeout of {timeout}s reached.")
                return None
            
            # Heartbeat check for progress (files being written by the agent)
            current_io_timestamp = get_latest_io_timestamp(agent_id)
            if current_io_timestamp > last_io_timestamp:
                progress_detected = True
                last_io_timestamp = current_io_timestamp
                last_io_time = current_time
                elapsed = int(current_time - start_time)
                print(f"💓 [{agent_id.upper()}] Heartbeat: Active progress detected ({elapsed}s elapsed)")
            else:
                quiet_duration = int(current_time - last_io_time)
                if quiet_duration >= io_deadlock_threshold:
                    print(f"💀 DEADLOCK: Agent {agent_id} has been silent for {quiet_duration}s.")
                    restart_gateway_and_cleanup()
                    return None
            
            time.sleep(20) # Check every 20s
            
        # Once finished
        if result_container["error"]:
            print(f"Error triggering {agent_id} via API: {result_container['error']}")
            # Detect implicit 60s timeout from host/proxy if still occurring
            if "timeout" in result_container["error"].lower():
                 print(f"⚠️  HTTP Timeout detected at {int(time.time() - start_time)}s")
            return None
            
        parsed = result_container["data"]
        if parsed and "result" in parsed:
            text = ""
            try:
                text = parsed.get("result", {}).get("payloads", [{}])[0].get("text", "")
            except: pass
            
            aborted = False
            try:
                aborted = parsed.get("result", {}).get("meta", {}).get("aborted", False)
            except: pass
            
            return {"response": text, "raw": parsed, "aborted": aborted, "progress_detected": progress_detected}
            
        return None

    except Exception as e:
        print(f"Exception during agent trigger: {e}")
        return None

    except Exception as e:
        print(f"Exception triggering agent: {e}")
        if process.poll() is None:
            process.kill()
        return None

def handle_failure(item, env, reason):
    print(f"❌ FALLBACK TRIGGERED: {reason}")
    send_telegram(f"❌ Task '{item['title']}' failed and was moved to Backlog.\nReason: {reason}")
    
    issue_num = item.get("number")
    if issue_num:
        comment_on_issue(issue_num, f"🤖 **Mission Control Update**:\nMoving back to **Backlog**.\n\n**Reason for Failure:**\n> {reason}", env)
    
    project_path = env.get("PROJECT_PATH")
    if project_path and os.path.exists(project_path):
        # Discard modifications, reset git state and checkout production branch
        print("Reverting Git workspace due to failure...")
        subprocess.run(["git", "-C", project_path, "reset", "--hard", "HEAD"], capture_output=True)
        subprocess.run(["git", "-C", project_path, "clean", "-fd"], capture_output=True)
        subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)

    move_task_column(item['id'], item['title'], "Backlog", env)
    
def handle_retry(item, env, reason, cur_branch=None):
    print(f"⚠️ RETRY TRIGGERED: {reason}")
    send_telegram(f"♻️ Task '{item['title']}' failed execution but will be retried.\nReason: {reason}")
    
    issue_num = item.get("number")
    if issue_num:
        comment_on_issue(issue_num, f"🤖 **Mission Control Update**:\nAgent execution failed. Moving back to **To Do** for an automatic retry.\n\n**Reason:**\n> {reason}", env)
    
    project_path = env.get("PROJECT_PATH")
    if project_path and os.path.exists(project_path):
        print("Reverting Git workspace due to retry...")
        subprocess.run(["git", "-C", project_path, "reset", "--hard", "HEAD"], capture_output=True)
        subprocess.run(["git", "-C", project_path, "clean", "-fd"], capture_output=True)
        subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)
        if cur_branch:
            subprocess.run(["git", "-C", project_path, "branch", "-D", cur_branch], capture_output=True)

    move_task_column(item['id'], item['title'], "To Do", env)

def check_or_clone_repo(env):
    project_name = env.get("PROJECT_NAME")
    if not project_name:
        print("PROJECT_NAME not provided in .env. Skipping auto-clone.")
        return env

    base_dir = "/home/nicolasmd/Development/agents-developmet"
    project_path = f"{base_dir}/{project_name}"
    env["PROJECT_PATH"] = project_path
    
    owner = env.get("GITHUB_USER")
    repo = env.get("GITHUB_REPO", project_name)
    token = env.get("GITHUB_TOKEN")

    if not os.path.exists(project_path) or not os.path.exists(os.path.join(project_path, ".git")):
        print(f"Repository not found at {project_path}. Cloning automatically...")
        clone_url = f"https://{token}@github.com/{owner}/{repo}.git"
        subprocess.run(["git", "clone", clone_url, project_path], capture_output=True)
        print("Clone complete.")
    
    # Configure git to use token for seamless pushing
    subprocess.run(["git", "-C", project_path, "remote", "set-url", "origin", f"https://{token}@github.com/{owner}/{repo}.git"], capture_output=True)
    return env

# ─── Main Orchestrator Loop ──────────────────────────────────────────────────
def poll_and_process(env):
    env = check_or_clone_repo(env)
    
    # Safe startup lock cleanup (with timeout so it never hangs)
    safe_clear_locks()

    project_path = env.get("PROJECT_PATH")
    items = fetch_todo_items(env)
    
    if not items:
        return

    print(f"\n=> Found {len(items)} task(s) in 'To Do'.")

    for item in items:
        try:
            print(f"\n🚀 Processing Task: {item['title']}")
            send_telegram(f"🚀 Mission Control: Starting processing for task '{item['title']}'")
            move_task_column(item['id'], item['title'], "In Progress", env)
            
            # Prepare clean branch workspace
            cur_branch = f"agent-{item.get('number', 'task')}"
            if project_path and os.path.exists(project_path):
                # Ensure we start from clean production branch
                subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)
                subprocess.run(["git", "-C", project_path, "pull", "origin", "production"], capture_output=True)
                
                print(f"Checking out clean working branch '{cur_branch}'...")
                subprocess.run(["git", "-C", project_path, "checkout", "-B", cur_branch], capture_output=True)
            else:
                handle_failure(item, env, "LOCAL REPOSITORY MISSING: Cannot proceed without access to PROJECT_PATH codebase.")
                continue

            # Auto-route using title tags to save CPU time
            assigned_agent = None
            if "BACKEND" in item['title'].upper():
                assigned_agent = "backend"
                print("Auto-routing to BACKEND based on title tag.")
            elif "FRONTEND" in item['title'].upper():
                assigned_agent = "frontend"
                print("Auto-routing to FRONTEND based on title tag.")

            if not assigned_agent:
                # 1. Trigger Architect for Planning (Timeout increased for CPU)
                print("Clearing stale session locks for [architect]...")
                safe_clear_locks("architect")
                prompt_architect = f"Task Title: {item['title']}\nDescription: {item['body']}\n\nYou must analyze the task to decide the required developer role.\nReply STRICTLY with exactly ONE WORD: 'BACKEND', 'FRONTEND', or 'ERROR'.\nIf the task is unclear, missing details, or cannot be routed, reply 'ERROR'."
                
                res = trigger_agent("architect", prompt_architect, timeout=3600)
                if not res:
                    handle_retry(item, env, "ARCHITECT FAILURE: Agent timed out or failed to execute gracefully.", cur_branch)
                    continue
                    
                response_text = res.get("response", "").strip().upper()
                print(f"Architect Response: {response_text}")
                
                if "ERROR" in response_text or ("BACKEND" not in response_text and "FRONTEND" not in response_text):
                    handle_retry(item, env, f"ARCHITECT ROUTING ERROR: Unable to parse role or task unclear. Response: '{response_text}'", cur_branch)
                    continue

                assigned_agent = "backend" if "BACKEND" in response_text else "frontend"

            # 2. Dispatch Work to Dev Agent
            print(f"Claiming task with {assigned_agent.upper()} agent...")
            work_prompt = (
                f"Task Title: {item['title']}\n"
                f"Description: {item['body']}\n\n"
                "IMPORTANT INSTRUCTIONS — READ CAREFULLY:\n"
                "1. You MUST use your 'write' or 'edit' file tools to create or modify actual files in the repository workspace.\n"
                "2. Do NOT just describe what you would do. Actually do it by calling your file tools.\n"
                "3. If the task requires creating spec/test files, factories, or source code — write every file using your 'write' tool.\n"
                "4. After writing all files, reply with a brief summary listing each file you created or modified and why.\n"
                "5. NEVER respond with only a plan or description — only a response that includes real file writes counts as success.\n"
                "6. When finished writing all files, also use your 'write' tool to save a file called AGENT_REPORT.md "
                "at the root of the workspace with a markdown summary of all the changes you made."
            )
            
            # --- Sync Host Source Code into Container Workspace ---
            container_ws = f"/root/.openclaw/workspaces/{assigned_agent}"
            print(f"Syncing code files into container workspace {container_ws}...")
            
            # Backup agent prompts (SYSTEM.md, etc.) before wiping the workspace
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"mkdir -p /tmp/oc_backup && cp {container_ws}/*.md {container_ws}/*.json /tmp/oc_backup/ 2>/dev/null || true"], capture_output=True)
            
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"rm -rf {container_ws}/*"], capture_output=True)
            subprocess.run(["docker", "cp", f"{project_path}/.", f"openclaw-gateway:{container_ws}/"], capture_output=True)

            # Prevent OpenClaw from freezing its indexer by trying to AI-scan thousands of binary/library files
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", 
                            f"rm -rf {container_ws}/.git {container_ws}/node_modules {container_ws}/tmp {container_ws}/log {container_ws}/vendor {container_ws}/public"], 
                           capture_output=True)

            # Restore agent prompts
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"cp /tmp/oc_backup/*.md /tmp/oc_backup/*.json {container_ws}/ 2>/dev/null || true"], capture_output=True)

            # Clear any stale session locks for this agent BEFORE triggering
            print(f"Clearing stale session locks for [{assigned_agent}]...")
            safe_clear_locks(assigned_agent)

            work_res = trigger_agent(assigned_agent, work_prompt, timeout=3600)
            if not work_res:
                handle_retry(item, env, f"{assigned_agent.upper()} DEV FAILURE: Agent returned None (process error).", cur_branch)
                continue
            
            # ── Strict Abort/Timeout Interception ────────────────────────
            # If OpenClaw internally timed out (60s default or any other),
            # do NOT proceed to QA. Intercept immediately and retry.
            # EXCEPTION: If we detected I/O progress (files written), we SALVAGE the work.
            if work_res.get("aborted") and not work_res.get("progress_detected"):
                duration_ms = work_res.get("raw", {}).get("result", {}).get("meta", {}).get("durationMs", "?")
                reason = (
                    f"{assigned_agent.upper()} DEV TIMEOUT: OpenClaw agent was aborted internally "
                    f"(durationMs={duration_ms}). This is usually caused by the gateway's "
                    f"agents.defaults.timeoutSeconds being too low or config being rejected. "
                    f"The agent did NOT produce valid output. Retrying."
                )
                handle_retry(item, env, reason, cur_branch)
                continue
            
            if work_res.get("aborted") and work_res.get("progress_detected"):
                print(f"⚠️  {assigned_agent.upper()} ABORTED but files were written. Salvaging partial work...")
            
            work_response_text = work_res.get("response", "").strip()
            print(f"Dev Agent Response: {work_response_text}")
            
            # Secondary validation: check response content for timeout signatures
            # even if aborted flag was somehow missed
            TIMEOUT_STRINGS = ["request timed out", "timed out before a response", "increase `agents.defaults"]
            response_lower = work_response_text.lower()
            is_timeout_text = any(sig in response_lower for sig in TIMEOUT_STRINGS)
            
            is_valid_report = (len(work_response_text.strip()) > 50 and not is_timeout_text)
            if work_res.get("progress_detected"):
                 # Override validation: if files were written, the work is salvageable despite the gateway timeout message
                 is_valid_report = True
            
            if len(work_response_text.strip()) <= 50 and "ERROR:" in work_response_text.upper() and not work_res.get("progress_detected"):
                 is_valid_report = False
            
            if not is_valid_report:
                print(f"❌ DEV REJECTION: {work_response_text}")
                send_telegram(f"♻️ Task '{item['title']}' failed DEV execution. Moving back to 'To Do' for a retry.\nReason: {work_response_text}")
                
                if item.get("number"):
                    comment_on_issue(item.get("number"), f"🤖 **Dev Agent Execution Failed:**\n\nYou must fix context errors and try again:\n\n> {work_response_text}", env)
                
                print("⚠️ [RESILIENCE] Skipping Git workspace reset due to Dev failure (preserving partial work).")
                # subprocess.run(["git", "-C", project_path, "reset", "--hard", "HEAD"], capture_output=True)
                # subprocess.run(["git", "-C", project_path, "clean", "-fd"], capture_output=True)
                # subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)
                # subprocess.run(["git", "-C", project_path, "branch", "-D", cur_branch], capture_output=True)
                
                move_task_column(item['id'], item['title'], "To Do", env)
                continue
                
            # --- Sync Container Updates back to Host ---
            print("Syncing modifications back from container to host...")
            container_ws = f"/root/.openclaw/workspaces/{assigned_agent}"
            subprocess.run(["docker", "cp", f"openclaw-gateway:{container_ws}/.", f"{project_path}/"], capture_output=True)

            print(f"✅ {assigned_agent.upper()} turn complete.")
            
            # --- 3. Save Persistent Report on Host ---
            import datetime
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            report_dir = os.path.join(project_path, "agent-report", date_str)
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "agent_report.md")
            
            # Extract from Container Sandbox
            sandbox_path = f"/root/.openclaw/workspaces/{assigned_agent}/AGENT_REPORT.md"
            cat_result = subprocess.run(["docker", "exec", "openclaw-gateway", "cat", sandbox_path], capture_output=True, text=True)
            report_content = cat_result.stdout.strip() if cat_result.returncode == 0 else ""
            
            if not report_content:
                report_content = work_response_text # fallback
                
            write_success = False
            if report_content:
                with open(report_path, "w") as f:
                    f.write(report_content)
                print(f"📄 Report saved persistently on host at: {report_path}")
                write_success = True
                comment_on_issue(item.get("number"), f"🤖 **{assigned_agent.upper()} Agent Report & Analysis**:\n\n{report_content}", env)

            subprocess.run(["git", "-C", project_path, "add", "."], capture_output=True)
            # Only commit if changes were actually made
            git_status = subprocess.run(["git", "-C", project_path, "status", "--porcelain"], capture_output=True, text=True)
            has_changes = bool(git_status.stdout.strip())
            
            if has_changes:
                subprocess.run(["git", "-C", project_path, "commit", "-m", f"[{assigned_agent.upper()}] Implemented changes for: {item['title']}"], capture_output=True)
            
            # Determine if we should bypass QA Agent step (Audit Report mode)
            # Audit mode = ONLY the AGENT_REPORT.md or agent-report/ directory changed.
            # If the agent created/modified spec/, app/, db/, config/, or any real source files -> NOT audit mode.
            REAL_CODE_DIRS = ("spec/", "app/", "db/", "config/", "lib/", "test/")
            is_audit_mode = True
            lines = git_status.stdout.strip().split("\n")
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Get the file path part (after the 2-char git status prefix)
                file_path = stripped[3:] if len(stripped) > 3 else stripped
                is_report_only = (
                    "agent-report" in file_path
                    or "AGENT_REPORT" in file_path.upper()
                )
                is_real_code = any(file_path.startswith(d) for d in REAL_CODE_DIRS)
                if is_real_code or (not is_report_only):
                    is_audit_mode = False  # Actual source/spec files were touched!
                    break

            if is_audit_mode:
                # ── Hallucination guard ──────────────────────────────────────────
                # Small models (qwen2.5:1.5b) often CLAIM to write files in their
                # text response without actually calling the write tool.
                # If the task body implies code/spec files were expected but the
                # agent only produced a report, treat this as a DEV FAILURE.
                CODE_TASK_KEYWORDS = [
                    "create spec/", "spec/factories", "spec/models", "spec/graphql",
                    "spec/requests", "spec/controllers", "write test", "write spec",
                    "create migration", "create file", "add model", "write rspec",
                    "create app/", "add route", "create controller", "create service",
                ]
                task_body_lower = (item.get("body") or "").lower()
                task_implies_code = any(kw in task_body_lower for kw in CODE_TASK_KEYWORDS)

                if task_implies_code:
                    reason = (
                        "AGENT HALLUCINATION: Task required creating code/spec files but the agent "
                        "only produced a text report — it claimed to use the write tool but never did. "
                        "Sending back to 'To Do' for a retry."
                    )
                    print(f"⚠️  {reason}")
                    send_telegram(f"♻️ Task '{item['title']}' failed: agent hallucinated file writes. Retrying.")
                    if item.get("number"):
                        comment_on_issue(item.get("number"),
                            f"🤖 **Agent Execution Warning:**\n\nThe agent described creating files but "
                            f"did not actually write them to disk. Moving back to **To Do** for a retry.\n\n"
                            f"> {work_response_text[:500]}", env)
                    print("⚠️ [RESILIENCE] Skipping Git workspace reset due to Hallucination guard (preserving partial work).")
                    # subprocess.run(["git", "-C", project_path, "reset", "--hard", "HEAD"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "clean", "-fd"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "branch", "-D", cur_branch], capture_output=True)
                    move_task_column(item['id'], item['title'], "To Do", env)
                    continue

                # Genuine audit task (only a report was expected)
                print("📋 No code modifications made (Audit mode confirmed). Bypassing QA Turn.")
                move_task_column(item['id'], item['title'], "Pull request Review", env)
                if has_changes:
                    subprocess.run(["git", "-C", project_path, "push", "-f", "origin", cur_branch], capture_output=True)
                    create_pull_request(item.get("number"), env, cur_branch)
                send_telegram(f"🎉 SUCCESS: Audit Report drafted for issue #{item.get('number')}. Ready at 'Pull Request Review'.")
                continue

            print("✅ Code touch detected. Moving to QA verification workflow.")
            send_telegram(f"✅ {assigned_agent.upper()} implemented turn for '{item['title']}'. Reviewing in QA.")
            move_task_column(item['id'], item['title'], "In Review QA", env)

            # 4. Trigger QA turn
            print("Clearing stale session locks for [qa]...")
            safe_clear_locks("qa")
            # Clear stale QA log to prevent false successes from previous turns
            qa_log_path = os.path.join(project_path, "qa_heartbeat.log")
            if os.path.exists(qa_log_path): os.remove(qa_log_path)
            # Build a list of actual files the backend agent changed so QA can review them specifically
            changed_files = []
            for line in git_status.stdout.strip().split("\n"):
                stripped = line.strip()
                if stripped and len(stripped) > 3:
                    changed_files.append(stripped[3:])
            changed_files_str = "\n".join(f"  - {f}" for f in changed_files) if changed_files else "  (no files detected)"

            qa_prompt = (
                f"Task Title: {item['title']}\n"
                f"Description: {item['body']}\n\n"
                "QA TEST EXECUTION INSTRUCTIONS:\n"
                "The backend developer has finished implementing. The following code files were modified:\n"
                f"{changed_files_str}\n\n"
                "Your job is to ACTUALLY RUN THE TEST SUITE to verify the code genuinely works!\n"
                "1. Use your 'exec' tool to run this exact command: `docker exec ordenapp_web_container bundle exec rspec | tee /root/project/qa_heartbeat.log`\n"
                "   (This ensures the results are saved even if the connection times out).\n"
                "2. Wait for the test result output from your exec tool.\n"
                "3. If the test passes (0 failures, mostly green), reply STRICTLY with the single word: SUCCESS\n"
                "4. If the test fails or hits a compiler/syntax error, reply with: ERROR: [paste the exact ruby failure trace here so the Dev can fix it]\n"
                "5. You MUST use your exec tool before replying. NEVER guess!"
            )

            qa_res = trigger_agent("qa", qa_prompt, timeout=3600)
            if not qa_res:
                handle_retry(item, env, "QA FAILURE: Agent returned None (process error).", cur_branch)
                continue
            
            # ── QA Abort/Timeout Interception ────────────────────────────
            if qa_res.get("aborted"):
                qa_duration = qa_res.get("raw", {}).get("result", {}).get("meta", {}).get("durationMs", "?")
                
                # FINAL RESILIENCE CHECK: Look for the heartbeat log on the host
                qa_log_path = os.path.join(project_path, "qa_heartbeat.log")
                if os.path.exists(qa_log_path):
                    with open(qa_log_path, 'r') as f:
                        log_content = f.read()
                        if "0 failures" in log_content and "passed" in log_content.lower():
                            print("⚠️  QA ABORTED but Heartbeat log shows SUCCESS. Salvaging QA result...")
                            qa_response_text = "SUCCESS (Salvagued from heartbeat log)"
                        else:
                            print(f"⚠️  QA ABORTED and log shows failures or is incomplete. Failing.")
                            handle_retry(item, env, f"QA TIMEOUT/FAILURE: {qa_duration}ms. Log: {log_content[-100:]}", cur_branch)
                            continue
                else:
                    handle_retry(item, env,
                        f"QA TIMEOUT: OpenClaw QA agent was aborted internally "
                        f"(durationMs={qa_duration}). No heartbeat log found. Retrying.", cur_branch)
                    continue
            else:
                qa_response_text = qa_res.get("response", "").strip()
            print(f"QA Response: {qa_response_text}")
            
            if "SUCCESS" not in qa_response_text.upper() or "ERROR" in qa_response_text.upper():
                print(f"❌ QA REJECTION: {qa_response_text}")
                send_telegram(f"♻️ Task '{item['title']}' failed QA. Moving back to 'To Do' for a retry.\nReason: {qa_response_text}")
                
                if item.get("number"):
                    comment_on_issue(item.get("number"), f"🤖 **QA Rejected Previous Attempt:**\n\nYou must fix the errors identified below and try again:\n\n> {qa_response_text}", env)
                
                if not qa_res.get("aborted"):
                    print("⚠️ [RESILIENCE] Skipping Git workspace reset due to QA rejection (preserving partial work).")
                    # subprocess.run(["git", "-C", project_path, "reset", "--hard", "HEAD"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "clean", "-fd"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)
                    # subprocess.run(["git", "-C", project_path, "branch", "-D", cur_branch], capture_output=True)
                else:
                    print("QA TIMEOUT: Preserving workspace (Backend work salvaged). Moving back to To Do for retry.")
                
                move_task_column(item['id'], item['title'], "To Do", env)
                continue

            # 5. Success Finalization
            move_task_column(item['id'], item['title'], "Pull request Review", env)
            print(f"Pushing isolate branch {cur_branch} to GitHub...")
            # Use --force in case the agent rewrites and PR existed previously, but handle safely
            subprocess.run(["git", "-C", project_path, "push", "-f", "origin", cur_branch], capture_output=True)
            
            create_pull_request(item.get("number"), env, cur_branch)
            send_telegram(f"🎉 SUCCESS: QA Passed for issue #{item.get('number')}. PR ready for manual review at 'Pull Request Review'.")
            
            issue_number = item.get("number")
            if issue_number:
                # Deliberately leaving the GitHub issue Open. User reviews in 'Pull request Review' column and moves to Done manually!
                print(f"Task #{issue_number} completed. Waiting on manual PR review to close.")
                
            # Checkout production again to leave workspace clean for next run
            subprocess.run(["git", "-C", project_path, "checkout", "production"], capture_output=True)

        except Exception as e:
            handle_failure(item, env, f"SYSTEM EXCEPTION in workflow processing: {str(e)}")

def orchestrate():
    env = load_env()
    if not env.get("GITHUB_TOKEN"):
        print("GITHUB_TOKEN not found in .env. Exiting.")
        return

    print("==============================================")
    print("🚀 Mission Control active.")
    print("🔁 Entering continuous Kanban polling loop...")
    print("==============================================")
    
    while True:
        try:
            poll_and_process(env)
        except Exception as e:
            print(f"Critical error in polling loop: {e}")
        time.sleep(15)  # Constantly poll every 15 seconds safely

if __name__ == "__main__":
    orchestrate()
