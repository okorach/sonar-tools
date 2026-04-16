#!/bin/bash
# PreToolUse hook: Scan files before reading to prevent secret leakage
# Blocks file reads if secrets are detected

if ! command -v sonar &> /dev/null; then
  exit 0
fi

# Read JSON from stdin and extract fields using sed (handles both compact and pretty-printed JSON)
stdin_data=$(cat)
tool_name=$(echo "$stdin_data" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

if [[ "$tool_name" != "Read" ]]; then
  exit 0
fi

file_path=$(echo "$stdin_data" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

if [[ -z "$file_path" ]] || [[ ! -f "$file_path" ]]; then
  exit 0
fi

# Scan file for secrets
sonar analyze secrets "$file_path" > /dev/null 2>&1
exit_code=$?

if [[ $exit_code -eq 51 ]]; then
  # Secrets found - deny file read
  reason="Sonar detected secrets in file: $file_path"
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$reason\"}}"
  exit 0
fi

exit 0
