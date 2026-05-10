# Other

## For Petrichor Players on macOS

Petrichor currently uses a "known artists list" pattern to match artists, which means some artists not in the list may not be correctly recognized, causing classification issues.

You can download the project's [/tools/artists_gen.py](/tools/artists_gen.py) and run it from any location.  
It reads the artist list stored in `vncmd`'s cache and generates a file named `known_artists_DATE.txt` in the same directory as `artists_gen.py`.

Place this file in `/Applications/Petrichor.app/Contents/Resources` and the player will correctly recognize artists.

~~Additionally, the Petrichor player has issues when processing artist lists with "multiple artists where the first artist is a 2+ character Chinese name". This is not a `vncmd` issue.~~  
This [Issue](https://github.com/kushalpandya/Petrichor/issues/280) has been fixed.
