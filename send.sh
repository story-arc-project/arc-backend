#!/bin/bash
cd "$(dirname "$0")" || exit 1
WORKDIRNAME="~/arc-backend"
SSHNAME="archive"
ssh $SSHNAME "mkdir -p $WORKDIRNAME"
rsync -avr --delete --exclude={'.venv','__pycache__','.pytest_cache','*.md','*.log'} --files-from sendfiles.txt ./ $SSHNAME:$WORKDIRNAME
