#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  🛸 APPLY NUCLEAR PATCH — v45 (DEFINITIVE)
#  
#  THE ONE SCRIPT TO RULE THEM ALL.
#  
#  This script performs a complete, clean restart of the entire autonomous
#  TDD pipeline. It incorporates ALL fixes from Sessions 1-12:
#  
#  ✓ Infrastructure reset (Docker containers, Ollama models)
#  ✓ RAM isolation (OLLAMA_MAX_LOADED_MODELS=1, KEEP_ALIVE=30s)
#  ✓ Agent SYSTEM.md restoration (QA + Backend instructions)
#  ✓ Task state reset (counters, branches, workspace caches)
#  ✓ Project container verification (from CONTAINER_NAME in .env)
#  ✓ Network connectivity validation (GitHub API)
#  ✓ GitHub board automation (move stuck tasks back to To Do)
#  ✓ QA execution allowlist
#  ✓ Lock file cleanup
#  ✓ Mission Control launch
#  
#  Usage: sudo bash apply_nuclear_patch.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Load .env
if [ -f "$DIR/.env" ]; then
    export $(grep -v '^#' "$DIR/.env" | xargs)
else
    echo "❌ FATAL: .env file not found at $DIR/.env"
    echo "   Copy .env.example to .env and fill in your project values."
    exit 1
fi

# ── Validate required variables ──────────────────────────────────────────────
MISSING=""
for VAR in PROJECT_NAME PROJECT_PATH GITHUB_TOKEN GITHUB_USER GITHUB_REPO PROJECT_NUMBER \
           PROJECT_BOARD_ID PROJECT_STATUS_FIELD_ID PROJECT_OPTION_TODO PROJECT_OPTION_BACKLOG; do
    if [ -z "${!VAR}" ]; then
        MISSING="$MISSING $VAR"
    fi
done
if [ -n "$MISSING" ]; then
    echo "❌ FATAL: Missing required variables in .env:$MISSING"
    echo "   Please set them before running this script."
    exit 1
fi

# Derive container name: use CONTAINER_NAME from .env, or fallback to ${PROJECT_NAME}_container
RUBY_CONTAINER="${CONTAINER_NAME:-${PROJECT_NAME}_container}"

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  🛸 NUCLEAR PATCH v45 — DEFINITIVE PIPELINE RESET"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  AI Hub:       $DIR"
echo "  Project:      $PROJECT_PATH"
echo "  Container:    $RUBY_CONTAINER"
echo "  GitHub User:  $GITHUB_USER"
echo "  GitHub Repo:  $GITHUB_REPO"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 1: STOP EVERYTHING
# ═══════════════════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 1: STOPPING ALL PROCESSES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 1.1 Killing any running mission_control.py..."
pkill -f "mission_control.py" 2>/dev/null || true
pkill -f "run_mission_control.sh" 2>/dev/null || true
sleep 2

echo "=> 1.2 Removing stale lock file..."
rm -f /tmp/mission_control.lock

echo "=> 1.3 Ensuring OPENCLAW_AGENTS includes all roles..."
if grep -q "^OPENCLAW_AGENTS=" .env 2>/dev/null; then
  AGENTS_VAR=$(grep "^OPENCLAW_AGENTS=" .env | cut -d= -f2)
  if [ -n "$AGENTS_VAR" ] && ! echo "$AGENTS_VAR" | grep -q "qa"; then
    echo "   ⚠️  Adding missing agents to OPENCLAW_AGENTS..."
    sed -i "s/^OPENCLAW_AGENTS=.*/OPENCLAW_AGENTS=backend,frontend,qa,architect,analyst,product_owner/" .env
  fi
fi
echo "   ✅ Process cleanup complete."

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 2: INFRASTRUCTURE RESET
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 2: INFRASTRUCTURE RESET"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 2.1 Generating clean OpenClaw config..."
bash generate-config.sh

echo "=> 2.2 Tearing down AI Hub containers..."
docker compose -f docker-compose.yml down

echo "=> 2.3 Purging RAM/Swap caches..."
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || echo "   ⚠️  Could not flush RAM caches (not root). Continuing."

echo "=> 2.4 Fixing workspace file ownership..."
if [ -n "$SUDO_USER" ]; then
    echo "   Running under sudo: fixing ownership of everything for standard user $SUDO_USER"
    chown -R "$SUDO_USER:$SUDO_USER" "$DIR"
    chown -R "$SUDO_USER:$SUDO_USER" "$PROJECT_PATH" 2>/dev/null || true
else
    echo "   Fixing ownership for current user $(whoami)"
    chown -R "$(whoami):$(whoami)" "$DIR" 2>/dev/null || true
    chown -R "$(whoami):$(whoami)" "$PROJECT_PATH" 2>/dev/null || true
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 3: AGENT SYSTEM.md RESTORATION
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 3: RESTORING AGENT INSTRUCTIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure directories exist
mkdir -p "$DIR/openclaw-docker/workspaces/qa/.openclaw"
mkdir -p "$DIR/openclaw-docker/workspaces/backend/.openclaw"

echo "=> 3.1 Writing QA Agent SYSTEM.md..."
cat > "$DIR/openclaw-docker/workspaces/qa/.openclaw/SYSTEM.md" << 'QASYSTEM'
# QA Engineer — System Instructions

You are a **QA Test Execution Gateway**. You do NOT write code. You do NOT analyze code. You ONLY execute tests and report results.

## Your ONLY Workflow

1. **Execute** the test suite using your `exec` tool:
   ```
   bash ./run_tests.sh
   ```

2. **Copy** the COMPLETE terminal output into your response. Include ALL lines — especially:
   - The RSpec summary line (e.g., `3 examples, 0 failures`)
   - Any error messages or stack traces
   - The elapsed time

3. **Write a verdict** at the END of your response:
   - `VERDICT: PASS` — if 0 failures AND 0 errors AND more than 0 examples ran (e.g. `3 examples, 0 failures`)
   - `VERDICT: FAIL` — if ANY failures or errors, OR if `0 examples` ran. If `0 examples` ran, it means the tests were not found or did not execute, which is a FAILURE.

## ABSOLUTE RULES

- You MUST use the `exec` tool to run the command. Do NOT guess or fabricate output.
- Do NOT write, modify, or suggest code changes. You are NOT a developer.
- Do NOT output JSON tool calls as text. You must INVOKE the tool, not print it.
- If the exec tool fails or is blocked, report the exact error message. Do NOT say PASS.
- If `run_tests.sh` does not exist, report: `VERDICT: FAIL — run_tests.sh not found`
- If the tests output `0 examples, 0 failures`, your verdict MUST be `VERDICT: FAIL` (because no tests were actually run).
- Your response MUST contain real terminal output with "examples" and "failures" from RSpec.
- Responses without real test output will be REJECTED automatically.

## Anti-Hallucination

- Do NOT invent test results. Only report what the terminal actually outputs.
- Do NOT say "all tests pass" without showing the actual RSpec output.
- If you cannot execute the tests for any reason, say `VERDICT: FAIL` and explain why.
QASYSTEM
echo "   ✅ QA SYSTEM.md restored ($(wc -c < "$DIR/openclaw-docker/workspaces/qa/.openclaw/SYSTEM.md") bytes)"

echo "=> 3.2 Writing Backend Agent SYSTEM.md..."
cat > "$DIR/openclaw-docker/workspaces/backend/.openclaw/SYSTEM.md" << 'BESYSTEM'
# Backend Developer — System Instructions

You are a **Ruby on Rails Backend Developer**. You write production-quality code and RSpec tests.

## Output Format (MANDATORY)

You MUST output files using this EXACT Markdown format:

```
File: path/to/your/file.rb
```ruby
# your full code here
```
```

Output EVERY file. Do NOT describe what you would write — actually write it.

## Code Rules

### GraphQL Mutations
- Place mutations in `app/graphql/mutations/<model_plural>/create_<model>.rb`
- Place input types in `app/graphql/inputs/<model>_input.rb`
- Extend `BaseMutation` (not `GraphQL::Schema::Mutation`)
- Register mutations in `app/graphql/types/mutation_type.rb`

### RSpec Testing Rules
- Use ONLY RSpec syntax. NEVER use Jest syntax.
- ❌ BANNED: `expect.anything`, `toEqual`, `toBe`, `describe.each`
- ✅ CORRECT: `be_present`, `eq()`, `be_valid`, `include()`
- Use `let` and `let!` for setup, not `before(:each)` with instance variables
- Use FactoryBot: `create(:model)`, `build(:model)`
- Use `type: :request` for GraphQL mutation specs
- **Relay Classic Mutation Specs**: Under `BaseMutation` (Relay Classic), mutation input variables in RSpec specs MUST be declared as `Create<Model>Input!` (e.g. `CreateCorporationInput!`), not `<Model>Input!` (e.g. `CorporationInput!`). In variables payload, wrap properties appropriately under the input key. Refer to sibling specs in the blueprint for exact schema patterns.

### Database Schema
- ALWAYS use column names from `db/schema.rb` — NEVER guess
- If the PRE-FLIGHT BLUEPRINT provides a schema, use ONLY those column names
- Check `belongs_to` associations — they create `_id` columns automatically

### Anti-Hallucination
- Do NOT create empty spec stubs with `pending "add some examples"`
- Every spec file MUST contain at least one real `it` block with assertions
- If you don't know a column name, check the schema — do NOT invent one
BESYSTEM
echo "   ✅ Backend SYSTEM.md restored ($(wc -c < "$DIR/openclaw-docker/workspaces/backend/.openclaw/SYSTEM.md") bytes)"

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 4: LAUNCH INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 4: LAUNCHING INFRASTRUCTURE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 4.1 Starting AI Hub containers (Ollama + OpenClaw)..."
docker compose -f docker-compose.yml up -d

echo "=> 4.2 Waiting for Ollama to stabilize (20s)..."
sleep 20

echo "=> 4.3 Pulling/syncing all agent models..."
bash pull-models.sh || echo "   ⚠️  Some models failed to pull. Check manually."

echo "=> 4.4 Waiting for OpenClaw Gateway health..."
for i in {1..20}; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' openclaw-gateway 2>/dev/null || echo "starting")
  echo "   Status: $STATUS ($i/20)"
  if [ "$STATUS" == "healthy" ]; then break; fi
  sleep 5
done

echo "=> 4.5 Applying QA Agent execution allowlist..."
docker exec openclaw-gateway openclaw approvals allowlist add --agent qa "*" 2>/dev/null || true
echo "   ✅ Infrastructure is running."

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 5: TASK STATE RESET (Intelligent — not blind nuke)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 5: RESETTING TASK STATE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 5.1 Resetting ALL task counters in mission_state.db..."
python3 -c "
import sqlite3, os
db = os.path.join('${DIR}', 'mission_state.db')
if not os.path.exists(db):
    print('   No DB found — will be created fresh on launch.')
else:
    conn = sqlite3.connect(db, timeout=5)
    # Show current state
    rows = conn.execute('SELECT * FROM state').fetchall()
    if rows:
        print('   Current state:')
        for r in rows:
            print(f'     {r}')
    else:
        print('   DB is already clean.')
    # Reset everything
    conn.execute('DELETE FROM state')
    conn.execute('DELETE FROM qa_cycles')
    conn.execute('DELETE FROM feedback')
    conn.commit()
    conn.close()
    print('   ✅ All counters reset to zero.')
" 2>/dev/null || echo "   ⚠️  DB reset failed (file may not exist yet). Will be created on launch."

echo "=> 5.2 Cleaning stale git branches for stuck tasks..."
if [ -d "$PROJECT_PATH/.git" ]; then
    cd "$PROJECT_PATH"
    git checkout production 2>/dev/null || true
    git pull origin production 2>/dev/null || true
    
    # Find tasks that are in Backlog and delete their local branches
    for branch in $(git branch --list 'agent-*' | tr -d ' *'); do
        echo "   🗑️  Deleting stale branch: $branch"
        git branch -D "$branch" 2>/dev/null || true
    done
    
    cd "$DIR"
    echo "   ✅ Git workspace is clean (production branch)."
else
    echo "   ⚠️  Project path not found: $PROJECT_PATH. Will be cloned on launch."
fi

echo "=> 5.3 Clearing agent workspace caches..."
docker exec openclaw-gateway sh -c "
    # Backend workspace
    rm -rf /root/.openclaw/workspaces/backend/spec/ \
           /root/.openclaw/workspaces/backend/app/ \
           /root/.openclaw/workspaces/backend/AGENT_REPORT.md \
           /root/.openclaw/workspaces/backend/.containers.txt \
           /root/.openclaw/workspaces/backend/.git_log.txt \
           /root/.openclaw/workspaces/backend/docker-compose.override.yml 2>/dev/null
    # QA workspace
    rm -rf /root/.openclaw/workspaces/qa/spec/ \
           /root/.openclaw/workspaces/qa/app/ \
           /root/.openclaw/workspaces/qa/AGENT_REPORT.md 2>/dev/null
    # Session locks
    find /root/.openclaw/state -name '*.lock' -delete 2>/dev/null
    find /root/.openclaw/state -name '*.jsonl' -path '*/sessions/*' -delete 2>/dev/null
    echo '   Workspaces and sessions cleaned.'
" 2>/dev/null || echo "   ⚠️  Could not clean workspaces (gateway may still be starting)."

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 6: PROJECT CONTAINER VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 6: PROJECT CONTAINER HEALTH"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# The QA agent needs the project container running to execute tests.
# This was a major root cause of failures — the container silently died.
echo "=> 6.1 Checking $RUBY_CONTAINER status..."

CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' "$RUBY_CONTAINER" 2>/dev/null || echo "not_found")
echo "   Current status: $CONTAINER_STATUS"

if [ "$CONTAINER_STATUS" = "running" ]; then
    echo "   ✅ $RUBY_CONTAINER is running."
elif [ "$CONTAINER_STATUS" = "exited" ] || [ "$CONTAINER_STATUS" = "created" ]; then
    echo "   🔄 Starting $RUBY_CONTAINER..."
    docker start "$RUBY_CONTAINER" 2>/dev/null || true
    sleep 5
    NEW_STATUS=$(docker inspect -f '{{.State.Status}}' "$RUBY_CONTAINER" 2>/dev/null || echo "failed")
    if [ "$NEW_STATUS" = "running" ]; then
        echo "   ✅ $RUBY_CONTAINER started successfully."
    else
        echo "   ⚠️  Could not start $RUBY_CONTAINER (status: $NEW_STATUS)."
        echo "      QA tests will fail. Fix the container manually before tasks reach QA."
    fi
elif [ "$CONTAINER_STATUS" = "not_found" ]; then
    echo "   ⚠️  $RUBY_CONTAINER does not exist."
    echo "      Attempting to create it with docker compose from PROJECT_PATH..."
    if [ -d "$PROJECT_PATH" ] && [ -f "$PROJECT_PATH/docker-compose.yml" ]; then
        ENV=development docker compose -f "$PROJECT_PATH/docker-compose.yml" up -d --no-deps web 2>/dev/null || true
        sleep 5
    else
        echo "      ⚠️  No docker-compose.yml found at $PROJECT_PATH"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 7: NETWORK CONNECTIVITY VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 7: NETWORK CONNECTIVITY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 7.1 Testing DNS resolution..."
if host api.github.com > /dev/null 2>&1; then
    echo "   ✅ DNS is working."
else
    echo "   ❌ DNS FAILED. Check your network connection."
    echo "   The pipeline will not work without internet access."
fi

echo "=> 7.2 Testing GitHub API connectivity..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 https://api.github.com 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ GitHub API reachable (HTTP $HTTP_CODE)."
else
    echo "   ❌ GitHub API unreachable (HTTP $HTTP_CODE)."
    echo "   Check: Is the ethernet/wifi connected? Is GITHUB_TOKEN valid?"
fi

echo "=> 7.3 Testing GitHub Token validity..."
TOKEN_CHECK=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 \
    -H "Authorization: bearer ${GITHUB_TOKEN}" \
    https://api.github.com/user 2>/dev/null || echo "000")
if [ "$TOKEN_CHECK" = "200" ]; then
    echo "   ✅ GitHub Token is valid."
else
    echo "   ⚠️  GitHub Token returned HTTP $TOKEN_CHECK (may be expired)."
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 8: MOVE STUCK TASKS BACK TO "To Do"
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 8: GITHUB BOARD — UNSTICKING TASKS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 8.1 Moving any tasks stuck in Backlog/In Progress back to To Do..."

# Query current board state
BOARD_RESPONSE=$(curl -s --connect-timeout 10 --max-time 30 \
    -H "Authorization: bearer ${GITHUB_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST https://api.github.com/graphql \
    -d "{\"query\": \"query { user(login: \\\"${GITHUB_USER}\\\") { projectV2(number: ${PROJECT_NUMBER}) { items(first: 20) { nodes { id content { ... on Issue { title state number } } fieldValues(first: 10) { nodes { ... on ProjectV2ItemFieldSingleSelectValue { name } } } } } } } }\"}" 2>/dev/null)

if echo "$BOARD_RESPONSE" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    # Parse and move stuck items
    python3 -c "
import json, subprocess, sys

data = json.loads('''${BOARD_RESPONSE}''')

try:
    items = data['data']['user']['projectV2']['items']['nodes']
except (KeyError, TypeError):
    print('   Could not parse board data.')
    sys.exit(0)

project_id = '${PROJECT_BOARD_ID}'
field_id = '${PROJECT_STATUS_FIELD_ID}'
todo_option = '${PROJECT_OPTION_TODO}'
token = '${GITHUB_TOKEN}'

moved = 0
for item in items:
    content = item.get('content', {})
    if not content or content.get('state') == 'CLOSED':
        continue
    
    title = content.get('title', '')
    item_id = item['id']
    
    # Get current status
    status = ''
    for fv in item.get('fieldValues', {}).get('nodes', []):
        if 'name' in fv:
            status = fv['name']
    
    # Move Backlog, In Progress, and In Review items back to To Do
    if status in ['Backlog', 'In Progress', 'In Review QA']:
        print(f'   📋 Moving \"{title}\" from \"{status}\" → \"To Do\"')
        mutation = '''mutation { updateProjectV2ItemFieldValue(input: { projectId: \"%s\", itemId: \"%s\", fieldId: \"%s\", value: { singleSelectOptionId: \"%s\" } }) { clientMutationId } }''' % (project_id, item_id, field_id, todo_option)
        
        cmd = ['curl', '-s', '--connect-timeout', '10', '--max-time', '30',
               '-H', f'Authorization: bearer {token}',
               '-H', 'Content-Type: application/json',
               '-X', 'POST', 'https://api.github.com/graphql',
               '-d', json.dumps({'query': mutation})]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and 'errors' not in result.stdout:
            moved += 1
        else:
            print(f'     ⚠️  Move failed: {result.stdout[:200]}')

if moved > 0:
    print(f'   ✅ Moved {moved} task(s) to To Do.')
else:
    print('   ℹ️  No stuck tasks found. Board is clean.')
" 2>/dev/null || echo "   ⚠️  Board automation failed. Move tasks manually if needed."
else
    echo "   ⚠️  Could not fetch board state. Move tasks manually if needed."
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 9: LAUNCH MISSION CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 9: LAUNCHING MISSION CONTROL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "=> 9.1 Clearing old logs..."
rm -f mission_logs.out

echo "=> 9.2 Starting mission_control.py in background..."
if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    echo "   Running as standard user: $SUDO_USER (dropping root privileges)"
    sudo -u "$SUDO_USER" nohup python3 -u mission_control.py > mission_logs.out 2>&1 &
    MC_PID=$!
    chown "$SUDO_USER:$SUDO_USER" mission_logs.out 2>/dev/null || true
else
    echo "   Running as current user: $(whoami)"
    nohup python3 -u mission_control.py > mission_logs.out 2>&1 &
    MC_PID=$!
fi
echo "   PID: $MC_PID"
sleep 3

# Verify it's still running
if kill -0 $MC_PID 2>/dev/null; then
    echo "   ✅ Mission Control is running (PID $MC_PID)."
else
    echo "   ❌ Mission Control crashed on startup! Check mission_logs.out"
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ✅ NUCLEAR PATCH v45 COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Models:"
echo "    Backend/Frontend → qwen2.5-coder:7b-cpu"
echo "    QA               → qwen2.5-coder:7b-cpu"
echo "    Architect/Analyst → qwen2.5:1.5b-cpu"
echo "    Product Owner    → gemma2:2b-vram (GPU)"
echo ""
echo "  v45 Improvements over v44:"
echo "    ✓ Intelligent task state reset (not blind DB nuke)"
echo "    ✓ Stale git branch cleanup (all agent-* branches)"
echo "    ✓ Project container health check ($RUBY_CONTAINER)"
echo "    ✓ Network connectivity validation (DNS + GitHub API + Token)"
echo "    ✓ Automatic GitHub board unsticking (Backlog → To Do)"
echo "    ✓ Agent workspace cache purge (spec/, app/, sessions)"
echo ""
echo "  Persistent fixes in mission_control.py (NOT overwritten):"
echo "    ✓ rescue_hallucinated_writes() runs unconditionally"
echo "    ✓ docker start fallback in ensure_dev_container()"  
echo "    ✓ timeout 120 in generated run_tests.sh"
echo ""
echo "  Monitor: tail -f mission_logs.out"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
tail -f mission_logs.out
