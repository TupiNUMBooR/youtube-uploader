# youtube-uploader

![](docs/image.jpg)

Tiny Docker service that uploads prepared folders from `./in` to YouTube.

![CI/CD](https://github.com/TupiNUMBooR/youtube-uploader/actions/workflows/ci-cd.yml/badge.svg)
![Latest Release](https://img.shields.io/github/release/TupiNUMBooR/youtube-uploader)
![Release Date](https://img.shields.io/github/release-date/TupiNUMBooR/youtube-uploader)

![Top Lang](https://img.shields.io/github/languages/top/TupiNUMBooR/youtube-uploader?logo=python)
![Docker](https://img.shields.io/badge/docker-ghcr-blue?logo=docker)

Another tool creates a folder with:

* video
* metadata
* optional thumbnail

`youtube-uploader` scans /in, uploads ready folders, and sends Telegram notifications.

## Run

`.env`

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Put `token.json` in `.auth/` (see below).

Start:

```bash
docker compose up -d --build
```

## Workspace

Each upload candidate is one direct child folder inside `./in`.

Example:

```text
in/
out/
fail/
  my-video/
    youtube-uploader.md
    video.mp4
    thumbnail.png
```

The uploader ignores folders containing:

* `youtube-uploader-uploaded.txt`
* `youtube-uploader-failed.txt`

## youtube-uploader.md

The metadata file is the source of truth.

Example:

```md
# title
My Cool Video

# description
Very atmospheric thing.

Made with strange machines
in the middle of the night.

# privacy
private

# upload_since
2026-05-10T00:00:00Z

# publish_at
2026-05-10T08:00:00Z

# priority
10

# video_file
video.mp4

# thumbnail_file
thumbnail.png
```

Minimal file:

```md
# video_file
video.mp4

# privacy
private
```

Supported sections:

| Section          | Required | Meaning                                                                     |
| ---------------- | -------- | --------------------------------------------------------------------------- |
| `title`          | no       | YouTube title. Defaults to video filename without extension.                |
| `description`    | no       | YouTube description. Multiline supported.                                   |
| `privacy`        | yes      | `private`, `unlisted`, or `public`.                                         |
| `upload_since`   | no       | Do not upload before this UTC timestamp.                                    |
| `publish_at`     | no       | Scheduled YouTube publish time. Upload is sent as private with `publishAt`. |
| `priority`       | no       | Higher value uploads first. Default: `0`.                                   |
| `video_file`     | yes      | Video filename inside the same folder.                                      |
| `thumbnail_file` | no       | Thumbnail filename inside the same folder.                                  |

Timestamp format:

```text
2026-05-10T08:00:00Z
```

Why .md, you may ask? Because it's human-friendly readable and editable.
Imagine fixing yaml indentation or json quotes by an average user.

## Upload state

During retries:

```text
youtube-uploader-uploading.txt
```

After success:

```text
youtube-uploader-uploaded.txt
youtube-uploader.log
```

Example:

```text
uploaded_at: 2026-05-09T12:00:00Z
video_id: abc123
url: https://youtu.be/abc123
privacy: private
publish_at: 2026-05-10T08:00:00Z
```

After permanent failure:

```text
youtube-uploader-failed.txt
youtube-uploader.log
```

Example:

```text
failed_at: 2026-05-09T12:00:00Z
stage: upload
attempts: 20
message: HttpError: ...
last_log_lines:
...
```

## Retry behavior

Environment variables:

```env
POLL_SECONDS=5
MAX_UPLOAD_ATTEMPTS=20
RETRY_BASE_SECONDS=60
RETRY_MAX_SECONDS=3600
```

Retries use exponential backoff:

```text
60s
120s
240s
480s
...
```

Failed uploads automatically lose priority over time.

## Telegram

The uploader sends Telegram notifications for:

* startup
* shutdown
* upload started
* retry scheduled
* upload complete
* upload failed
* main loop errors

Telegram is optional.
Uploads still work if Telegram variables are empty.

## OAuth

Expected token location inside container:

```text
/.auth/token.json
```

Mounted from:

```text
./token.json
```

See `docs/YOUTUBE.md` for OAuth setup.

# Getting `client_secret.json` and `token.json` (YouTube OAuth)

* Create a new Google Cloud Console project.
  [https://console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)

* Enable **YouTube Data API v3**
  [https://console.cloud.google.com/apis/library/youtube.googleapis.com](https://console.cloud.google.com/apis/library/youtube.googleapis.com)

* Configure **OAuth consent screen**
  [https://console.cloud.google.com/auth/branding](https://console.cloud.google.com/auth/branding)

* Create OAuth credentials
  [https://console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)

  * Click **Create Credentials**
  * Choose **OAuth client ID**
  * Application type: **Desktop app**
  * Click **Create**
  * Click **Download JSON**

* Save file as:

```text
.auth/client_secret.json
```

* Configure **Data Access**
  [https://console.cloud.google.com/auth/scopes](https://console.cloud.google.com/auth/scopes)

  * Click **Add or Remove Scopes**
  * User type: **External**
  * Publishing status: **Testing**
  * Add scopes:

```text
https://www.googleapis.com/auth/youtube.upload
https://www.googleapis.com/auth/youtube.force-ssl
```

* Add yourself as a test user
  [https://console.cloud.google.com/auth/audience](https://console.cloud.google.com/auth/audience)

* Run:

```sh
docker compose run --rm -e PORT=4444 -p "4444:4444" -v "./.auth:/.auth" youtube-uploader python oauth.py
```

Authorize in browser.

Token will be saved to:

```text
.auth/token.json
```

## Release

Git tag:

```bash
git tag 1.0.0
git push origin 1.0.0
```

Published images:

```text
ghcr.io/tupinumboor/youtube-uploader:1.0.0
ghcr.io/tupinumboor/youtube-uploader:latest
```
