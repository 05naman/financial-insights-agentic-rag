#!/bin/sh
# Build the two folders the Docker image copies in. Run from backend/ after ingesting the reports
# into a FRESH index (see docs/deploy-cloud-run.md, step 3).
set -e
[ -d deploy/qdrant ] || { echo "deploy/qdrant is missing: ingest first with QDRANT_PATH=./deploy/qdrant"; exit 1; }
rm -rf deploy/models
mkdir -p deploy/models
# only the two search models; the slow reranker is off and stays out of the image
cp -r data/models/models--Qdrant--bge-small-en-v1.5-onnx-Q deploy/models/
cp -r data/models/models--Qdrant--bm25 deploy/models/
du -sh deploy/models deploy/qdrant
