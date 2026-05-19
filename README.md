<div align="center">
<img width="128" height="128" alt="27ef7465-6bf8-46c6-94a7-f2ddc6979259-4" src="https://github.com/user-attachments/assets/2f87aac6-f2cd-4615-b24c-912e7cc9485d" />


# SoundCloud Downloader

**Download tracks from SoundCloud directly to your desktop.**

![Platform](https://img.shields.io/badge/platform-Windows-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)

</div>

---

## Features

**Download** — paste a track link from SoundCloud and hit Download. That's it.

**Monitor** — add artists to a watchlist, click Check — the app finds their new tracks from the last N days and downloads them automatically. Already downloaded tracks are skipped via an archive file.

**Clipboard detection** — copy a link in your browser, switch to the app — the URL is already filled in.

**OAuth token** — if SoundCloud starts rate-limiting requests, set your personal token for stable operation.

Output format: **MP3** with embedded cover art and metadata (artist, title, date).

---

## Screenshots

<img width="740" height="676" alt="Screenshot_1" src="https://github.com/user-attachments/assets/4d800097-672c-42c8-8958-607bd74e0da7" />
<img width="738" height="674" alt="Screenshot_2" src="https://github.com/user-attachments/assets/c1741b54-4aa0-4901-bcb8-545b49dff11f" />
<img width="739" height="675" alt="Screenshot_3" src="https://github.com/user-attachments/assets/d612d876-d6c1-491d-af24-ea0f24ee9f49" />

---

## Installation

1. Download the archive from [Releases](../../releases/latest)
2. Extract to any folder
3. Run `SoundCloud Downloader.exe`
> **If you are from Russia, use together with [zapret](https://github.com/Flowseal/zapret-discord-youtube)
and add the following domains to ```list-general.txt```:**
```soundcloud.com
a-v2.sndcdn.com
style.sndcdn.com
assets.web.soundcloud.cloud
i1.sndcdn.com
al.sndcdn.com
va.sndcdn.com
wave.sndcdn.com
playback.media-streaming.soundcloud.cloud
cf-hls-media.sndcdn.com
license.media-streaming.soundcloud.cloud**
```

---

## Folder structure after first run

```
SoundCloud Downloader/
├── SoundCloud Downloader.exe
├── Downloads/                  ← tracks saved here
│   └── ArtistName/
│       └── 20250501 - Track Title.mp3
├── artists.txt                 ← artist watchlist for Monitor
├── downloaded.txt              ← archive log (do not delete)
└── oauth.txt                   ← token (created when saved)
```

---

## Monitor — how to use

1. Open the **Monitor** tab
2. Paste an artist page URL (`https://soundcloud.com/artist-name`)
3. Click **Add** — the artist is added to the list
4. Click **Check All** — the app checks all artists and downloads new tracks

Tracks are saved to `Downloads/<artist name>/` with the release date in the filename.

---

## OAuth Token (optional)

Needed if SoundCloud starts returning 403 errors. The token is tied to your account.

**How to get it:**

1. Open [soundcloud.com](https://soundcloud.com) and log in
2. Press `F12` → **Network** tab
3. Type `api-v2` in the filter box
4. Press Play on any track
5. Click any request → **Headers** tab → find:
   ```
   Authorization: OAuth 2-294412-987654321-AbCdEfGhIjKlMn
   ```
6. Copy only the part after `OAuth ` (without the word itself)
7. Paste it in **Settings** → OAuth Token field → click **Save Token**

---

## Supported sources

| Source | Single track | Artist monitor |
|---|---|---|
| SoundCloud | ✅ | ✅ |
| Coming soon | ❌ | ❌ |

---

The built executable will appear in `dist\SoundCloud Downloader\`.

---

## Dependencies

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — track downloading
- [ffmpeg](https://ffmpeg.org) — MP3 conversion
- [aria2c](https://github.com/aria2/aria2/releases/tag/release-1.37.0)
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) — UI
- [Pillow](https://python-pillow.org) — icon generation
