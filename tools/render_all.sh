#!/bin/zsh
# Render and encode the intro: tools/render_all.sh mock|final [layout-light ...]
# Mocks are 30 fps, the final is 60 fps.
set -e
cd "${0:A:h}/.."
quality=$1; shift
variants=("$@")
if [[ $quality == mock ]]; then fps=30; else fps=60; fi
(( $#variants )) || variants=(equal-reflect)
blender=/Applications/Blender.app/Contents/MacOS/Blender
for v in $variants; do
  layout=${v%-*}; light=${v#*-}
  dir=frames/$v-$quality
  rm -f $dir/[0-9]*.png(N)
  start=$(date +%s)
  $blender -b --factory-startup -P build.py -- --layout $layout --light $light --quality $quality --fps $fps --render > logs/$v-$quality.txt 2>&1
  echo "$v: rendered in $(( $(date +%s) - start )) s"
  if [[ $quality == mock ]]; then
    out=mockups/i10-intro-$v-mock.mp4; crf=20
  else
    out=out/i10-intro-$v-1080p$fps.mp4; crf=14
  fi
  ffmpeg -y -loglevel error -framerate $fps -i $dir/%04d.png -c:v libx264 -profile:v high -preset slow -crf $crf \
    -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -r $fps -an -movflags +faststart $out
  echo "$v: wrote $out"
done
