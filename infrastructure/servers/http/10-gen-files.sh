#!/bin/sh
# Runs from the nginx image entrypoint before nginx starts: creates the download files
# (random bytes, so they are not compressible) and an index page.
set -e
dir=/usr/share/nginx/html/files
mkdir -p "$dir"
bytes() {
  n=${1%[kKmM]}
  case $1 in *k|*K) echo $((n * 1024)) ;; *m|*M) echo $((n * 1048576)) ;; *) echo "$n" ;; esac
}
for size in ${HTTP_FILE_SIZES:-1k 10k 100k 1m 10m 100m}; do
  f="$dir/$size.bin"
  [ -s "$f" ] || head -c "$(bytes "$size")" /dev/urandom > "$f"
done
{
  echo "<html><body><h1>lab5g HTTP server</h1><ul>"
  for f in "$dir"/*.bin; do b=$(basename "$f"); echo "<li><a href=\"/files/$b\">$b</a> ($(stat -c %s "$f") bytes)</li>"; done
  echo "</ul></body></html>"
} > /usr/share/nginx/html/index.html
ls -l "$dir"
