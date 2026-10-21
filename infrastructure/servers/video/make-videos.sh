#!/bin/sh
# make-videos.sh <dir>: renders three H.264/AAC test videos (moving test pattern and a tone).
set -e
out=${1:-/videos}
mkdir -p "$out"
gen() { # name size fps bitrate
  echo "rendering $1 ($2 @ $3 fps, $4)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=$2:rate=$3" -f lavfi -i "sine=frequency=440:sample_rate=48000" \
    -t 60 -c:v libx264 -preset veryfast -tune zerolatency -b:v "$4" -maxrate "$4" -bufsize "$4" \
    -pix_fmt yuv420p -g "$3" -c:a aac -b:a 64k "$out/$1.mp4"
}
gen low    320x240  15 300k
gen medium 640x480  25 1000k
gen high   1280x720 30 3000k
ls -l "$out"
