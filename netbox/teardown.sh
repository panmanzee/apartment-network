#!/bin/bash
# remove the test NetBox stack and its volumes
cd "$(dirname "$0")"
docker compose down -v
