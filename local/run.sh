#!/bin/bash

cd "$(dirname "$0")"
mkdir -p build
rsync -va Dockerfile build
rsync -va ../src/ build
rsync -va ../static build

docker build -t juncture-iiif build
docker run -it -p 8000:8000 --env-file aws-creds juncture-iiif

rm -rf build