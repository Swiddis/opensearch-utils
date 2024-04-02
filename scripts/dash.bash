#!/bin/bash

ROOT=~/Documents/code/dashboards
cd $ROOT

if [ $1 == "up" ]; then
    yarn osd bootstrap --single-version=loose
    yarn start --no-base-path --host=0.0.0.0
    exit 0
fi

git $@

for dir in $ROOT/plugins/*/; do
    echo "=== $(basename $dir) ==="
    cd $dir
    git $@
done
