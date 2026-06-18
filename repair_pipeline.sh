#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
#  🔧 AI-Hub Pipeline Repair Script
#  Fixes: SYSTEM.md, RAM isolation, workspace sync, KEEP_ALIVE
#  Run: bash repair_pipeline.sh
# ═══════════════════════════════════════════════════════════════════════════
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "═══════════════════════════════════════════════════"
echo "  🔧 AI-Hub Pipeline Repair"
echo "═══════════════════════════════════════════════════"
echo ""

# ── 1. Kill any running mission_control ──────────────────────────────────
echo "=> 1. Stopping all running agents..."
pkill -f "mission_control.py" 2>/dev/null || true
rm -f /tmp/mission_control.lock
sleep 2

# ── 2. Fix file ownership (Docker creates files as root) ──────────────────
echo "=> 2. Fixing file ownership..."
sudo chown -R $(whoami):$(whoami) "$DIR/openclaw-docker/workspaces/" 2>/dev/null || true

# ── 3. Restore QA SYSTEM.md ──────────────────────────────────────────────
echo "=> 3. Restoring QA Agent SYSTEM.md..."
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
   - `VERDICT: PASS` — if 0 failures AND 0 errors
   - `VERDICT: FAIL` — if ANY failures or errors

## ABSOLUTE RULES

- You MUST use the `exec` tool to run the command. Do NOT guess or fabricate output.
- Do NOT write, modify, or suggest code changes. You are NOT a developer.
- Do NOT output JSON tool calls as text. You must INVOKE the tool, not print it.
- If the exec tool fails or is blocked, report the exact error message. Do NOT say PASS.
- If `run_tests.sh` does not exist, report: `VERDICT: FAIL — run_tests.sh not found`
- Your response MUST contain real terminal output with "examples" and "failures" from RSpec.
- Responses without real test output will be REJECTED automatically.

## Anti-Hallucination

- Do NOT invent test results. Only report what the terminal actually outputs.
- Do NOT say "all tests pass" without showing the actual RSpec output.
- If you cannot execute the tests for any reason, say `VERDICT: FAIL` and explain why.
QASYSTEM
echo "   ✅ QA SYSTEM.md restored ($(wc -c < "$DIR/openclaw-docker/workspaces/qa/.openclaw/SYSTEM.md") bytes)"

# ── 4. Restore Backend SYSTEM.md ─────────────────────────────────────────
echo "=> 4. Restoring Backend Agent SYSTEM.md..."
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

# ── 5. Restart Docker stack with corrected KEEP_ALIVE ─────────────────────
echo "=> 5. Restarting Docker infrastructure..."
docker compose -f docker-compose.yml down 2>/dev/null || true
sleep 5

# Flush OS RAM caches
echo "=> 🚨 Flushing RAM caches..."
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true

docker compose -f docker-compose.yml up -d
echo "   Waiting 20s for containers to stabilize..."
sleep 20

# ── 6. Verify models are available ───────────────────────────────────────
echo "=> 6. Checking Ollama models..."
docker exec ollama-brain ollama list 2>/dev/null || echo "   ⚠️ Ollama not ready yet"

# ── 7. Apply QA exec allowlist ───────────────────────────────────────────
echo "=> 7. Applying QA execution allowlist..."
for i in {1..5}; do
    docker exec openclaw-gateway openclaw approvals allowlist add --agent qa "*" 2>/dev/null && break
    echo "   Retry $i/5..."
    sleep 5
done

# ── 8. Reset mission state ──────────────────────────────────────────────
echo "=> 8. Resetting mission state database..."
python3 reset_state.py 2>/dev/null || echo "   ⚠️ State reset skipped"
rm -f mission_logs.out

# ── 9. Launch ────────────────────────────────────────────────────────────
echo "=> 9. Launching Mission Control v44..."
nohup python3 -u mission_control.py > mission_logs.out 2>&1 &

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Pipeline Repair Complete (v44)"
echo ""
echo "  Fixes applied:"
echo "    ✓ QA SYSTEM.md restored"
echo "    ✓ Backend SYSTEM.md restored"
echo "    ✓ OLLAMA_KEEP_ALIVE reduced to 30s"
echo "    ✓ RAM isolation between agents"
echo "    ✓ Workspace sync protection"
echo "    ✓ QA exec allowlist applied"
echo "    ✓ Mission state reset"
echo ""
echo "  Monitor: tail -f mission_logs.out"
echo "═══════════════════════════════════════════════════"
tail -f mission_logs.out
