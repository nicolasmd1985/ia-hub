#!/bin/bash
pkill -f mission_control.py && pkill -f run_mission_control.sh
bash apply_nuclear_patch.sh
nohup bash run_mission_control.sh > mission_logs_v23.out 2>&1 &
tail -f mission_logs_v23.out
