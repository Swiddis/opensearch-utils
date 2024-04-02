#!/bin/bash

ROOT=~/Documents/code/dashboards
cd $ROOT

git $@

for dir in $ROOT/plugins/*/;
do
    echo "=== $(basename $dir) ==="
    cd $dir
    git $@
done
