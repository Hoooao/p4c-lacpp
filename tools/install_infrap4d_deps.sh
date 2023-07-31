#!/bin/bash
set -e

# This script should only be used in Ubuntu22.04

DEPS="libabsl-dev \
      libc-ares-dev=1.18.1-1ubuntu0.22.04.2 \
      libcctz-dev \
      libgflags-dev \
      libgoogle-glog-dev \
      libgrpc++-dev \
      libgtest-dev=1.11.0-3 \
      nlohmann-json3-dev \
      libprotobuf-dev \
      protobuf-compiler \
      zlib1g-dev"

sudo apt-get update
sudo apt-get install -y ${DEPS}









