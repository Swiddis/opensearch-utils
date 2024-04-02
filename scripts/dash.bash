#!/bin/bash

ROOT=~/Documents/code/dashboards
cd $ROOT

git $@

for dir in $ROOT/plugins/*/;
do
    cd $dir
    git $@
done
