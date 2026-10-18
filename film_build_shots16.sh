#!/bin/bash
# Build shots 1 (logo intro) and 6 (outro) with ffmpeg. Silent.
set -e
WORK=~/workspace/goals/ai-championship-adaptive-traffic-signals
OUT=$WORK/film_frames
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
LOGO=$WORK/logo.png
mkdir -p "$OUT"

# ---- SHOT 1: logo intro, 6s ----
ffmpeg -y -v error \
  -f lavfi -i "color=black:s=1280x720:d=6:r=24" \
  -loop 1 -i "$LOGO" \
  -filter_complex "\
[1:v]scale=760:-1,format=rgba,fade=t=in:st=0.5:d=1.5:alpha=1,fade=t=out:st=5.2:d=0.8:alpha=1[logo];\
[0:v][logo]overlay=(W-w)/2:(H-h)/2-50,format=yuv420p[bg];\
[bg]drawtext=fontfile=$FONT:text='ADAPTIVE TRAFFIC AI':fontsize=38:fontcolor=0x00E676:\
x=(w-text_w)/2:y=h*0.70:alpha='if(lt(t,3),0,if(lt(t,4.5),(t-3)/1.5,1))'[out]" \
  -map "[out]" -c:v libx264 -pix_fmt yuv420p -r 24 -t 6 $OUT/shot1.mp4
echo "shot1 done"

# ---- SHOT 6: outro, 8s ----
ffmpeg -y -v error \
  -f lavfi -i "color=black:s=1280x720:d=8:r=24" \
  -loop 1 -i "$LOGO" \
  -filter_complex "\
[1:v]scale=880:-1,format=rgba,fade=t=in:st=0.5:d=1.5:alpha=1[logo];\
[0:v][logo]overlay=(W-w)/2:(H-h)/2-110,format=yuv420p[bg];\
[bg]drawtext=fontfile=$FONT:text='TEAM SABZ':fontsize=54:fontcolor=white:\
x=(w-text_w)/2:y=h*0.62:alpha='if(lt(t,2.5),0,if(lt(t,4),(t-2.5)/1.5,1))',\
drawtext=fontfile=$FONT:text='LAHORE GARRISON UNIVERSITY':fontsize=30:fontcolor=0x9aa4b2:\
x=(w-text_w)/2:y=h*0.62+72:alpha='if(lt(t,3.5),0,if(lt(t,5),(t-3.5)/1.5,1))',\
fade=t=out:st=6.5:d=1.5[out]" \
  -map "[out]" -c:v libx264 -pix_fmt yuv420p -r 24 -t 8 $OUT/shot6.mp4
echo "shot6 done"
