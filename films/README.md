# Films

`index.html` is a public page at `/films` on the hosted demo
(https://parlu-app.vercel.app/films) with the Parlu films and app screen
recordings, so they can be shared with one link. No sign-in is needed.

- `media/` holds the films as H.264 MP4 files (already `faststart`, so they
  begin playing before they finish downloading).
- `posters/` holds one still frame per film, taken with ffmpeg.
- The root `vercel.json` serves this folder as static files and keeps it out of
  the Python function bundle. Each link like `/films#the-yes` jumps to a film.

The source animations and audio for the films live outside the repository in
the project's shared files (`launch-film/`).
