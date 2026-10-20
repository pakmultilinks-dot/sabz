#!/bin/bash
# SABZ cinematic edit: segment builder
set -e
F=~/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/footage
B=~/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_video/build
S=/tmp/cine/segs
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

cardseg () { # name png dur
  local name=$1 png=$2 dur=$3
  local fost=$(awk "BEGIN{print $dur - 0.4}")
  ffmpeg -v error -loop 1 -i /tmp/cine/cards/$png -t $dur \
    -vf "fps=30,fade=t=in:st=0:d=0.4,fade=t=out:st=$fost:d=0.4,format=yuv420p" \
    $ENC $S/$name.mp4 -y
  echo "built $name"
}

# S1 COLD OPEN - THE PROBLEM (28s)
seg s01_gridlock $F/04_aerial_gridlock_dusk.mp4 2 10 "$GRADE" 0.8 0.6
seg s02_redwait  $F/01_red_light_wait_dusk.mp4 3 7 "$GRADE" 0.6 0.6
seg s03_hands    $F/03_hands_steering_wheel.mp4 2.5 4.5 "$GRADE" 0.6 0.6
seg s04_driver   $F/02_driver_in_car.mp4 10 3.5 "$GRADE" 0.6 0.6
cardseg s05_card1 card1.png 3

# S2 THE WASTE (14s, hard cuts)
seg s06_redwait2 $F/01_red_light_wait_dusk.mp4 12.5 3 "$GRADE" 0.05 0.05
seg s07_empty11  $F/11_aerial_empty_intersection.mp4 5 3 "$GRADE" 0.05 0.05
seg s08_redwait3 $F/01_red_light_wait_dusk.mp4 18 2.5 "$GRADE" 0.05 0.05
seg s09_empty10  $F/10_aerial_empty_roads.mp4 6 2.5 "$GRADE" 0.05 0.05
cardseg s10_card2 card2.png 3

# S3 THE TURN (9s)
seg s11_redsig   $F/07_signal_closeup_day.mp4 8 2 "$GRADE" 0.3 0.4
seg s12_pedgreen $F/08_ped_signal_countdown.mp4 2.5 4.3 "$GRADE" 0.4 0.4
cardseg s13_sabz card3.png 2.7

# S4 THE PROOF (34.9s)
seg s14_battleA  $B/seg2.mp4 8 12 "$BGRADE" 0.5 0.5
seg s15_flow06   $F/06_aerial_flowing_traffic.mp4 1.5 5 "$GRADE" 0.6 0.6
seg s16_battleB  $B/seg2.mp4 23 12.9 "$BGRADE" 0.5 0.5
seg s17_trails09 $F/09_night_junction_light_trails.mp4 0.5 5 "$GRADE" 0.6 0.6

# S5 RESULTS (12.8s)
cardseg s18_stat1 stat1.png 3.2
cardseg s19_stat2 stat2.png 3.2
cardseg s20_stat3 stat3.png 3.2
cardseg s21_stat4 stat4.png 3.2

# S6 CLOSE (11.8s)
seg s22_flow06b  $F/06_aerial_flowing_traffic.mp4 7.8 5.8 "$GRADE" 0.6 0.8
cardseg s23_final cardF.png 6

ls -la $S
