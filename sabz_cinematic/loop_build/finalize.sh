#!/bin/bash
# Final assembly for SABZ_Monitor_Loop.mp4 (as executed 2026-10-21).
# build_loop.sh creates seg/s1..s6.mp4. Two gotchas found the hard way:
#  1. Segments built with -ss input-seeking + concat-demuxer stream copy carry
#     timestamp offsets/duplicates. A 6-input concat FILTER then silently
#     drops frames (first attempt: 58.9s of video in an 80s file).
#  2. s4 in particular (stream-copy concat of 4 beats) loses frames on any
#     filtered re-encode; it must be rebuilt via the concat FILTER (below).
# Fix: normalize every segment through setpts (timestamps rebuilt from frame
# counts), rebuild s4 via filter-concat, then concat-filter the six parts.
set -e
cd "$(dirname "$0")"
ROOT=/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals

ffmpeg -v error -i seg/s4_1.mp4 -i seg/s4_2.mp4 -i seg/s4_3.mp4 -i seg/s4_4.mp4 \
  -filter_complex "[0:v]settb=AVTB,setpts=N/(30*TB),setsar=1[a];[1:v]settb=AVTB,setpts=N/(30*TB),setsar=1[b];[2:v]settb=AVTB,setpts=N/(30*TB),setsar=1[c];[3:v]settb=AVTB,setpts=N/(30*TB),setsar=1[d];[a][b][c][d]concat=n=4:v=1:a=0[v]" \
  -map "[v]" -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -video_track_timescale 15360 seg/n_s4.mp4 -y
for s in s1 s2 s3 s5 s6; do
  ffmpeg -v error -i seg/$s.mp4 -vf "settb=AVTB,setpts=N/(30*TB),setsar=1" \
    -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -video_track_timescale 15360 seg/n_$s.mp4 -y
done
# frame counts must read 180/420/900/360/360/180 (=2400) before continuing

ffmpeg -v error -i seg/n_s1.mp4 -i seg/n_s2.mp4 -i seg/n_s3.mp4 -i seg/n_s4.mp4 -i seg/n_s5.mp4 -i seg/n_s6.mp4 \
  -i $ROOT/sabz_cinematic/build/v2/heart_of_nowhere.mp3 \
  -filter_complex "[0:v]setsar=1[a0];[1:v]setsar=1[a1];[2:v]setsar=1[a2];[3:v]setsar=1[a3];[4:v]setsar=1[a4];[5:v]setsar=1[a5];[a0][a1][a2][a3][a4][a5]concat=n=6:v=1:a=0[v];[6:a]atrim=0:80,afade=t=in:st=0:d=1.5,afade=t=out:st=77.5:d=2.5,volume=0.45[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k -movflags +faststart $ROOT/sabz_cinematic/SABZ_Monitor_Loop.mp4 -y
echo "FINALIZED: expect duration 80.0, frames 2400"
