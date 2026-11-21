#!/bin/bash
# runs on the PC (WSL): start NetBox, load twice, export, tear down
cd "$(dirname "$0")"
D=$(date +%F)
mkdir -p results
LOG=results/import-$D.log
TOKEN=0123456789abcdef0123456789abcdef01234567
{
echo "# NetBox import test $D, image netboxcommunity/netbox:v4.7-5.1.2, simulated data"
bash teardown.sh >/dev/null 2>&1
docker compose up -d 2>&1 | tail -5
for i in $(seq 1 80); do curl -s -m 3 -o /dev/null http://localhost:8010/login/ && break; sleep 5; done
echo "netbox up after $i checks"
docker exec -i bcr-netbox-netbox-1 /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell < mktoken.py 2>&1 | grep "^token"
echo "## run 1"
python3 load.py --url http://localhost:8010 --token $TOKEN || echo "load run 1 FAILED"
echo "## run 2"
python3 load.py --url http://localhost:8010 --token $TOKEN --export results/export-$D.json || echo "load run 2 FAILED"
docker logs bcr-netbox-netbox-1 2>&1 | grep -E "Traceback| 500 " | head -5
bash teardown.sh 2>&1 | tail -6
echo "## stack removed, containers left on PC:"
docker ps --format '{{.Names}}'
} 2>&1 | tee $LOG
