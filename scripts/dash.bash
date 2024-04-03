#!/bin/bash

ROOT=~/Documents/code/dashboards
cd $ROOT

# Helper method to check for param https://stackoverflow.com/a/56431189/7543069
has_param() {
    local term="$1"
    shift
    for arg; do
        if [[ $arg == "$term" ]]; then
            return 0
        fi
    done
    return 1
}

if [ $1 == "up" ]; then
    shift 1
    if ! has_param "--no-bootstrap" "$@"; then
        yarn osd bootstrap --single-version=loose
    fi
    yarn start --no-base-path --host=0.0.0.0
    exit 0
fi

git $@

for dir in $ROOT/plugins/*/; do
    echo "=== $(basename $dir) ==="
    cd $dir
    git $@
done