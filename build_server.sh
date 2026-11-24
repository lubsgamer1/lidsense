#!/bin/bash
# Copies the shared dashboard and the schema into the web folder you upload to the host.
set -e
cd "$(dirname "$0")"
W=server/public_html/lidsense
cp frontend/index.html "$W/"
mkdir -p "$W/assets" && cp frontend/assets/* "$W/assets/"
cp server/sql/schema.sql "$W/api/schema.sql"
echo "Web folder ready: $W"
