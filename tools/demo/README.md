# Demo recording

`record.mjs` drives the fictional workspace demo in Chromium and saves frames;
`ffmpeg` turns them into `docs/demo.gif`.

```sh
python -B -m workspace_ui.demo --port 8775 &
node tools/demo/record.mjs http://127.0.0.1:8775 "Fictional browser test password" /tmp/frames
ffmpeg -y -framerate 2 -i /tmp/frames/f%03d.png \
  -vf "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none" docs/demo.gif
```

Re-record after any visual change so the GIF matches the product.
