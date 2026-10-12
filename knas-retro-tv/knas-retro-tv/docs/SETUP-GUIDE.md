# KNAS Setup Guide

Everything from "I just downloaded this" to watching 90s cable on your TV. Follow the parts you need and skip the rest.

**Contents**

1. [Before you start](#1-before-you-start)
2. [Install KNAS on your server](#2-install-knas-on-your-server)
3. [Fill out the setup page](#3-fill-out-the-setup-page)
4. [Watch it on your TV](#4-watch-it-on-your-tv)
5. [ErsatzTV (your own TV channels)](#5-ersatztv-your-own-tv-channels)
6. [Break clips: shows that start on the :00 and :30](#6-break-clips-shows-that-start-on-the-00-and-30)
7. [Add your own stuff](#7-add-your-own-stuff)
8. [Updating](#8-updating)
9. [Troubleshooting](#9-troubleshooting)
10. [Questions](#10-questions)

---

## 1. Before you start

**You need:**

- **A computer that's always on and runs Docker.** A NAS (UGREEN, Synology, QNAP, Unraid, TrueNAS…), an old PC running Linux, a mini PC or a Raspberry Pi 4/5 all work.
- **Something to watch on.** A TV box or stick (Onn, Chromecast with Google TV, Fire TV), an Xbox, a PC, a phone, or a CRT TV through an HDMI-to-composite converter.
- **Optional: [ErsatzTV](https://ersatztv.org)**, if you want your own shows and movies as live channels in the KNAS cable box. KNAS works without it, too: you still get the weather channel, sports and break screen.

**Find your server's IP address.** You'll type it in a lot. It's in your NAS's network settings or your router's list of devices, and usually looks like `192.168.1.50`. This guide writes it as `SERVER_IP`.

---

## 2. Install KNAS on your server

### Step 1: Put the files on the server

1. On the GitHub page, click the green **Code** button → **Download ZIP**.
2. Unzip it.
3. Copy the unzipped folder to your server, where your other Docker apps live. For example:
   - UGREEN / Synology: `/volume1/docker/knas`
   - Unraid: `/mnt/user/appdata/knas`
   - Linux: `~/knas`

The folder should contain `docker-compose.yml`, `settings.txt`, `server.py` and the `app`, `web` and `cast` folders.

### Step 2: Start it

Pick whichever way you normally run Docker apps.

**A) Your NAS's Docker app** (UGREEN Docker, Synology Container Manager, QNAP Container Station)

1. Open the Docker app and go to **Projects** (Synology: **Project**, QNAP: **Applications**).
2. Click **Create**.
3. Name it `knas`.
4. Set the **path** to the KNAS folder from Step 1.
5. It will find the `docker-compose.yml` that's already in the folder. Choose to use it (Synology: **Use existing docker-compose.yml**). If your app asks you to paste the compose file instead, open `docker-compose.yml` in a text editor and paste its contents.
6. Click **Create / Deploy / Build**.

**B) Command line** (Linux, or SSH into your NAS)

```sh
cd /path/to/knas
docker compose up -d --build
```

**The first start takes 5 to 10 minutes.** Docker downloads a small web browser and video tools for the recorder. After that it starts in seconds.

> **Portainer users:** Portainer's web editor can't build from a local folder. Use the command line once, or a Portainer stack from a Git repository.
>
> **Docker Desktop on Windows or Mac:** KNAS uses host networking. Turn it on in Docker Desktop: **Settings → Resources → Network → Enable host networking** (Docker Desktop 4.34 or newer). A NAS or Linux box is easier.

### Step 3: Check it's running

There are two containers: **knas42** (the website) and **knas42-cast** (the recorder). Open the **knas42** log in your Docker app. You'll see something like:

```
KNAS 42 2.6.2 on the air at http://0.0.0.0:8642

  Setup page:  http://192.168.1.50:8642/setup
  Cable box (TV):    http://192.168.1.50:8642/tv
```

**It's already working.** Open the cable box address on your TV, computer or phone. KNAS guessed your town from your internet connection (the log says which town), so the weather works right away. Nothing on the setup page is required.

That's the address to open next.

---

## 3. Fill out the setup page (optional)

Open **`http://SERVER_IP:8642/setup`** in a browser on any device on your home network. A phone works fine.

**Everything on the setup page is optional.** KNAS works the moment it starts: it guesses your town from your internet connection, and every other setting has a sensible default. Come here when you want to change something. (If KNAS can't reach the internet when it first starts, it can't guess your town, so the screens send you here to type it in.) The menu down the side (along the top on a phone) has every section, and the **Find a setting** box jumps straight to anything.

| Section | What to do |
|---|---|
| **Location** | Already guessed for you. If the guess is wrong (internet providers sometimes place you in a nearby city), type your town, press **Find**, and pick it from the list. The time zone fills itself in. Pick °F or °C. |
| **Channels & screen** | Station name and channel numbers (`0` hides a channel). **Fill any screen** for normal TVs and phones, **Classic 4:3** for a CRT. |
| **Weather** | Which weather pages to show, seconds per page, your own ticker message and the map style. |
| **Sports** | Pick a sport, type a team name and click it. Add as many as you like. Optional radio station. |
| **News** | One source per line: a news website, a few words to search, or an RSS feed. Press **Check**. Only headlines from the last few hours are shown (6 by default), on the weather channel and in the break screen's ticker. |
| **Facts & trivia** | Your own lists, plus facts from topics or links and trivia by topic. See [section 7](#7-add-your-own-stuff). |
| **ErsatzTV** | Its address, where it runs, and a **Test** button. See [section 5](#5-ersatztv-your-own-tv-channels). |
| **Colors, Fonts, Guide style, Names & logos** | Make it look the way you want. There's a live preview. Logos upload right away. |
| **Sound** | The volume leveler, so channels don't jump in loudness. |
| **Holidays** | Automatic holiday looks (snow at Christmas, bats at Halloween…), or off. |
| **Breaks & clips** | Break screen contents, and break clips for ErsatzTV. See [section 6](#6-break-clips-shows-that-start-on-the-00-and-30). |

Press **Save & Start** at the bottom. KNAS restarts with your settings in a few seconds.

> Saving can't break anything. Values that don't make sense are skipped and your old setting is kept, and every save backs up your previous settings to `data/settings.backup.txt`. Only devices on your home network can save.

---

## 4. Watch it on your TV

| Page | Address |
|---|---|
| **Cable box** (all channels, guide, remote control) | `http://SERVER_IP:8642/tv` |
| Weather channel only | `http://SERVER_IP:8642/` |
| Sports channel only | `http://SERVER_IP:8642/sports` |
| Break screen only | `http://SERVER_IP:8642/break` |

### Android TV box (Onn, Chromecast with Google TV, Fire TV…)

1. Install **Fully Kiosk Browser** from the app store. The free version is fine.
2. Set its **Start URL** to `http://SERVER_IP:8642/tv`.
3. In Fully's settings, turn on **Autoplay Videos**, **Launch on Boot** and **Keep Screen On**.
4. Set the box's output resolution to **1080p or 720p** (not 4K) in its display settings. Everything runs smoother and text looks sharper.

To get back to Fully's settings later, hold **Back** or swipe in from the left edge.

### Other devices

- **Xbox:** open Microsoft Edge and go to the `/tv` address. A controller works as a remote.
- **PC:** any browser. Press **F11** for full screen.
- **iPhone / iPad:** in Safari, tap **Share → Add to Home Screen**. KNAS Cable opens like an app, full screen.
- **Android phone:** the first tap goes full screen. **⋮ → Add to Home screen** makes it an app.
- **CRT TV:** pick **Classic 4:3** under Channels & screen. If the picture looks squeezed, add `?stretch=1` to the address. If the edges are cut off, add `?zoom=0.92`.

### Controls

| | Change channel | Guide | Last channel | What's on | Close |
|---|---|---|---|---|---|
| **TV remote** | Up / Down | OK | Left | Right | Back |
| **Game controller** | LB / RB | A | | | B |
| **Phone / tablet** | Swipe up / down | Double-tap | | Tap | |
| **Keyboard** | Up / Down, or type the number | Enter | Left | Right | Esc |
| **Mouse** | Scroll wheel (also scrolls the guide) | Click | | | |

**In the guide:** long show names wrap onto two lines so they fit in their box. The box at the top shows the selected show's description, plus its picture if ErsatzTV has artwork for it. With a mouse, rest the pointer on any show for a second to see its description in a pop-up.

---

## 5. ErsatzTV (your own TV channels)

[ErsatzTV](https://ersatztv.org) turns your own shows and movies into live, scheduled TV channels. KNAS puts those channels in its cable box with the guide, channel banner and static between channels.

### 5.1 Connect it

1. Install and set up ErsatzTV by following [its own guide](https://ersatztv.org/docs/). It can run on the same NAS as KNAS, or on another computer.
2. In the KNAS setup page, open **ErsatzTV**:
   - **ErsatzTV address:** where you open ErsatzTV in a browser, for example `http://192.168.1.50:8409`. Press **Test**.
   - **Where does ErsatzTV run?** Pick **On this same NAS / server**, **On a Windows PC**, or **On a Mac or Linux computer**. This decides how break clips get to it (section 6).
3. Press **Save & Start**. Your ErsatzTV channels now show up in the cable box at `/tv`, next to the KNAS weather and sports channels.

### 5.2 The weather channel inside ErsatzTV (optional)

You only need this if you want KNAS Weather as a channel in ErsatzTV itself, for example to watch it in the ErsatzTV or Jellyfin apps. The KNAS cable box already has it built in.

> This keeps a hidden browser recording the weather channel all day, which uses a fair amount of CPU. Skip it unless you need it.

1. Setup page → **Breaks & clips** → **What to record**: tick **Weather channel stream** and save.
2. Setup page → **Files**: download **Weather channel for ErsatzTV (.yml)**. It already has your server's address in it.
3. Put that file in a folder ErsatzTV can see. In ErsatzTV, add a **Local** library of kind **Remote Streams** pointing at that folder, scan it, and make a channel that plays it.

---

## 6. Break clips: shows that start on the :00 and :30

Real TV channels start shows on the hour and half hour, with commercials in between. ErsatzTV can do the same if it has **filler** to play in the gaps. KNAS makes that filler for you: short videos of its "We'll Be Right Back" break screen, with trivia, facts and your channel name.

- KNAS records them into the `break-clips` folder inside the KNAS folder: `KNAS Break 30sec A.ts`, `KNAS Break 1min A.ts`, `KNAS Break 5min B.ts`, and so on.
- The first set takes about 20 minutes. They're re-recorded every 3 hours and just after midnight, so the trivia, facts and headlines in them stay fresh. New clips **replace** the old ones (same names), so nothing piles up.
- The clips leave out the clock, the date, Coming Up and On This Day, so they never look out of date.
- The recorder only runs while it's making clips, so it doesn't use CPU the rest of the time.

**Don't want them?** Setup page → **Breaks & clips** → **Off: I use my own filler**. KNAS then records nothing and leaves the clips folder alone.

**Watch progress** in the **Clip status** box on the Breaks & clips page. It shows when each clip was made and, if ErsatzTV is on another computer, when that computer last copied it. There's also a **Make new clips now** button.

### 6.1 Get the clips to ErsatzTV

The setup page shows exactly these steps for whatever you picked under **Where does ErsatzTV run?**, with download buttons that already have your server's address filled in.

#### A) ErsatzTV on the same NAS (Docker)

ErsatzTV can read the clips straight from the KNAS folder. You just have to let its container see that folder.

1. In your Docker app, edit the **ErsatzTV** container or project and add a volume / folder mapping:

   | On the NAS (host) | Inside ErsatzTV (container) |
   |---|---|
   | your KNAS folder's `break-clips` folder, e.g. `/volume1/docker/knas/break-clips` | `/knas-clips` |

   In an ErsatzTV `docker-compose.yml` that's one more line under `volumes:`:

   ```yaml
       volumes:
         - /volume1/docker/knas/break-clips:/knas-clips:ro
   ```
2. Restart ErsatzTV.
3. In ErsatzTV: **Media Sources → Local** → add a library of kind **Other Videos** with the folder `/knas-clips`, then scan it.

#### B) ErsatzTV on a Windows PC

Windows can't reliably read the clips off the NAS by itself (ErsatzTV usually can't see network folders). So one small setup file keeps a fresh copy of the clips on the PC.

1. On the PC that runs ErsatzTV, open the KNAS setup page → **Breaks & clips** → **Getting the clips to ErsatzTV**, and click **Download Get KNAS Break Clips.bat**. It already has your server's address in it.
2. **Double-click it.** If Windows warns you, click **More info → Run anyway** (or **Keep** in your browser). It:
   - makes a folder for the clips, usually `C:\Users\you\KNAS Break Clips`
   - copies the clips there (the first time takes a few minutes)
   - sets itself to check for new or missing clips every 5 minutes in the background, with no windows popping up
   - shows you the clips folder and copies its path, so you can paste it
3. In ErsatzTV: **Media Sources → Local** → add a library of kind **Other Videos**, paste the clips folder, save, and scan it.

You never need to touch it again. It updates itself whenever KNAS updates, gives KNAS ErsatzTV's API key by itself, and tells KNAS when the clips change. Running the file again is safe: it reuses the same folder. The **Copied to ErsatzTV computer** column in Clip status shows it working. If the PC hasn't picked up any clips, the setup page shows a yellow **!** next to Breaks & clips.

#### C) ErsatzTV on a Mac or Linux computer

1. Download **knas-clip-sync.sh** from the setup page (Breaks & clips, or Files) and put it in a folder on that computer.
2. Run it once in Terminal: `sh knas-clip-sync.sh`. The clips land in a `break-clips` folder next to it.
3. Make it run every 5 minutes: run `crontab -e` and add
   ```
   */5 * * * * /bin/sh "/full/path/to/knas-clip-sync.sh" >/dev/null 2>&1
   ```
4. In ErsatzTV, add a **Local** library of kind **Other Videos** with that `break-clips` folder and scan it.

### 6.2 Let KNAS tell ErsatzTV when clips change

ErsatzTV only notices that the clips changed when it scans its library. Until then, it can try to play a clip it remembers and show a "media isn't available" error. KNAS can ask ErsatzTV to rescan the clips library every time the clips change, so this never happens:

1. In ErsatzTV, go to **Media Sources → Local** and click **edit** (the pencil) on the library with the KNAS break clips. The number in the address bar is the library number, for example `…/media/sources/local/5/edit` means **5**.
2. **Newer ErsatzTV (26.8 and later) also needs its API key.** If ErsatzTV runs on a Windows PC, Mac or Linux computer, **the clip copier finds the key and gives it to KNAS automatically** the next time it runs, so there's nothing to do. If ErsatzTV runs in Docker on the NAS, copy it yourself: it's in `api-secrets.json` in the folder you mapped to ErsatzTV's config. Open the file and copy the long key (the text in quotes after the name).
3. KNAS setup page → **Breaks & clips** → **Keep ErsatzTV up to date**: type the library number (and paste the API key if you copied it yourself), then press **Test**. ErsatzTV should start scanning that library. (If it says ErsatzTV wants its API key, the key is missing or wrong.)
4. Press **Save & Start**.

From then on, KNAS asks ErsatzTV to rescan right after new clips are made (ErsatzTV on the NAS) or right after your computer copies them (ErsatzTV on a PC or Mac). The Clip status box shows when the last rescan happened.

### 6.3 Set up the filler in ErsatzTV

Do this once, after the clips show up in ErsatzTV.

1. **Make a collection.** In ErsatzTV: **Lists → Collections → Add Collection**, name it `KNAS Break Clips`. Then open the Other Videos library, select all the KNAS Break clips, and use **Add to Collection** to put them in it.
2. **Make two filler presets.** In **Lists → Filler Presets → Add Filler Preset**:

   | Name | Filler Kind | Filler Mode | Pad to Nearest Minute | Collection |
   |---|---|---|---|---|
   | KNAS Break Pad | Post-Roll | Pad | 30 | KNAS Break Clips |
   | KNAS Break Fallback | Fallback | | | KNAS Break Clips |

3. **Use them on your channels.** For each channel, open its schedule, and on each schedule item set:
   - **Start Type:** Dynamic
   - **Post-Roll Filler:** KNAS Break Pad
   - **Fallback Filler:** KNAS Break Fallback
4. **Reset the playouts** (Playouts → reset) so the new schedule takes effect.

Now each show is followed by break clips until the next :00 or :30, and the next show starts right on time.

> Don't use the live break stream (port 8644) as filler. ErsatzTV doesn't handle live streams well as filler, which is why KNAS makes clips.

---

## 7. Add your own stuff

| What | How |
|---|---|
| **Background music** for the weather channel | Put `.mp3`, `.m4a`, `.ogg` or `.flac` files in the `music` folder. Smooth jazz is the classic choice. |
| **Video clips** for the break screen | Put `.mp4` or `.webm` files in the `break-videos` folder (old commercials, station IDs…). |
| **Facts** ("Did You Know?") | Setup page → **Facts & trivia**. Edit **My facts list**, turn on **Facts about where I live** (from Wikipedia), or add more under **More facts from**, one per line. That can be a topic in plain words (`Space`, `Dinosaurs`, `The Simpsons`), a Wikipedia page, a Google Sheet, a text file link, any web page with a list of facts, or an RSS feed. Facts show on the break screen and in the weather ticker. |
| **Trivia** | Same page. Edit **My trivia list**, tap **Trivia topics** (TV, Movies, Music, Sports, History… from the free Open Trivia Database), or add your own Google Sheet: one question per row, with the right answer in column B and wrong answers in C to E. |
| **Logos** | Setup page → **Names & logos** → Upload. Square PNGs with a see-through background look best. |
| **Sports teams** | Setup page → **Sports**, or edit `teams.txt`. |

**Using a Google Sheet:** in Google Sheets, click **Share → General access → Anyone with the link**, then copy the link into KNAS.

---

## 8. Updating

1. Download the new release `.zip` from the GitHub **Releases** page.
2. Drop the zip, as is (don't unzip it), into the **`updates`** folder inside your KNAS folder.
3. Wait about a minute. KNAS installs it and restarts by itself.

Your settings, teams, facts, trivia, music, logos and clips are never touched. `updates/update-log.txt` shows what happened. A broken update is refused, and the working version keeps running.

`docker-compose.yml` is never changed by an update, so your Docker setup stays exactly as you made it.

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| **Can't open the setup page** | Check both containers are running in your Docker app, and that you're using the server's IP with `:8642`. Look at the **knas42** log for the exact address. |
| **The weather is for the wrong place** | KNAS guessed your town from your internet connection, and providers sometimes place you in a nearby city. Setup page → Location → type the town with its state or country, press **Find**, pick the right one, and save. |
| **A weather page is missing or empty** | Pages with nothing to show are skipped (for example News with no sources). Open `http://SERVER_IP:8642/api/all` and look at `errors`. |
| **The cable box says it can't reach ErsatzTV** | Setup page → ErsatzTV → press **Test**. The address needs `http://` and the port (usually `8409`). |
| **Break clips aren't updating** | Setup page → Breaks & clips → **Clip status**. The top line says what's wrong. Press **Make new clips now**. If it says it can't reach the break recorder, restart the **knas42-cast** container. |
| **ErsatzTV says a break clip "isn't available" or can't be found** | ErsatzTV is remembering a clip that was replaced or removed. In ErsatzTV: scan the clips library, then open **Trash** and empty it, and check the KNAS Break Clips collection only has the current clips. Then set up [automatic rescans](#62-let-knas-tell-ersatztv-when-clips-change) so it stays in sync. |
| **ErsatzTV still shows old clips** | Check **Copied to ErsatzTV computer** in Clip status. If it's empty, set up the copier (section 6.1). If it's recent, rescan the library in ErsatzTV. |
| **High CPU on the NAS** | Make sure **Weather channel stream** is off (Breaks & clips → What to record) unless you need it in ErsatzTV. Re-record clips every 2–3 hours instead of 1. Lower **Smoothness** to 15 fps under Recording quality. |
| **Choppy on the TV box** | Set the box to 1080p or 720p instead of 4K. KNAS also turns off heavy effects on TV boxes by itself. |
| **Text looks blocky** | Setup page → Fonts → try **Smooth** or **Modern News** with a **Soft** shadow. |
| **Facts or trivia from a link don't show up** | Facts & trivia → press **Check**. It says what went wrong in plain words. Google Sheets must be shared as **Anyone with the link**. |
| **Something went wrong after saving** | Copy `data/settings.backup.txt` over `settings.txt`. KNAS restarts within a few seconds. |

Logs: the **knas42** and **knas42-cast** container logs in your Docker app, plus `data/break-clips-log.txt` and `updates/update-log.txt` in the KNAS folder.

---

## 10. Questions

**Do I need ErsatzTV?** No. Without it you still get the weather channel, sports and the break screen in the cable box. ErsatzTV adds your own shows and movies as channels.

**Do I need any accounts or API keys?** No. Weather, radar, maps, scores, news, facts and trivia all come from free services that don't need keys.

**Is it private?** KNAS only runs on your home network, and only devices on your network can change settings. It contacts the internet only to fetch weather, maps, scores, news, facts and trivia, with no accounts and no tracking.

**How much does it slow down my NAS?** The website itself uses almost nothing. The recorder (knas42-cast) only works while it's making break clips, a few minutes each time. The optional weather stream for ErsatzTV is the one thing that runs all day.

**Which ports does it use?** `8642` for the web pages, plus `8643` (weather stream, off by default) and `8644` (break recorder, only while making clips). Both containers use host networking.

**Can I edit settings without the setup page?** Yes. Everything is in `settings.txt` (and `teams.txt`, `facts.txt`, `trivia.txt`) in the KNAS folder. Each setting is explained in the file. Save it and KNAS restarts within a few seconds.

**What's in the folder?**

| | |
|---|---|
| `settings.txt` | your settings (the setup page writes it) |
| `teams.txt`, `facts.txt`, `trivia.txt` | your teams, facts and trivia |
| `music/`, `break-videos/` | your music and break videos |
| `break-clips/` | break clips KNAS records for ErsatzTV |
| `updates/` | drop update zips here |
| `extras/` | ErsatzTV and clip-copier files (the setup page has ready-to-use copies) |
| `data/` | KNAS's own saved stuff: logos, caches, logs, settings backups |
| `app/`, `web/`, `cast/`, `docs/` | the KNAS code and this guide |
