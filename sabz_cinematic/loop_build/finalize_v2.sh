#!/bin/bash
# Final assembly for SABZ_Monitor_Loop.mp4 v2 (expo loop standard).
# Same trap as v1 applies: NEVER stream-copy concat then filter; normalize
# every segment through settb/setpts=N/(30*TB) (timestamps rebuilt from frame
# counts) and join with the concat FILTER, or frames silently vanish.
# Segment frame counts (verified before assembly):
#   sting 150, gridlock 210, redwait 180, battle 840, beats 243,
#   results 315, cta 150, sting 150  = 2238 frames = 74.6s
set -e
cd "$(dirname "$0")"
ROOT=/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals

norm() { # $1 src $2 dst $3 fade-in-start $4 fade-out-start
  ffmpeg -v error -i "seg2/$1" -vf "settb=AVTB,setpts=N/(30*TB),setsar=1,fade=t=in:st=0:d=0.35,fade=t=out:st=$4:d=0.35" \
    -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -video_track_timescale 15360 "seg2/$2" -y
}
# sting head: slower fade from black at the very start (loop seam)
ffmpeg -v error -i seg2/v2_s1_sting.mp4 -vf "settb=AVTB,setpts=N/(30*TB),setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st=4.65:d=0.35" \
  -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -video_track_timescale 15360 seg2/n_sting_head.mp4 -y
# sting tail: fades back to black at the very end (loop seam)
ffmpeg -v error -i seg2/v2_s1_sting.mp4 -vf "settb=AVTB,setpts=N/(30*TB),setsar=1,fade=t=in:st=0:d=0.35,fade=t=out:st=4.4:d=0.6" \
  -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -video_track_timescale 15360 seg2/n_sting_tail.mp4 -y
norm v2_s2_gridlock.mp4 n_gridlock.mp4 0 6.65
norm v2_s3_redwait.mp4  n_redwait.mp4  0 5.65
norm v2_s4_battle.mp4   n_battle.mp4   0 27.65
norm v2_s5_beats.mp4    n_beats.mp4    0 7.75
norm v2_s6_results.mp4  n_results.mp4  0 10.15
norm v2_s7_cta.mp4      n_cta.mp4      0 4.65

ffmpeg -v error \
  -i seg2/n_sting_head.mp4 -i seg2/n_gridlock.mp4 -i seg2/n_redwait.mp4 -i seg2/n_battle.mp4 \
  -i seg2/n_beats.mp4 -i seg2/n_results.mp4 -i seg2/n_cta.mp4 -i seg2/n_sting_tail.mp4 \
  -i $ROOT/sabz_cinematic/build/v2/heart_of_nowhere.mp3 \
  -filter_complex "[0:v]setsar=1[a0];[1:v]setsar=1[a1];[2:v]setsar=1[a2];[3:v]setsar=1[a3];[4:v]setsar=1[a4];[5:v]setsar=1[a5];[6:v]setsar=1[a6];[7:v]setsar=1[a7];[a0][a1][a2][a3][a4][a5][a6][a7]concat=n=8:v=1:a=0[v];[8:a]atrim=0:74.6,afade=t=in:st=0:d=1.5,afade=t=out:st=72.1:d=2.5,volume=0.4[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k -movflags +faststart $ROOT/sabz_cinematic/SABZ_Monitor_Loop.mp4 -y
echo "FINALIZED v2: expect duration 74.6, frames 2238"
