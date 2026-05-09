# Other

## For Petrichor Users on macOS

Petrichor currently uses a "known artists list" to match artist names, which means artists not in the list may not be recognized correctly.

You can download [tools/artists_gen.py](tools/artists_gen.py) and run it from anywhere.  
It reads the artist list cached by `vncmd` and generates a `known_artists_DATE.txt` file next to itself.

Place this file in `/Applications/Petrichor.app/Contents/Resources` and the app will correctly recognize your artists.

Additionally, Petrichor crashes when processing multi-artist tags where the first artist has 3+ CJK characters. This is not a `vncmd` issue.
