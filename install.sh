#!/bin/sh
# curl -fsSL https://raw.githubusercontent.com/leoadberg/ladstack/main/install.sh | sh
set -eu

repo="${LADSTACK_REPO:-https://github.com/leoadberg/ladstack.git}"
dir="$HOME/.ladstack"

for tool in git python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ladstack: $tool is required but not installed" >&2
    exit 1
  fi
done

if [ -d "$dir/.git" ]; then
  git -C "$dir" pull -q --ff-only
elif [ -e "$dir" ]; then
  echo "ladstack: $dir exists and is not a git checkout" >&2
  exit 1
else
  git clone -q "$repo" "$dir"
fi

python3 "$dir/tests/test_ladstack.py" -q
exec python3 "$dir/bin/setup.py"
