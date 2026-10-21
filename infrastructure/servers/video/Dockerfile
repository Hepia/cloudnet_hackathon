# RTSP/RTP video server (MediaMTX with ffmpeg). Three test videos are rendered at build time;
# each RTSP path starts an ffmpeg publisher on demand, i.e. when a client requests it.
FROM bluenviron/mediamtx:1.21.2-ffmpeg
COPY make-videos.sh /make-videos.sh
RUN sh /make-videos.sh /videos
COPY mediamtx.yml /mediamtx.yml
