#!/bin/bash
# UserPromptSubmit hook: Scan prompt for secrets before sending

if ! command -v sonar &> /dev/null; then
  exit 0
fi

# Read JSON from stdin
stdin_data=$(cat)

# Extract prompt field using sed
prompt=$(echo "$stdin_data" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

if [[ -z "$prompt" ]]; then
  exit 0
fi

# Create temporary file with prompt content (stdin is already occupied by hook input)
temp_file=$(mktemp -t 'sonarqube-cli-hook.XXXXXX')
trap "rm -f $temp_file" EXIT

echo -n "$prompt" > "$temp_file"

# Scan prompt for secrets (using file instead of stdin pipe)
sonar analyze secrets "$temp_file" > /dev/null 2>&1
exit_code=$?

if [[ $exit_code -eq 51 ]]; then
  # Secrets found - block prompt
  reason="Sonar detected secrets in prompt"
  echo "{\"decision\":\"block\",\"reason\":\"$reason\"}"
  exit 0
fi

exit 0
