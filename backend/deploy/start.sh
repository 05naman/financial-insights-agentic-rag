#!/bin/sh
# The container disk is read-only data plus a scratch /tmp: give the embedded index a writable copy.
set -e
rm -rf /tmp/qdrant
cp -r /app/seed/qdrant /tmp/qdrant
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
