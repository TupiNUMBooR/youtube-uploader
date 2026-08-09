#!/usr/bin/env bash

set -euo pipefail

started_at=$SECONDS

log() {
    printf '[%(%H:%M:%S)T] %s\n' -1 "$*" >&2
}

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 @channel" >&2
    exit 2
fi

channel=$1
if [[ $channel != @* ]]; then
    echo "Channel must be a YouTube handle starting with @" >&2
    exit 2
fi

for command in ffmpeg magick curl; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command not found: $command" >&2
        exit 1
    fi
done

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output_dir="$repo_dir/user/test"
thumbnail="$output_dir/thumbnail.jpg"
video="$output_dir/video.mp4"
server_url=${SERVER_URL:-http://localhost:8080}

log "Preparing test files in $output_dir"
mkdir -p "$output_dir"

log "Generating thumbnail with ImageMagick"
magick -size 1280x720 xc:white \
    +noise Random \
    -colorspace Gray \
    -quality 90 \
    "$thumbnail"
log "Thumbnail ready: $(du -h "$thumbnail" | cut -f1)"

log "Generating 10-second test video with FFmpeg"
ffmpeg -hide_banner -loglevel warning -stats -y \
    -f lavfi -i "nullsrc=size=320x180:rate=10,noise=alls=100:allf=t+u" \
    -f lavfi -i "anoisesrc=color=white:sample_rate=44100:amplitude=0.1" \
    -t 10 \
    -c:v libx264 -preset fast -crf 28 \
    -c:a aac -b:a 96k \
    -pix_fmt yuv420p -movflags +faststart \
    "$video"
log "Video ready: $(du -h "$video" | cut -f1)"

metadata=$(printf \
    '{"channel":"%s","title":"White noise test","description":"Generated upload test","privacy":"unlisted"}' \
    "$channel")

log "Uploading test video to $channel via $server_url"
curl --fail-with-body --show-error --progress-bar \
    -X POST "$server_url/uploads" \
    -F "metadata=$metadata" \
    -F "video=@$video;type=video/mp4" \
    -F "thumbnail=@$thumbnail;type=image/jpeg"
echo
log "Done in $((SECONDS - started_at)) seconds"
