#!/bin/bash
# SABZ cinematic v4: identical to v2 except ONLY the battle segment is the
# new photo battle recording (from build/v3). The brain segment is v2 original.
#   s08_brain  (45.0-63.0s)  <- build/v3/work/segs/s08_brain.mp4  (SABZ panel + DQN line)
#   s11_battle (68.5-86.5s)  <- build/v3/work/segs/s11_battle.mp4 (photo battle, SABZ WINS)
# All other segments are reused untouched from build/v2/work/segs/.
# Assembly follows the documented timestamp trap fix: every segment is first
# normalized through settb/setpts=N/(30*TB) (timestamps rebuilt from frame
# counts) and frame-counted, then joined with the concat FILTER (never the
# concat demuxer + stream copy). Music: the v2 master's audio stream is
# copied bit-exact so the track, fades and sync are unchanged.
# Expected segment frames: 270 195 120 105 90 480 90 540 90 75 540 135 120
#                          105 90 90 90 90 135 120 165  = 3735 (124.5s)
set -e
ROOT=/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals
V2S=$ROOT/sabz_cinematic/build/v2/work/segs
V3=$ROOT/sabz_cinematic/build/v4
N=$V3/work/norm
mkdir -p $N

SEGS="s01_gridlock s02_redwait s03_hands s04_driver s05_card1 s06_eye s07_cardeye s08_brain s09_cardbrain s10_carddec s11_battle s12_flow06 s13_safety s14_cardsafe s15_stat1 s16_stat2 s17_stat3 s18_stat4 s19_trails s20_flow06b s21_final"

for s in $SEGS; do
  if [ "$s" = "s11_battle" ]; then SRC=$ROOT/sabz_cinematic/build/v3/work/segs/$s.mp4; else SRC=$V2S/$s.mp4; fi
  ffmpeg -v error -i "$SRC" -vf "settb=AVTB,setpts=N/(30*TB),setsar=1" \
    -c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -r 30 -an -video_track_timescale 16000 $N/$s.mp4 -y
  echo "normalized $s"
done

echo "--- frame counts (must match the expected list, total 3735) ---"
TOTAL=0
for s in $SEGS; do
  C=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 $N/$s.mp4)
  echo "$s: $C"
  TOTAL=$((TOTAL+C))
done
echo "TOTAL: $TOTAL"
[ "$TOTAL" = "3735" ] || { echo "FRAME COUNT MISMATCH - ABORT"; exit 1; }

# concat filter + original v2 audio (stream copy), master encode crf17 medium
ARGS=""
IDX=0
for s in $SEGS; do ARGS="$ARGS -i $N/$s.mp4"; IDX=$((IDX+1)); done
FC=""
for i in $(seq 0 20); do FC="$FC[$i:v]setsar=1[a$i];"; done
FC="$FC"
JOIN=""
for i in $(seq 0 20); do JOIN="$JOIN[a$i]"; done
FC="$FC$JOIN"
FC="${FC}concat=n=21:v=1:a=0[v]"

ffmpeg -v error $ARGS -i $ROOT/sabz_cinematic/SABZ_Cinematic_v2.mp4 \
  -filter_complex "$FC" -map "[v]" -map 21:a \
  -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -r 30 -video_track_timescale 16000 \
  -c:a copy -movflags +faststart $ROOT/sabz_cinematic/SABZ_Cinematic_v4.mp4 -y
echo "MASTER DONE"

# web version: 720p crf26, aac 128k (same recipe as v2_web)
ffmpeg -v error -i $ROOT/sabz_cinematic/SABZ_Cinematic_v4.mp4 \
  -vf "scale=1280:720" -c:v libx264 -preset medium -crf 26 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart $ROOT/sabz_cinematic/SABZ_Cinematic_v4_web.mp4 -y
echo "WEB DONE"
ls -la $ROOT/sabz_cinematic/SABZ_Cinematic_v4.mp4 $ROOT/sabz_cinematic/SABZ_Cinematic_v4_web.mp4
