#!/bin/sh
set -e

# to sensure redis server is always up and running
service redis-server start > /dev/null


task $@