#!/bin/bash
cd /root/Dashboard/webapp/keydrop
nohup python3 dashboard.py > dashboard.log 2>&1 &
echo "Dashboard started on port 5000"
echo "Access it at: http://YOUR_SERVER_IP:5000"
