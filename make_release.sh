#!/bin/bash
# Builds the two files you install from:
#   dist/lidsense-v2.zip          -> copy to the Raspberry Pi (setup guide, Step 5)
#   dist/lidsense-web-upload.zip  -> upload to Hostinger public_html (setup guide, Step 4)
set -e
cd "$(dirname "$0")"
./build_server.sh
rm -rf dist && mkdir -p dist
git archive --format=zip --prefix=lidsense/ -o dist/lidsense-v2.zip HEAD
(cd server/public_html && zip -qr ../../dist/lidsense-web-upload.zip lidsense -x 'lidsense/api/config.php')
echo "Built: dist/lidsense-v2.zip and dist/lidsense-web-upload.zip"
