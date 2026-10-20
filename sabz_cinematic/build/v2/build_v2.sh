#!/bin/bash
# SABZ cinematic v2 (FULL LOGIC): segment builder
set -e
ROOT=~/workspace/goals/ai-championship-adaptive-traffic-signals
F=$ROOT/sabz_cinematic/footage
B=$ROOT/sabz_video/build
V=$ROOT/sabz_cinematic/build/v2
S=$V/work/segs
mkdir -p $S
GRADE="eq=contrast=1.07:brightness=-0.015:saturation=0.90,colorbalance=rs=-0.05:gs=0.01:bs=0.07:rm=-0.01:bm=0.02"
BGRADE="eq=contrast=1.03:saturation=0.97"
ENC="-c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -r 30 -an"

seg () { # name src ss dur grade fadein fadeout
  local name=$1 src=$2 ss=$3 dur=$4 grade=$5 fi=$6 fo=$7
  local fost=$(awk "BEGIN{print $dur - $fo}")
  ffmpeg -v error -ss $ss -i "$src" -t $dur \
    -vf "fps=30,scale=1920:1080,$grade,fade=t=in:st=0:d=$fi,fade=t=out:st=$fost:d=$fo,format=yuv420p" \
    $ENC $S/$name.mp4 -y
  echo "built $name"
}

rawseg () { # name src ss dur fadein fadeout  (no grade, already treated)
  local name=$1 src=$2 ss=$3 dur=$4 fi=$5 fo=$6
  local fost=$(awk "BEGIN{print $dur - $fo}")
  ffmpeg -v error -ss $ss -i "$src" -t $dur \
    -vf "fps=30,scale=1920:1080,fade=t=in:st=0:d=$fi,fade=t=out:st=$fost:d=$fo,format=yuv420p" \
    $ENC $S/$name.mp4 -y
  echo "built $name"
}

cardseg () { # name png dur
  local name=$1 png=$2 dur=$3
  local fost=$(awk "BEGIN{print $dur - 0.4}")
  ffmpeg -v error -loop 1 -i $V/work/cards/$png -t $dur \
    -vf "fps=30,fade=t=in:st=0:d=0.4,fade=t=out:st=$fost:d=0.4,format=yuv420p" \
    $ENC $S/$name.mp4 -y
  echo "built $name"
}

# S1 PROBLEM (26s)
seg s01_gridlock $F/04_aerial_gridlock_dusk.mp4 2 9 "$GRADE" 0.8 0.6
seg s02_redwait  $F/01_red_light_wait_dusk.mp4 3 6.5 "$GRADE" 0.6 0.6
seg s03_hands    $F/03_hands_steering_wheel.mp4 2.5 4 "$GRADE" 0.6 0.6
seg s04_driver   $F/02_driver_in_car.mp4 10 3.5 "$GRADE" 0.6 0.6
cardseg s05_card1 card1.png 3

# S2 THE EYE (19s) - YOLO render, pre-graded
rawseg s06_eye $V/work/eye_render.mp4 0 16 0.6 0.6
cardseg s07_cardeye card_eye.png 3

# S3 THE BRAIN (21s) - real DQN page recording
seg s08_brain $V/work/page@8fe1aa01ea23ca54989eecaaa558e6b3.webm 4 18 "$BGRADE" 0.6 0.6
cardseg s09_cardbrain card_brain.png 3

# S4 THE DECISION (24.9s)
cardseg s10_carddec card_decision.png 2.5
seg s11_battle $B/seg2.mp4 17.9 18 "$BGRADE" 0.5 0.5
seg s12_flow06 $F/06_aerial_flowing_traffic.mp4 1.5 4.5 "$GRADE" 0.6 0.6

# S5 SAFETY (7.5s)
seg s13_safety $F/07_signal_closeup_day.mp4 1 4 "$GRADE" 0.5 0.5
cardseg s14_cardsafe card_safety.png 3.5

# S6 RESULTS (12s)
cardseg s15_stat1 stat1.png 3
cardseg s16_stat2 stat2.png 3
cardseg s17_stat3 stat3.png 3
cardseg s18_stat4 stat4.png 3

# S7 CLOSE (14s)
seg s19_trails $F/09_night_junction_light_trails.mp4 0.5 4.5 "$GRADE" 0.6 0.6
seg s20_flow06b $F/06_aerial_flowing_traffic.mp4 7.8 4 "$GRADE" 0.6 0.8
cardseg s21_final cardF.png 5.5

ls $S
