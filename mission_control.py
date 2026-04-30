# 🛸 MISSION CONTROL HEARTBEAT: Re-launched v42.
import os
import subprocess
import json
import urllib.request
import time
import sys
import threading
import builtins
import sqlite3
import fcntl

def print(*args, **kwargs):
    """Override print to always flush, ensuring logs are visible in real-time."""
    kwargs.setdefault('flush', True)
    builtins.print(*args, **kwargs)

print("==============================================")
print("==============================================")

# ─── Global State (SQLite) ───────────────────────────────────────────────────
STATE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mission_state.db")

def ensure_tables():
    """Ensure all required SQLite tables exist. Called before processing to prevent 'no such table' errors."""
    conn = sqlite3.connect(STATE_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS state 
                    (task_id TEXT, counter_type TEXT, attempts INTEGER, 
                     PRIMARY KEY(task_id, counter_type))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS qa_cycles
                    (task_id TEXT, cycle_num INTEGER,
                     total_examples INTEGER, failures INTEGER, errors INTEGER,
                     error_score INTEGER, pass_rate REAL,
                     timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                     PRIMARY KEY(task_id, cycle_num))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS feedback 
                    (task_id TEXT PRIMARY KEY, content TEXT)''')
    conn.commit()
    conn.close()

ensure_tables()

def get_state_counter(task_id, counter_type):
    conn = sqlite3.connect(STATE_DB)
    row = conn.execute("SELECT attempts FROM state WHERE task_id=? AND counter_type=?", (str(task_id), counter_type)).fetchone()
    conn.close()
    return row[0] if row else 0

def increment_state_counter(task_id, counter_type):
    conn = sqlite3.connect(STATE_DB)
    conn.execute('''INSERT INTO state(task_id, counter_type, attempts) 
                    VALUES(?,?,1) 
                    ON CONFLICT(task_id, counter_type) DO UPDATE SET attempts=attempts+1''',
                 (str(task_id), counter_type))
    conn.commit()
    conn.close()
    return get_state_counter(task_id, counter_type)

MAX_HALLUCINATION_RETRIES = 3
MAX_QA_HARD_CEILING = 8  # Absolute maximum QA↔Backend cycles (safety net)

# ─── Convergence Tracking DB ─────────────────────────────────────────────────

def record_qa_cycle(task_id, total_examples, failures, errors):
    """Record QA cycle metrics and return the current cycle number."""
    conn = sqlite3.connect(STATE_DB)
    row = conn.execute("SELECT MAX(cycle_num) FROM qa_cycles WHERE task_id=?", (str(task_id),)).fetchone()
    cycle_num = (row[0] or 0) + 1
    error_score = failures + errors
    pass_rate = ((total_examples - failures) / total_examples) if total_examples > 0 else 0.0
    conn.execute(
        "INSERT INTO qa_cycles(task_id, cycle_num, total_examples, failures, errors, error_score, pass_rate) VALUES(?,?,?,?,?,?,?)",
        (str(task_id), cycle_num, total_examples, failures, errors, error_score, pass_rate)
    )
    conn.commit()
    conn.close()
    return cycle_num

def evaluate_convergence(task_id):
    """Analyze QA cycle trend using monotone convergence (early stopping).
    
    Algorithm:
    - Track error_score (failures + errors) over cycles
    - If decreasing → IMPROVING → continue
    - If stagnant for 2+ cycles → STAGNANT → stop
    - If increasing → REGRESSING → stop
    - Hard ceiling at MAX_QA_HARD_CEILING (safety net)
    
    Returns (should_continue: bool, reason: str, cycle_num: int, metrics: dict)
    """
    conn = sqlite3.connect(STATE_DB)
    rows = conn.execute(
        "SELECT cycle_num, error_score, pass_rate, total_examples, failures FROM qa_cycles WHERE task_id=? ORDER BY cycle_num",
        (str(task_id),)
    ).fetchall()
    conn.close()
    
    if not rows:
        return True, "First cycle", 0, {}
    
    cycle_num = rows[-1][0]
    latest_score = rows[-1][1]
    latest_rate = rows[-1][2]
    latest_examples = rows[-1][3]
    latest_failures = rows[-1][4]
    
    metrics = {
        'cycle': cycle_num,
        'error_score': latest_score,
        'pass_rate': latest_rate,
        'total_examples': latest_examples,
        'failures': latest_failures,
        'trend': [r[1] for r in rows]
    }
    
    # SUCCESS: All tests pass
    if latest_score == 0 and latest_examples > 0:
        return False, "ALL_TESTS_PASS", cycle_num, metrics
    
    # HARD CEILING
    if cycle_num >= MAX_QA_HARD_CEILING:
        return False, f"HARD_CEILING ({MAX_QA_HARD_CEILING} cycles)", cycle_num, metrics
    
    # Need at least 2 data points for trend analysis
    if len(rows) < 2:
        return True, f"FIRST_DATAPOINT (error_score={latest_score})", cycle_num, metrics
    
    # Calculate deltas
    scores = [r[1] for r in rows]
    delta = scores[-1] - scores[-2]
    
    if delta < 0:
        improvement = scores[-2] - scores[-1]
        return True, f"IMPROVING (Δ=-{improvement}, error_score: {scores[-2]}→{scores[-1]})", cycle_num, metrics
    
    if delta > 0:
        regression = scores[-1] - scores[-2]
        return False, f"REGRESSING (Δ=+{regression}, error_score: {scores[-2]}→{scores[-1]})", cycle_num, metrics
    
    # delta == 0 → stagnation
    stagnant_count = 0
    for i in range(len(scores) - 1, 0, -1):
        if scores[i] == scores[i-1]:
            stagnant_count += 1
        else:
            break
    
    if stagnant_count >= 2:
        return False, f"STAGNANT ({stagnant_count} cycles at error_score={latest_score})", cycle_num, metrics
    
    return True, f"MONITORING (stagnant {stagnant_count} cycle(s), error_score={latest_score})", cycle_num, metrics

def save_feedback(task_id, feedback):
    conn = sqlite3.connect(STATE_DB)
    conn.execute('''INSERT INTO feedback(task_id, content) VALUES(?,?) 
                    ON CONFLICT(task_id) DO UPDATE SET content=excluded.content''', (str(task_id), feedback))
    conn.commit()
    conn.close()

def get_feedback(task_id):
    conn = sqlite3.connect(STATE_DB)
    try:
        row = conn.execute("SELECT content FROM feedback WHERE task_id=?", (str(task_id),)).fetchone()
        return row[0] if row else ""
    except sqlite3.OperationalError:
        return ""
    finally:
        conn.close()

def clear_feedback(task_id):
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute("DELETE FROM feedback WHERE task_id=?", (str(task_id),))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

# ─── RSpec Output Parser ─────────────────────────────────────────────────────
import re as _re

def parse_rspec_result(output_text):
    """Parse RSpec output to extract pass/fail status and counts."""
    result = {
        'passed': False, 'examples': 0, 'failures': 0, 'errors': 0,
        'raw_summary': '', 'has_evidence': False
    }
    
    summary_match = _re.search(r'(\d+)\s+examples?,\s+(\d+)\s+failures?', output_text)
    if summary_match:
        result['examples'] = int(summary_match.group(1))
        result['failures'] = int(summary_match.group(2))
        result['raw_summary'] = summary_match.group(0)
        result['has_evidence'] = True
        result['passed'] = result['failures'] == 0 and result['examples'] > 0
    
    error_match = _re.search(r'(\d+)\s+errors?\s+occurred', output_text)
    if error_match:
        result['errors'] = int(error_match.group(1))
        result['has_evidence'] = True
        result['passed'] = False
    
    return result

def extract_schema_for_model(project_path, model_name):
    """Extract the CREATE TABLE definition from db/schema.rb for a given model."""
    schema_path = os.path.join(project_path, "db", "schema.rb")
    if not os.path.exists(schema_path):
        return ""
    with open(schema_path, 'r') as f:
        content = f.read()
    # CamelCase → snake_case pluralized
    table_name = _re.sub(r'(?<!^)(?=[A-Z])', '_', model_name).lower() + 's'
    pattern = rf'(create_table "{table_name}".*?end)'
    match = _re.search(pattern, content, _re.DOTALL)
    return match.group(1) if match else ""

def build_targeted_feedback(qa_output, rspec_result):
    """Build structured, actionable feedback for the Backend agent from QA failures."""
    feedback = "\n\n## ❌ QA TEST RESULTS — YOUR CODE HAS BUGS\n"
    feedback += f"**Results:** {rspec_result['examples']} tests, {rspec_result['failures']} failures, {rspec_result['errors']} errors\n\n"
    
    # Wrong column names (most common 3B mistake)
    no_method_matches = _re.findall(r"undefined method [`'](\w+)='", qa_output)
    if no_method_matches:
        feedback += "### ❌ Wrong Column Names\n"
        feedback += "These attributes DO NOT EXIST. Check db/schema.rb for correct names:\n"
        for method in sorted(set(no_method_matches)):
            feedback += f"- `{method}` does not exist\n"
        feedback += "\n"
    
    # Missing constants
    name_errors = _re.findall(r"NameError:\s+uninitialized constant (.+?)$", qa_output, _re.MULTILINE)
    if name_errors:
        feedback += "### ❌ Missing Classes/Modules\n"
        for name in sorted(set(name_errors)):
            feedback += f"- `{name.strip()}` does not exist\n"
        feedback += "-> ⚠️ You MUST CREATE the file that defines this constant (e.g., app/models/... or app/graphql/mutations/...).\n"
        feedback += "-> DO NOT just rewrite the spec file. Write the actual implementation file.\n\n"
        
    # Load Errors (syntax or uninitialized constants in describe blocks)
    load_errors = _re.findall(r"An error occurred while loading (.+?)\.\nFailure/Error:(.+?)(?=\n\n|\Z)", qa_output, _re.DOTALL)
    if load_errors:
        feedback += "### ❌ File Load Errors (Syntax or Missing Constants)\n"
        for file_path, error_details in load_errors[:3]:
            feedback += f"**File:** `{file_path}` failed to load.\n"
            feedback += f"```ruby\n{error_details.strip()[:500]}\n```\n"
            if "NameError" in error_details or "uninitialized constant" in error_details:
                feedback += "-> ⚠️ This usually means you need to create the class/module in `app/` before the spec can load it.\n"
        feedback += "\n"
    
    # Individual failures (max 3 to fit context window)
    failure_descs = _re.findall(r'\d+\)\s+(.+?)\n\s+Failure/Error:', qa_output, _re.DOTALL)
    if failure_descs:
        feedback += "### Failing Tests\n"
        for i, desc in enumerate(failure_descs[:3]):
            feedback += f"{i+1}. {desc.strip()}\n"
        feedback += "\n"
    
    feedback += "Fix ALL errors. Use ONLY column names from the schema provided above.\n"
    return feedback

def run_rspec_directly(project_path, spec_files, container_name):
    """Fallback: Run RSpec directly from the orchestrator, bypassing QA agent."""
    cmd = ["docker", "exec", container_name, "bundle", "exec", "rspec"] + spec_files
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT: RSpec execution exceeded 300 seconds"
    except Exception as e:
        return f"ERROR: {str(e)}"

def load_project_config(project_path):
    """Load project-specific agent configuration from .openclaw/config.json."""
    config_path = os.path.join(project_path, ".openclaw", "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading project config: {e}")
    return {}

def rescue_hallucinated_writes(response_text, container_ws):
    """Safety net: Parse write tool calls or markdown blocks from agent TEXT response.
    Small models (3B) often fallback to markdown when tools fail.
    This rescues both JSON-like tool strings and markdown code blocks."""
    import re
    rescued = 0
    
    # ── PATTERN 1: JSON-like strings ──────────────────────────────────────────
    json_pattern = r'"name"\s*:\s*"write"[^}]*?"(?:path|filePath|file)"\s*:\s*"([^"]+)"[^}]*?"content"\s*:\s*"((?:[^"\\]|\\.)*)"'
    for match in re.finditer(json_pattern, response_text, re.DOTALL):
        file_path, content = match.group(1), match.group(2)
        content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
        rescued += write_rescued_file(file_path, content, container_ws)
        
    # ── PATTERN 2: Markdown headers + Ruby blocks ─────────────────────────────
    # Matches "### spec/path/file.rb" or "File: spec/..." followed by ```ruby...```
    md_pattern = r'(?:###\s*|File:\s*|Path:\s*|`)([\w\/\.\-]+\.(?:rb|yml|json|md))[`\s]*\n\s*```(?:ruby|yaml|json|markdown|)\n(.*?)\n\s*```'
    for match in re.finditer(md_pattern, response_text, re.DOTALL):
        file_path, content = match.group(1), match.group(2)
        if 'AGENT_REPORT' not in file_path.upper():
            rescued += write_rescued_file(file_path, content, container_ws)
    
    return rescued

def write_rescued_file(file_path, content, container_ws):
    """Helper to write a rescued file to the container."""
    # Normalize path
    if '/workspaces/' in file_path:
        parts = file_path.split('/workspaces/')
        if len(parts) > 1:
            subpath = parts[1]
            file_path = subpath.split('/', 1)[1] if '/' in subpath else subpath
    elif file_path.startswith('/root/'):
        file_path = file_path.split('/')[-1] if '/' in file_path else file_path
    
    # Skip report files and non-code files
    if any(kw in file_path.upper() for kw in ('AGENT_REPORT', 'SYSTEM.MD', 'DOCKER-COMPOSE')):
        return 0
    if not any(file_path.endswith(ext) for ext in ('.rb', '.yml', '.json', '.js', '.ts')):
        return 0
        
    full_path = f"{container_ws}/{file_path}"
    dir_path = os.path.dirname(full_path)
    
    subprocess.run(["docker", "exec", "openclaw-gateway", "mkdir", "-p", dir_path], capture_output=True)
    write_result = subprocess.run(
        ["docker", "exec", "-i", "openclaw-gateway", "bash", "-c", f"cat > '{full_path}'"],
        input=content, capture_output=True, text=True
    )
    
    if write_result.returncode == 0:
        print(f"🔧 [RESCUE] Successfully recovered: {file_path}")
        return 1
    return 0

# ─── Load Environment ────────────────────────────────────────────────────────
def load_env():
    env = {}
    AI_HUB_DIR = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.join(AI_HUB_DIR, ".env")
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
    project_id = env.get("PROJECT_BOARD_ID", "PVT_kwHOATWBuM4BQ0Pm")
    field_id = env.get("PROJECT_STATUS_FIELD_ID", "PVTSSF_lAHOATWBuM4BQ0Pmzg-0748")
    
    options = {
        "Backlog": env.get("PROJECT_OPTION_BACKLOG", "53cd9920"),
        "To Do": env.get("PROJECT_OPTION_TODO", "f75ad846"),
        "In Progress": env.get("PROJECT_OPTION_IN_PROGRESS", "47fc9ee4"),
        "In Review QA": env.get("PROJECT_OPTION_IN_REVIEW", "0004c560"),
        "Pull request Review": env.get("PROJECT_OPTION_PR_REVIEW", "d121c55f"),
        "Done": env.get("PROJECT_OPTION_DONE", "98236657")
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

        if status in ["To Do", "Todo", "In Progress"]:
            items.append({
                "id": node["id"],
                "title": title,
                "body": body,
                "url": content.get("url"),
                "number": content.get("number"),
                "status": status
            })

    return items

# ─── Container Environment Toggle ─────────────────────────────────────────
def ensure_dev_container(project_path):
    """Ensure the project container is running in development mode with host volume mount.
    Creates a docker-compose.override.yml to add '- .:/app' without modifying the production
    docker-compose.yml."""
    config = load_project_config(project_path)
    ruby_container = config.get("container_name", "ordenapp_web_container")
    override_path = os.path.join(project_path, "docker-compose.override.yml")
    
    # Create override file for dev volume mount (if not already present)
    if not os.path.exists(override_path):
        with open(override_path, 'w') as f:
            f.write("version: '3'\nservices:\n  web:\n    volumes:\n      - .:/app\n")
        print("📝 Created docker-compose.override.yml with dev volume mount.")
    
    # Restart container in development mode  
    print("🔄 Restarting container in development mode with volume mount...")
    dev_env = os.environ.copy()
    dev_env["ENV"] = "development"
    subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "web"], cwd=project_path, env=dev_env, capture_output=True)
    time.sleep(10)
    print(f"✅ {ruby_container} ready in development mode.")

def restore_production_container(project_path):
    """Restore the container to production mode by removing the override and restarting."""
    override_path = os.path.join(project_path, "docker-compose.override.yml")
    if os.path.exists(override_path):
        try:
            os.remove(override_path)
            print("🗑️ Removed docker-compose.override.yml.")
        except Exception as e:
            print(f"⚠️ Error removing override: {e}")
    
    print("🔄 Restarting container in production mode...")
    subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "web"], cwd=project_path, capture_output=True)
    time.sleep(5)
    print("✅ Container restored to production mode.")


def safe_clear_locks(agent_id=None, silent=False):
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
            if not silent:
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
    """Run an agent turn via CLI with proper timeout overrides and heartbeat monitor."""
    # --- Deep Clean Agent Workspace (Maximize 3B Reasoning) ---
    print(f"🧹 Cleaning agent workspace to maximize reasoning...")
    container_ws = f"/root/.openclaw/state/agents/{agent_id}"
    META_FILES_TO_CLEAN = [
        ".containers.txt", ".git_log.txt", "AGENT_REPORT.md", 
        "docker-compose.override.yml"
    ]
    for mf in META_FILES_TO_CLEAN:
        subprocess.run(["docker", "exec", "openclaw-gateway", "rm", "-f", f"{container_ws}/{mf}"], capture_output=True)

    # Inject MENTAL RESET instruction
    full_message = f"[MENTAL RESET: Clear all previous context, assumptions, and cached state. Start fresh.]\n\n{message}"
    
    cmd = [
        "docker", "exec", "openclaw-gateway", 
        "openclaw", "agent", "--agent", agent_id, "--message", full_message, "--json", "--timeout", str(timeout), "--verbose", "on"
    ]
    print(f"Triggering [{agent_id.upper()}] via CLI (Timeout: {timeout}s)...")
    
    # Initial I/O state
    last_io_time = time.time()
    last_io_timestamp = get_latest_io_timestamp(agent_id)
    progress_detected = False
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    start_time = time.time()
    io_deadlock_threshold = 10800 # 3 hours of silence = deadlock
    
    try:
        while True:
            # Check if process is still running
            retcode = process.poll()
            if retcode is not None:
                stdout, stderr = process.communicate()
                if retcode == 0:
                    try:
                        # Check for the 60s "Request timed out" payload
                        if "Request timed out" in stdout:
                             print(f"⚠️  [{agent_id.upper()}] CLI TIMEOUT DETECTED at {int(time.time() - start_time)}s.")
                             print("   Wait... I see the Agent is still working on the Gateway (Heartbeat logic active).")
                             print("   Switching to SILENT MONITOR MODE - Waiting for logs to go quiet.")
                             # We break the CLI check loop to enter the Silence-Detection loop below
                             break
                        
                        print(f"RAW AGENT OUTPUT (v37): {stdout[:500]}...")
                        start_idx = stdout.find('{')
                        if start_idx != -1:
                            parsed = json.loads(stdout[start_idx:])
                            text = ""
                            try:
                                text = parsed.get("result", {}).get("payloads", [{}])[0].get("text", "")
                            except: pass
                            
                            aborted = False
                            try:
                                aborted = parsed.get("result", {}).get("meta", {}).get("aborted", False)
                            except: pass
                            
                            # Success!
                            return {"response": text, "raw": parsed, "aborted": aborted, "progress_detected": progress_detected}
                        return {"response": "", "raw": {}, "aborted": False, "progress_detected": progress_detected}
                    except json.JSONDecodeError:
                        print(f"Error parsing JSON from {agent_id}: {stdout}")
                        return None
                else:
                    print(f"Error triggering {agent_id} (Code {retcode}): {stderr}")
                    return None

            # Heartbeat check
            current_time = time.time()
            if current_time - start_time > timeout:
                print(f"🛑 STRIKE 1: Absolute timeout of {timeout}s reached.")
                process.terminate()
                return None
            
            # Check for I/O activity every 20 seconds
            time.sleep(20)
            
            current_io_timestamp = get_latest_io_timestamp(agent_id)
            if current_io_timestamp > last_io_timestamp:
                progress_detected = True
                last_io_timestamp = current_io_timestamp
                last_io_time = current_time
                elapsed = int(current_time - start_time)
                print(f"💓 [{agent_id.upper()}] Heartbeat: Active progress detected ({elapsed}s elapsed)")
            else:
                # If CLI disconnected but we are still here, we wait for a persistent silence
                quiet_duration = int(current_time - last_io_time)
                if quiet_duration >= io_deadlock_threshold:
                    print(f"💀 DEADLOCK: Agent {agent_id} has been silent for {quiet_duration}s.")
                    process.kill()
                    restart_gateway_and_cleanup()
                    return None
                
        # --- SILENT MONITOR MODE (CLI died but Task is alive) ---
        print(f"🛸 [{agent_id.upper()}] Silent Monitor Active. Waiting for activity to cease...")
        while True:
            time.sleep(30) # Poll every 30s
            current_io_timestamp = get_latest_io_timestamp(agent_id)
            if current_io_timestamp > last_io_timestamp:
                last_io_timestamp = current_io_timestamp
                last_io_time = time.time()
                print(f"💓 [{agent_id.upper()}] Heartbeat (Silent): Still active...")
            else:
                quiet_duration = int(time.time() - last_io_time)
                if quiet_duration >= 180: # 3 minutes of total silence after a timeout = Finished
                    print(f"✅ [{agent_id.upper()}] Activity ceased for 3m. Assuming Agent has completed turn.")
                    return {"response": "Silent Completion", "raw": {}, "aborted": False, "progress_detected": True}
                
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

    AI_HUB_DIR = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(AI_HUB_DIR)
    project_path = os.path.join(base_dir, project_name)
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
    
    # Safe startup lock cleanup (with timeout so it never hangs, silent to avoid log spam)
    safe_clear_locks(silent=True)

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
                
                # Check if branch already exists locally to resume work
                branch_check = subprocess.run(["git", "-C", project_path, "branch", "--list", cur_branch], capture_output=True, text=True)
                if cur_branch in branch_check.stdout:
                    print(f"Resuming on existing branch '{cur_branch}'...")
                    subprocess.run(["git", "-C", project_path, "checkout", cur_branch], capture_output=True)
                else:
                    print(f"Checking out NEW working branch '{cur_branch}' from production...")
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
            
            # ── Schema Injection: Feed the 3B model the schema directly ──
            # Small models skip reading files. We inject the ground truth inline.
            model_match = _re.search(r'for\s+(\w+)', item['title'])
            model_name = model_match.group(1) if model_match else ""
            schema_excerpt = extract_schema_for_model(project_path, model_name) if model_name else ""
            
            # Also check for existing factory to prevent duplicates
            existing_factory = ""
            if model_name:
                factory_path = os.path.join(project_path, "spec", "factories", f"{model_name.lower()}s.rb")
                if os.path.exists(factory_path):
                    with open(factory_path, 'r') as f:
                        existing_factory = f.read()
            
            work_prompt = (
                f"## Task\n"
                f"**Title:** {item['title']}\n"
                f"**Description:**\n{item['body']}\n\n"
            )
            
            if schema_excerpt:
                work_prompt += (
                    f"## Database Schema (GROUND TRUTH — use ONLY these column names)\n"
                    f"```ruby\n{schema_excerpt}\n```\n\n"
                )
            
            if existing_factory:
                work_prompt += (
                    f"## Existing Factory (DO NOT duplicate — edit if needed)\n"
                    f"```ruby\n{existing_factory}\n```\n\n"
                )
            
            task_id = item.get('id', 'unknown')
            saved_feedback = get_feedback(task_id)
            hallucination_count = get_state_counter(task_id, 'hallucination')
            
            if saved_feedback:
                work_prompt += saved_feedback
            
            if hallucination_count > 0:
                work_prompt += (
                    f"\n⚠️  **CRITICAL RE-TRY WARNING (Attempt {hallucination_count+1})**\n"
                    f"Your previous attempt was REJECTED because you did not write any code files to disk.\n"
                    f"You MUST use the `write_file` tool or follow the File pattern below to output code.\n"
                    f"DO NOT just provide a text explanation. Output the full file contents.\n\n"
                )
            
            work_prompt += (
                "## Instructions\n"
                "Your full protocol is in `SYSTEM.md`.\n"
                "CRITICAL: Use ONLY the column names shown in the Database Schema above. Do NOT invent attributes.\n\n"
                "IMPORTANT: To write or modify files, you MUST use the following EXACT Markdown format in your text response:\n\n"
                "File: path/to/your/file.rb\n"
                "```ruby\n"
                "# your full code here\n"
                "```\n\n"
                "You must output the full file content inside the block. When done, write a short summary.\n"
            )

            
            # --- Sync Host Source Code into Container Workspace ---
            container_ws = f"/root/.openclaw/workspaces/{assigned_agent}"
            print(f"Syncing code files into container workspace {container_ws}...")
            
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"rm -rf {container_ws}/*"], capture_output=True)
            subprocess.run(["docker", "cp", f"{project_path}/.", f"openclaw-gateway:{container_ws}/"], capture_output=True)

            # Prevent OpenClaw from freezing its indexer by trying to AI-scan thousands of binary/library files
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", 
                            f"rm -rf {container_ws}/.git {container_ws}/node_modules {container_ws}/tmp {container_ws}/log {container_ws}/vendor {container_ws}/public"], 
                           capture_output=True)

            # Expose agent context context to gateway root (OpenClaw requires SYSTEM.md at workspace root)
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"cp {container_ws}/.openclaw/*.md {container_ws}/.openclaw/*.json {container_ws}/ 2>/dev/null || true"], capture_output=True)

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
            
            # Secondary validation: check response content for system errors or timeout signatures
            SYSTEM_ERRORS = ["404", "model not found", "error 500", "connection refused", "bad gateway"]
            TIMEOUT_STRINGS = ["request timed out", "timed out before a response", "increase `agents.defaults"]
            
            response_lower = work_response_text.lower()
            is_system_error = any(sig in response_lower for sig in SYSTEM_ERRORS)
            is_timeout_text = any(sig in response_lower for sig in TIMEOUT_STRINGS)
            
            if is_system_error:
                reason = f"SYSTEM ERROR DETECTED: {work_response_text}. Stopping to prevent infinite retry loops."
                print(f"🛑 {reason}")
                handle_failure(item, env, reason)
                continue

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
            
            # Preserve agent edits to SYSTEM.md etc by moving them back into .openclaw/ before sync
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"mv {container_ws}/SYSTEM.md {container_ws}/SOUL.md {container_ws}/IDENTITY.md {container_ws}/TOOLS.md {container_ws}/AGENTS.md {container_ws}/.openclaw/ 2>/dev/null || true"], capture_output=True)
            # Destroy transient files so they don't leak to host root
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"rm -f {container_ws}/.containers.txt {container_ws}/.git_log.txt {container_ws}/mutation_output_fixed.txt {container_ws}/*.out {container_ws}/docker-compose.override.yml"], capture_output=True)

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

            # ─── Selective Git Add ───────────────────────────────────────────────────
            # Use specific patterns to avoid adding internal agent files (SYSTEM.md, etc.)
            GIT_WHITELIST = ["spec/", "app/", "db/", "config/", "lib/", "test/", "agent-report/"]
            for dir_pattern in GIT_WHITELIST:
                subprocess.run(["git", "-C", project_path, "add", dir_pattern], capture_output=True)
            
            # Explicitly UNSTAGE/REMOVE meta-files if they were accidentally added
            META_FILES_TO_IGNORE = ["SYSTEM.md", "docker-compose.override.yml", "AGENT_REPORT.md", ".containers.txt", ".git_log.txt", ".openclaw/"]
            for meta in META_FILES_TO_IGNORE:
                subprocess.run(["git", "-C", project_path, "rm", "--cached", "-r", meta], capture_output=True)

            # Only commit if changes were actually made in whitelist dirs
            git_status = subprocess.run(["git", "-C", project_path, "status", "--porcelain"], capture_output=True, text=True)
            has_changes = bool(git_status.stdout.strip())
            
            if has_changes:
                subprocess.run(["git", "-C", project_path, "commit", "-m", f"[{assigned_agent.upper()}] Implemented changes for: {item['title']}"], capture_output=True)
            
            # Determine if we should bypass QA Agent step (Audit Report mode)
            # Audit mode = ONLY the AGENT_REPORT.md or agent-report/ directory changed.
            # If the agent created/modified spec/, app/, db/, config/, or any real source files -> NOT audit mode.
            REAL_CODE_DIRS = ("spec/", "app/", "db/", "config/", "lib/", "test/")
            is_audit_mode = True
            
            # Check 1: Uncommitted changes from this turn
            lines = git_status.stdout.strip().split("\n")
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Get the file path part (after the 2-char git status prefix)
                file_path = stripped[3:] if len(stripped) > 3 else stripped
                
                # A change is ONLY considered "real code" if it's in a code directory
                # AND it's not a report or internal system file.
                is_report_only = (
                    "agent-report" in file_path
                    or "AGENT_REPORT" in file_path.upper()
                )
                
                is_internal_system = any(kw in file_path for kw in [
                    "SYSTEM.md", "docker-compose.override.yml", ".containers.txt", ".git_log.txt", ".openclaw/"
                ])
                
                is_real_code_dir = any(file_path.startswith(d) for d in REAL_CODE_DIRS)
                
                if is_real_code_dir and (not is_report_only) and (not is_internal_system):
                    # ANTI-STUB CHECK: Verify the file isn't just a rails-generated placeholder
                    full_path = os.path.join(project_path, file_path)
                    if file_path.endswith('_spec.rb') and os.path.exists(full_path):
                        try:
                            with open(full_path, 'r') as fcheck:
                                content = fcheck.read()
                            if 'pending "add some examples' in content and content.count('\n') < 10:
                                print(f"⚠️  [STUB] {file_path} is a rails-generated empty spec. Ignoring.")
                                continue  # skip this file, keep checking others
                        except Exception:
                            pass
                    is_audit_mode = False  # Actual source/spec files were touched!
                    break

            # Check 2: If no uncommitted changes, check if the BRANCH itself has committed
            # code diffs vs production (from a previous successful agent turn).
            # This prevents false-positive hallucination detection on resumed branches.
            if is_audit_mode:
                branch_diff = subprocess.run(
                    ["git", "-C", project_path, "diff", "--name-only", "production...HEAD"],
                    capture_output=True, text=True, timeout=30
                )
                if branch_diff.returncode == 0:
                    for diff_file in branch_diff.stdout.strip().split("\n"):
                        diff_file = diff_file.strip()
                        if diff_file and any(diff_file.startswith(d) for d in REAL_CODE_DIRS):
                            is_audit_mode = False
                            print(f"📦 Branch has pre-committed code: {diff_file} — skipping hallucination guard.")
                            break

            if is_audit_mode:
                # ── Hallucination guard ──────────────────────────────────────────
                # Small models (qwen2.5-coder:3b) often CLAIM to write files in their
                # text response without actually calling the write tool.
                # RESCUE PHASE: Try to parse write tool calls from the text response
                # and execute them manually before declaring hallucination.
                CODE_TASK_KEYWORDS = [
                    "create spec/", "spec/factories", "spec/models", "spec/graphql",
                    "spec/requests", "spec/controllers", "write test", "write spec",
                    "create migration", "create file", "add model", "write rspec",
                    "create app/", "add route", "create controller", "create service",
                ]
                task_body_lower = (item.get("body") or "").lower()
                task_implies_code = any(kw in task_body_lower for kw in CODE_TASK_KEYWORDS)

                if task_implies_code:
                    # ── RESCUE ATTEMPT: Parse write calls from text and execute ──
                    rescued = rescue_hallucinated_writes(work_response_text, container_ws)
                    if rescued > 0:
                        print(f"🔧 [RESCUE] Recovered {rescued} file(s) from text response. Re-syncing...")
                        subprocess.run(["docker", "cp", f"openclaw-gateway:{container_ws}/.", f"{project_path}/"], capture_output=True)
                        
                        # Apply same selective add and meta-ignore policy
                        GIT_WHITELIST = ["spec/", "app/", "db/", "config/", "lib/", "test/", "agent-report/"]
                        for dir_pattern in GIT_WHITELIST:
                            subprocess.run(["git", "-C", project_path, "add", dir_pattern], capture_output=True)
                        
                        META_FILES_TO_IGNORE = ["SYSTEM.md", "docker-compose.override.yml", "AGENT_REPORT.md", ".containers.txt", ".git_log.txt", ".openclaw/"]
                        for meta in META_FILES_TO_IGNORE:
                            subprocess.run(["git", "-C", project_path, "rm", "--cached", "-r", meta], capture_output=True)

                        git_status = subprocess.run(["git", "-C", project_path, "status", "--porcelain"], capture_output=True, text=True)
                        
                        # Re-evaluate: did the rescue produce actual code files?
                        rescue_has_code = False
                        for rline in git_status.stdout.strip().split("\n"):
                            rstripped = rline.strip()
                            if len(rstripped) > 3:
                                rfp = rstripped[3:]
                                if any(rfp.startswith(d) for d in REAL_CODE_DIRS):
                                    rescue_has_code = True
                                    break
                        
                        if rescue_has_code:
                            is_audit_mode = False
                            print("✅ [RESCUE] Files successfully written! Proceeding to QA.")
                            # Fall through to QA workflow below (don't continue)
                        else:
                            print("⚠️  [RESCUE] Files were written but no real code detected.")
                    
                    # If rescue didn't fix it, apply hallucination guard with retry limit
                    if is_audit_mode:
                        task_id = item.get('id', 'unknown')
                        attempt = increment_state_counter(task_id, 'hallucination')
                        
                        if attempt >= MAX_HALLUCINATION_RETRIES:
                            reason = (
                                f"HALLUCINATION LIMIT REACHED ({attempt}/{MAX_HALLUCINATION_RETRIES}): "
                                "The agent repeatedly failed to write files to disk. "
                                "Escalating to Backlog for human review."
                            )
                            print(f"🛑 {reason}")
                            handle_failure(item, env, reason)
                            continue
                        
                        reason = (
                            f"AGENT HALLUCINATION (attempt {attempt}/{MAX_HALLUCINATION_RETRIES}): "
                            "Task required creating code/spec files but the agent only produced a text report. "
                            "Retrying."
                        )
                        print(f"⚠️  {reason}")
                        send_telegram(f"♻️ Task '{item['title']}' hallucination ({attempt}/{MAX_HALLUCINATION_RETRIES}). Retrying.")
                        if item.get("number"):
                            comment_on_issue(item.get("number"),
                                f"🤖 **Agent Hallucination (attempt {attempt}/{MAX_HALLUCINATION_RETRIES}):**\n\n"
                                f"The agent did not write files to disk. Retrying.\n\n"
                                f"> {work_response_text[:300]}", env)
                        print("⚠️ [RESILIENCE] Preserving workspace for retry.")
                        move_task_column(item['id'], item['title'], "To Do", env)
                        continue

                if is_audit_mode:
                    # Genuine audit task (only a report was expected)
                    print("📋 No code modifications made (Audit mode confirmed). Bypassing QA Turn.")
                    move_task_column(item['id'], item['title'], "Pull request Review", env)
                    if has_changes:
                        subprocess.run(["git", "-C", project_path, "push", "-f", "origin", cur_branch], capture_output=True)
                        create_pull_request(item.get("number"), env, cur_branch)
                    send_telegram(f"🎉 SUCCESS: Audit Report drafted for issue #{item.get('number')}. Ready at 'Pull Request Review'.")
                    continue

            print("✅ Code touch detected. Moving to QA verification workflow.")
            
            # --- 1. ENSURE DEV CONTAINER: Verify container is running with volume mount ---
            config = load_project_config(project_path)
            ruby_container = config.get("container_name", "ordenapp_web_container")
            print(f"🧐 [QA] Verifying execution inside {ruby_container}...")
            ensure_dev_container(project_path)

            # --- MULTI-AGENT FIX: Empowering QA gracefully ---
            # Build a list of ONLY the spec files the Backend agent created/modified
            changed_specs = []
            branch_diff = subprocess.run(
                ["git", "-C", project_path, "diff", "--name-only", "production...HEAD"],
                capture_output=True, text=True, timeout=30
            )
            if branch_diff.returncode == 0:
                for f in branch_diff.stdout.strip().split("\n"):
                    f = f.strip()
                    if f.startswith("spec/") and f.endswith("_spec.rb"):
                        changed_specs.append(f)
            
            # Also check uncommitted changes
            for line in git_status.stdout.strip().split("\n"):
                stripped = line.strip()
                if len(stripped) > 3:
                    fp = stripped[3:]
                    if fp.startswith("spec/") and fp.endswith("_spec.rb") and fp not in changed_specs:
                        changed_specs.append(fp)
            
            if not changed_specs:
                # Fallback: run specs only in model/graphql dirs (avoids broken view specs)
                rspec_target = "spec/models spec/graphql spec/requests"
            else:
                rspec_target = " ".join(changed_specs)
            
            print(f"🧪 QA will test ONLY: {rspec_target}")
            qa_workspace = "/root/.openclaw/workspaces/qa"
            
            # Create a focused test wrapper that only runs the relevant specs
            subprocess.run([
                "docker", "exec", "openclaw-gateway", "bash", "-c",
                f"echo '#!/bin/bash\ndocker exec {ruby_container} bash -l -c \"bundle exec rspec {rspec_target}\"' > {qa_workspace}/run_tests.sh && chmod +x {qa_workspace}/run_tests.sh"
            ])

            qa_prompt = (
                f"You are a QA test runner. Your ONLY job is to execute tests and report what happened.\n\n"
                f"STEP 1: Use your `exec` tool to run this command:\n"
                f"bash ./run_tests.sh\n\n"
                f"STEP 2: Copy the COMPLETE terminal output from the test execution into your response.\n"
                f"You MUST include the full output including the lines that say how many examples ran,\n"
                f"how many failures occurred, and the elapsed time.\n\n"
                f"STEP 3: After the terminal output, write a single verdict line:\n"
                f"VERDICT: PASS (if 0 failures) or VERDICT: FAIL (if any failures or errors)\n\n"
                f"CRITICAL RULES:\n"
                f"- You MUST actually execute the command using your `exec` tool. Do NOT guess the result.\n"
                f"- Do NOT just write a JSON code block in text. You MUST invoke the real tool execution.\n"
                f"- If the exec tool fails or is blocked, report the exact error. Do NOT say PASS.\n"
                f"- Your response MUST contain the text 'examples' and 'failures' from RSpec output.\n"
                f"- If your response does not contain real terminal output, it will be rejected.\n"
            )

            print("🛡️  Triggering autonomous QA Agent...")
            send_telegram(f"✅ {assigned_agent.upper()} implemented turn for '{item['title']}'. QA reviewing now.")
            move_task_column(item['id'], item['title'], "In Review QA", env)
            # Sync code to QA workspace
            subprocess.run(["docker", "exec", "openclaw-gateway", "sh", "-c", f"rm -rf {qa_workspace}/*"], capture_output=True)
            subprocess.run(["docker", "cp", f"{project_path}/.", f"openclaw-gateway:{qa_workspace}/"], capture_output=True)
            
            qa_res = trigger_agent("qa", qa_prompt, timeout=3600)
            if not qa_res:

                handle_retry(item, env, "QA FAILURE: Agent returned None.", cur_branch)
                continue
            
            # ── QA Outcome Analysis (Evidence-Based) ─────────────────────────
            qa_response_text = qa_res.get("response", "").strip()
            print(f"QA Response: {qa_response_text}")
            qa_lower = qa_response_text.lower()
            
            # Guard 1: Exec-denied or allowlist failures
            exec_failure_patterns = ["exec denied", "allowlist", "permission denied", "not permitted"]
            qa_exec_failed = any(p in qa_lower for p in exec_failure_patterns)
            
            if qa_exec_failed:
                print(f"🚨 [QA EXEC BLOCKED] The test runner was blocked by the gateway: {qa_response_text[:200]}")
                handle_retry(item, env, "QA EXEC DENIED: The gateway blocked test execution (allowlist miss). Retrying after config fix.", cur_branch)
                continue
            
            # Guard 2: Tool call hallucination (QA outputs JSON instead of running)
            is_tool_call_hallucination = '"name"' in qa_lower and ('"arguments"' in qa_lower or 'arguments:' in qa_lower)
            if is_tool_call_hallucination:
                print("⚠️ QA MODEL HALLUCINATION detected: Agent output tool JSON instead of running tests.")
                handle_retry(item, env, "QA MODEL HALLUCINATION: QA agent output tool call JSON instead of executing tests. Retrying task.", cur_branch)
                continue
            
            # Guard 3: Hollow response detection — verify RSpec evidence exists
            rspec_result = parse_rspec_result(qa_response_text)
            
            if not rspec_result['has_evidence']:
                # QA agent didn't produce real RSpec output — possible hallucination
                task_id = item.get('id', 'unknown')
                hollow_count = increment_state_counter(task_id, 'qa_hollow')
                
                if hollow_count >= 2:
                    # FALLBACK: Run RSpec directly from orchestrator
                    print(f"🔧 [DIRECT QA] QA agent hollow {hollow_count}x. Running RSpec directly (bypassing agent)...")
                    spec_list = changed_specs if changed_specs else ["spec/models", "spec/graphql", "spec/requests"]
                    direct_output = run_rspec_directly(project_path, spec_list, ruby_container)
                    print(f"📋 [DIRECT QA] Output:\n{direct_output[:500]}")
                    qa_response_text = direct_output
                    rspec_result = parse_rspec_result(direct_output)
                    
                    if not rspec_result['has_evidence']:
                        # Even direct execution failed — infrastructure problem
                        system_error_patterns = [
                            "no such container", "docker:", "connection reset",
                            "gateway error", "timed out", "TIMEOUT:"
                        ]
                        is_system_error = any(p in direct_output.lower() for p in system_error_patterns)
                        if is_system_error:
                            attempts = get_state_counter(task_id, 'recovery')
                            if attempts < 1:
                                print(f"🛠️  [RECOVERY] Infrastructure failure. Auto-recovery...")
                                increment_state_counter(task_id, 'recovery')
                                recovery_env = os.environ.copy()
                                recovery_env["ENV"] = "development"
                                subprocess.run(["docker", "compose", "up", "-d"], cwd=project_path, env=recovery_env, capture_output=True)
                                handle_retry(item, env, "QA INFRASTRUCTURE RECOVERY: Auto-started Docker container. Retrying.", cur_branch)
                                continue
                            else:
                                handle_failure(item, env, f"CRITICAL SYSTEM FAILURE (Persistent): {direct_output[:500]}")
                                continue
                        handle_retry(item, env, f"QA DIRECT EXECUTION FAILED: {direct_output[:300]}", cur_branch)
                        continue
                else:
                    print(f"⚠️ [QA HOLLOW] Response lacks RSpec evidence (attempt {hollow_count}/2). Retrying QA...")
                    move_task_column(item['id'], item['title'], "In Review QA", env)
                    continue
            
            # ── We now have verified RSpec evidence ──────────────────────────
            print(f"📊 [RSPEC] {rspec_result['raw_summary']} | errors: {rspec_result['errors']}")
            
            if rspec_result['passed']:
                # All tests pass — proceed to success finalization
                print(f"✅ [QA VERIFIED] All tests pass: {rspec_result['raw_summary']}")
                clear_feedback(item.get('id', 'unknown'))
            else:
                # Tests failed — apply convergence analysis
                task_id = item.get('id', 'unknown')
                cycle_num = record_qa_cycle(
                    task_id,
                    rspec_result['examples'],
                    rspec_result['failures'],
                    rspec_result['errors']
                )
                
                should_continue, reason, _, metrics = evaluate_convergence(task_id)
                trend_str = " → ".join(str(s) for s in metrics.get('trend', []))
                print(f"📈 [CONVERGENCE] Cycle {cycle_num}: {reason} | Trend: [{trend_str}]")
                
                if should_continue:
                    # Build targeted feedback and send back to Backend
                    print(f"♻️ [FEEDBACK LOOP] Sending structured error feedback to Backend...")
                    send_telegram(f"♻️ QA Cycle {cycle_num} for '{item['title']}': {reason}")
                    
                    if item.get("number"):
                        comment_on_issue(item.get("number"),
                            f"🤖 **QA Cycle {cycle_num} — {reason}**\n\n"
                            f"```\n{qa_response_text[:2000]}\n```", env)
                    
                    # Inject structured feedback into work_prompt
                    qa_error_context = build_targeted_feedback(qa_response_text, rspec_result)
                    
                    # SAVE IT PERSISTENTLY
                    save_feedback(task_id, qa_error_context)
                    
                    work_prompt = work_prompt.rstrip() + qa_error_context
                    
                    print("⚠️ [RESILIENCE] Preserving workspace for Backend correction.")
                    move_task_column(item['id'], item['title'], "In Progress", env)
                else:
                    # Convergence says stop — escalate to human
                    print(f"🛑 [CONVERGENCE STOP] {reason}")
                    send_telegram(
                        f"🛑 Convergence stop for '{item['title']}': {reason}\n"
                        f"Trend: [{trend_str}] | Pass rate: {metrics.get('pass_rate', 0):.0%}"
                    )
                    handle_failure(item, env,
                        f"CONVERGENCE STOP after {cycle_num} cycles: {reason}. "
                        f"Error trend: [{trend_str}]. "
                        f"Last result: {rspec_result['raw_summary']}"
                    )
                    clear_feedback(item.get('id', 'unknown'))
                
                continue


            # 5. Success Finalization
            restore_production_container(project_path)
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

LOCK_FILE = "/tmp/mission_control.lock"

def acquire_instance_lock():
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        return lock_fd
    except BlockingIOError:
        print("❌ Another instance is already running. Exiting to prevent concurrency issues.")
        sys.exit(1)

if __name__ == "__main__":
    _lock = acquire_instance_lock()
    orchestrate()
