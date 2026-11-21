#!/bin/bash
# clean deploy -> tests -> destroy (log is written by tests/run.sh into results/)
cd "$(dirname "$0")"
bash destroy.sh >/dev/null 2>&1
bash deploy.sh > results/deploy.log 2>&1 || { tail -30 results/deploy.log; exit 2; }
sleep 3
bash tests/run.sh; rc=$?
bash destroy.sh >results/destroy.log 2>&1
exit $rc
