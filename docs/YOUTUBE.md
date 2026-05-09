# Getting `client_secret.json` and `token.json` (YouTube OAuth)

- Create a new Google Cloud Console project.
  https://console.cloud.google.com/projectcreate

- Enable **YouTube Data API v3**
  https://console.cloud.google.com/apis/library/youtube.googleapis.com

- Configure **OAuth consent screen**
  https://console.cloud.google.com/auth/branding

- Create OAuth credentials
  https://console.cloud.google.com/apis/credentials
  - Click **Create Credentials**
  - Choose **OAuth client ID**
  - Application type: **Desktop app**
  - Click **Create**
  - Click **Download JSON**

- Save file as `.auth/client_secret.json`

- Configure **Data Access**
  https://console.cloud.google.com/auth/scopes
  - Click **Add or Remove Scopes**
  - User type: **External**
  - Publishing status: **Testing**
  - Add scope:
    ```
    https://www.googleapis.com/auth/youtube.upload
    https://www.googleapis.com/auth/youtube.force-ssl (for comments)
    ```
  - Click **Update**
  - Click **Save**

- Add self as a test user
   https://console.cloud.google.com/auth/audience

- Run `./tools/Auth.ps1` on Windows with browser
   Authorize via browser
   Will be saved to `.auth/token.json`
