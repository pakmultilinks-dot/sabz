#!/bin/bash
set -e
cd "$(dirname "$0")"
ROOT=/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals
A=assets
FOOT=$ROOT/sabz_cinematic/footage
WEBM=$(ls raw/*.webm | head -1)
ENC="-c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p -r 30 -video_track_timescale 30"
mkdir -p seg

# 1. TITLE (6s) fade in from black 0.7
ffmpeg -v error -loop 1 -i $A/card_title.png -vf "fade=t=in:st=0:d=0.7,format=yuv420p" -t 6 $ENC seg/s1.mp4 -y

# 2a. PROBLEM gridlock (7s)
ffmpeg -v error -ss 5 -i $FOOT/04_aerial_gridlock_dusk.mp4 -loop 1 -i $A/ov_problem1.png \
  -filter_complex "[0:v]fps=30,scale=1920:1080[bg];[1:v]format=rgba,fade=t=in:st=0.4:d=0.7:alpha=1,fade=t=out:st=6.0:d=0.7:alpha=1[ov];[bg][ov]overlay=0:0,format=yuv420p[v]" \
  -map "[v]" -t 7 $ENC seg/s2a.mp4 -y
# 2b. PROBLEM red light wait (7s)
ffmpeg -v error -ss 8 -i $FOOT/01_red_light_wait_dusk.mp4 -loop 1 -i $A/ov_problem2.png \
  -filter_complex "[0:v]fps=30,scale=1920:1080[bg];[1:v]format=rgba,fade=t=in:st=0.4:d=0.7:alpha=1,fade=t=out:st=6.0:d=0.7:alpha=1[ov];[bg][ov]overlay=0:0,format=yuv420p[v]" \
  -map "[v]" -t 7 $ENC seg/s2b.mp4 -y

# 3. BATTLE recording (30s): webm 65->95s, scale/crop into frame, caption bar
ffmpeg -v error -ss 65 -i "$WEBM" -loop 1 -i $A/ov_battle.png \
  -filter_complex "[0:v]fps=30,scale=1920:1176:flags=lanczos,crop=1920:1008:0:97,pad=1920:1080:0:0:color=0x0B1220[bg];[bg][1:v]overlay=0:0,format=yuv420p[v]" \
  -map "[v]" -t 30 $ENC seg/s3.mp4 -y

# 4. HOW IT WORKS beats (3s each)
for i in 1 2 3; do
  ffmpeg -v error -loop 1 -i $A/card_beat$i.png -vf "format=yuv420p" -t 3 $ENC seg/s4_$i.mp4 -y
done
ffmpeg -v error -ss 2 -i $FOOT/06_aerial_flowing_traffic.mp4 -loop 1 -i $A/ov_melt.png \
  -filter_complex "[0:v]fps=30,scale=1920:1080[bg];[bg][1:v]overlay=0:0,format=yuv420p[v]" \
  -map "[v]" -t 3 $ENC seg/s4_4.mp4 -y

# 5. RESULTS (12s)
ffmpeg -v error -loop 1 -i $A/card_results.png -vf "fade=t=in:st=0:d=0.5,fade=t=out:st=11.5:d=0.5,format=yuv420p" -t 12 $ENC seg/s5.mp4 -y

# 6. CLOSE (6s) same title card, fade out to black last 0.7s
ffmpeg -v error -loop 1 -i $A/card_title.png -vf "fade=t=out:st=5.3:d=0.7,format=yuv420p" -t 6 $ENC seg/s6.mp4 -y

# concat parts
printf "file 's2a.mp4'\nfile 's2b.mp4'\n" > seg/list2.txt
ffmpeg -v error -f concat -safe 0 -i seg/list2.txt -c copy seg/s2.mp4 -y
printf "file 's4_1.mp4'\nfile 's4_2.mp4'\nfile 's4_3.mp4'\nfile 's4_4.mp4'\n" > seg/list4.txt
ffmpeg -v error -f concat -safe 0 -i seg/list4.txt -c copy seg/s4.mp4 -y

# FINAL concat + music (trim 0-80, fades at seam, moderate level)
printf "file 's1.mp4'\nfile 's2.mp4'\nfile 's3.mp4'\nfile 's4.mp4'\nfile 's5.mp4'\nfile 's6.mp4'\n" > seg/list_all.txt
ffmpeg -v error -f concat -safe 0 -i seg/list_all.txt -i $ROOT/sabz_cinematic/build/v2/heart_of_nowhere.mp3 \
  -filter_complex "[1:a]atrim=0:80,afade=t=in:st=0:d=1.5,afade=t=out:st=77.5:d=2.5,volume=0.45[a]" \
  -map 0:v -map "[a]" -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k -movflags +faststart -shortest $ROOT/sabz_cinematic/SABZ_Monitor_Loop.mp4 -y
echo "BUILD DONE"
