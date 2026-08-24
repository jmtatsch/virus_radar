#!/bin/bash
set -uo pipefail

# Refreshes the RKI data sets listed in .gitmodules.
#
# Every data set is kept as its own depth-1 clone rather than as a git submodule
# checkout, so neither the image nor the running container has to carry the
# upstream history - that history is roughly 500 MB and keeps growing with every
# fetch, while the data we actually read is a single TSV per repository.
#
# Runs once during the image build and hourly from /etc/cron.d/virus-radar-update.
# A data set that cannot be updated leaves the copy that is already on disk in
# place and does not stop the remaining data sets from being updated; the script
# still exits non-zero so that a failure is visible in the log and fails the
# image build rather than producing an image with no data in it.

APP_DIR="${APP_DIR:-/app}"
# how often to try a single git operation before giving up on a data set
ATTEMPTS="${ATTEMPTS:-3}"

cd "$APP_DIR" || exit 1

# Retry a git operation with a growing pause, so that a brief GitHub outage
# neither fails the image build nor skips an hourly refresh.
retry() {
    local attempt=1
    until "$@"; do
        if [ "$attempt" -ge "$ATTEMPTS" ]; then
            echo "[$(date)] Giving up after $attempt attempts: $*"
            return 1
        fi
        echo "[$(date)] Attempt $attempt failed, retrying in $((attempt * 5))s: $*"
        sleep "$((attempt * 5))"
        attempt=$((attempt + 1))
    done
}

update_data_set() {
    local path="$1"
    local url branch

    url=$(git config -f .gitmodules --get "submodule.${path}.url") || return 1
    branch=$(git config -f .gitmodules --get "submodule.${path}.branch" || echo main)

    if [ -d "$path/.git" ]; then
        echo "[$(date)] Fetching $path from origin/$branch..."
        retry git -C "$path" fetch --depth 1 origin "$branch" || return 1
        git -C "$path" reset --hard "origin/$branch" || return 1
        git -C "$path" clean -fd || return 1
        # the objects the fetch just superseded are unreachable now; drop them so
        # a long running container does not accumulate them fetch after fetch
        git -C "$path" reflog expire --expire=now --all
        git -C "$path" gc --prune=now --quiet
    else
        # no clone yet, or a leftover submodule gitlink from the build context
        echo "[$(date)] Cloning $path from $url..."
        rm -rf "$path.new"
        if ! retry git clone --depth 1 --branch "$branch" "$url" "$path.new"; then
            rm -rf "$path.new"
            return 1
        fi
        # swap only after the clone succeeded, so a failed update keeps the data
        # that is already there instead of leaving the app with nothing to read
        rm -rf "$path"
        mv "$path.new" "$path" || return 1
    fi

    echo "[$(date)] $path at commit $(git -C "$path" rev-parse --short HEAD)" \
         "($(git -C "$path" log -1 --format=%cd --date=short))"
}

echo "[$(date)] Starting data update in $APP_DIR..."

failed=0
while read -r _key path; do
    update_data_set "$path" || {
        echo "[$(date)] Could not update $path, keeping the data already on disk"
        failed=$((failed + 1))
    }
done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$')

if [ "$failed" -gt 0 ]; then
    echo "[$(date)] Data update finished with $failed failed data set(s)"
    exit 1
fi

echo "[$(date)] Data update completed successfully"
