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
docker compose up -d
```

**The first start takes a minute or two** while Docker downloads the ready-made KNAS images. (If your NAS can't download them, it builds them from the files instead, which takes 5 to 10 minutes.) After that it starts in seconds.

> **Portainer users:** paste `docker-compose.yml` into a new stack. It downloads the ready-made images, so nothing has to be built from a folder. Change `./:/knas` to the full path of the KNAS folder on your server.
>
> **Docker Desktop on Windows or Mac:** KNAS uses host networking. Turn it on in Docker Desktop: **Settings → Resources → Network → Enable host networking** (Docker Desktop 4.34 or newer). A NAS or Linux box is easier.

### Step 3: Check it's running

There are two containers: **knas42** (the website) and **knas42-cast** (the recorder). Open the **knas42** log in your Docker app. You'll see something like:

```
KNAS 42 2.15.1 on the air at http://0.0.0.0:8642

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
| **Colors, Fonts, Guide style, Names & logos** | Make it look the way you want. There's a live preview. Logos upload right away. The "Cable listings 2000s" guide style color-codes shows: sports green, movies purple, kids light blue. |
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

### Android TV box (Onn, Chromecast with Google TV, Fire TV…) and Android phones

**The KNAS 42 app** is the easiest way. It opens straight to the cable box, full screen, and the TV remote just works.

1. Download **KNAS-42-<version>.apk** from the GitHub **Releases** page.
2. Get it onto the box. The easy way: install the free **Downloader** app on the TV, type the APK's download link into it and install. Or put the APK on a USB stick. The first time, the box asks you to allow installing apps from that source; say yes.
3. Open **KNAS 42** from the TV's apps and type your NAS's address (like `192.168.1.50`).
4. Set the box's output resolution to **1080p or 720p** (not 4K) in its display settings. Everything runs smoother and text looks sharper.

In the app:
- The remote works like a cable box: arrows, OK, numbers, channel up/down, guide and info.
- **Back** closes the guide. Pressing it again asks if you want to leave, or opens **Settings**.
- **Hold Back** for a second to open **Settings** any time: change the NAS address, reload, turn on **Open when the TV turns on**, or make KNAS the home screen.

**Updates:** the app checks GitHub for new versions by itself and asks "Install now?" when one is out. The first time, Android asks you to allow **Install unknown apps** for KNAS 42; the app takes you there. You can also check any time: hold **Back** → **Check for app updates**.

**Open when the TV turns on:** turn it on in the app's Settings and KNAS opens by itself whenever the TV (or the box) wakes up. Newer Android asks you to allow **Display over other apps** for KNAS 42 the first time; the app takes you to that setting. If your box doesn't open it, find it under Settings → Apps → Special app access → Display over other apps.

**Use KNAS as the home screen** (so the TV turns on straight to KNAS, with no home screen first): in the app, hold **Back** → **Use KNAS as the home screen** → on. Your other apps (Netflix, YouTube, settings) are always under hold **Back** → **Other apps**. Turn the setting off any time to go back to normal.
- **Most Android TV boxes and phones:** press **Home**. When it asks which home screen to use, pick **KNAS 42** → **Always**.
- **Google TV boxes (Onn, Chromecast with Google TV):** they don't ask, so it takes a one-time step from a computer:
  1. On the TV: **Settings → System → About**, then click **Android TV OS build** 7 times until it says you're a developer. Go back to **Settings → System → Developer options** and turn on **USB debugging**. Write down the TV's IP address (**Settings → Network & Internet →** your Wi-Fi).
  2. On a computer: download **SDK Platform-Tools** from developer.android.com/tools/releases/platform-tools and unzip it. Open a command window in that folder (on Windows: click the address bar of the folder, type `cmd`, press Enter).
  3. Type `adb connect TV_IP` (your TV's IP). The TV asks to allow it: pick **Always allow**, then type the same command again.
  4. Type `adb shell cmd package set-home-activity io.github.thebust3r.knas42/.Home` and press Enter.
  5. Press **Home** on the remote: it goes to KNAS. If a TV update ever puts the old home screen back, do step 4 again.
- **Fire TV:** Amazon doesn't allow other home screens. Use **Open when the TV turns on** instead.

**Rather use a browser?** Fully Kiosk Browser works too: set its Start URL to `http://SERVER_IP:8642/tv` and turn on **Autoplay Videos**, **Launch on Boot** and **Keep Screen On**.

### Other devices

- **Xbox:** open Microsoft Edge and go to the `/tv` address. A controller works as a remote.
- **PC:** any browser. Press **F11** for full screen.
- **iPhone / iPad:** in Safari, tap **Share → Add to Home Screen**. KNAS Cable opens like an app, full screen.
- **Android phone:** use the KNAS 42 app (above), or in Chrome tap **⋮ → Add to Home screen**.
- **CRT TV:** pick **Classic 4:3** under Channels & screen. If the picture looks squeezed, add `?stretch=1` to the address. If the edges are cut off, add `?zoom=0.92`.

### Controls

| | Change channel | Guide | Last channel | What's on | Close |
|---|---|---|---|---|---|
| **TV remote** | Up / Down | OK | Left | Right | Back |
| **Game controller** | LB / RB | A | | | B |
| **Phone / tablet** | Swipe up / down | Double-tap | | Tap | |
| **Keyboard** | Up / Down, or type the number | Enter | Left | Right | Esc |
| **Mouse** | Scroll wheel (also scrolls the guide) | Click | | | |

**Phone remote:** open `http://SERVER_IP:8642/remote` on your phone (bookmark it, or add it to your home screen). Every TV with the cable box open shows up there. Pick one and use the arrows, OK, guide, number pad and the volume slider. The **What's on** tab lists every channel with what's playing right now, how much is left and what's next; tap one to jump straight to it. Press ✏️ to name each TV, like "Living room". **☰ → Turn off all TVs** puts every TV on a good-night screen with the picture and sound stopped; press any button (on the TV or the phone) to turn one back on.

**Different channels on each TV:** on the remote's **Channels** tab, press **Choose channels** and untick the ones you don't want on that TV, like hiding the movie channels on the kids' TV. Other TVs keep all their channels.

**Volume and mute:** move the mouse (or a TV remote's pointer) to show the on-screen buttons, then use **VOL −**, **VOL +** and **MUTE**. On a keyboard, press **−** / **+** and **M**. The green volume bar shows at the top, and **MUTE** stays in the corner while it's muted. Each TV or computer remembers its own volume. On a phone, use the phone's volume buttons.

**Experimental tools:** the newer features (game time, weather alerts, the jukebox, trivia, the phone extras, and the commercial breaks tool) are hidden on the setup page to keep it simple. To show them, type the code on the setup page (just start typing the numbers anywhere on the page, or type them in **Find a setting**). An **🧪 Experimental** page appears in the menu. The code is `EXPERIMENTAL_CODE` in `settings.txt`; change it to your own. **Hide experimental tools** at the bottom of that page hides them again. Hiding them doesn't turn anything off.

**Jukebox channel (party videos):** in Setup → **Experimental** → **Jukebox channel**, give **Jukebox ch.** a number (like 44) and press Save. The jukebox channel shows a QR code: guests scan it with their phone camera (or type `SERVER_IP:8642/j`, or press 📲 Share on someone else's phone). Add your Wi-Fi name and password in the Jukebox card and it also shows a code that joins guests to your Wi-Fi. On the page that opens, anyone types a song or artist and taps **Search** (then **+ Add** or **Next** on the one they want), or pastes a YouTube link (YouTube's **Share → Copy link**) and taps **Add to list** or **Play next**. Every TV on that channel plays the same video, with what's up next beside it, and the next one starts by itself. When the list runs out it can shuffle what's already been played (tick that on the jukebox page; it needs at least 3 played videos). **Official music videos:** lots of music videos are blocked from playing anywhere but YouTube. With **Download the videos** on (it is by default, in the same Jukebox card), the NAS downloads each video in the list ahead of time in 720p and the TVs play it from the NAS, so blocked videos play too, with no ads and every TV in sync. A song that was downloaded before is reused, never downloaded again, and the oldest videos are deleted once the folder passes the size you set (10 GB by default). The first time, KNAS sets up the free **yt-dlp** downloader by itself (that takes a minute or two), and keeps it updated daily. Downloading from YouTube goes against YouTube's terms, so turn it off if you'd rather not. If a video ever says YouTube asked KNAS to sign in, see the help under that card. Good to know: the jukebox plays in the cable box, not in the recorded channels that go to ErsatzTV. If a TV starts the jukebox with no sound, press any button on that TV.

**Severe weather alerts (US):** in Setup → **Experimental** → **Severe weather alerts**, turn it on. When the National Weather Service issues a warning for your town, every TV with the cable box open shows the red emergency crawl over whatever's on, with the alert tones (you can turn those off), and a small ⚠ tag stays in the corner until it ends. Press **Back** to clear the crawl. Choose warnings only, warnings and watches, or everything. If you set up ntfy (below), it can send the alert to your phone too. Use **Show a test alert** to see what it looks like.

**Jukebox karaoke:** on the jukebox page, tick **🎤 Karaoke mode**. Searches then find karaoke versions (the music with the words on screen, from channels like Sing King), and the TV shows **🎤 SING!** while one plays.

**Party games channel:** in Setup → **Experimental** → **Party games channel**, give **Games ch.** a number (like 45) and press Save. Tune a TV there: it shows a QR code. Everyone scans it (or goes to `http://SERVER_IP:8642/p`) and types a name. The first one to join is the host 👑 and picks the game and its options, then presses **Start**:
- **Trivia:** multiple choice, from Open Trivia Database topics or **My trivia list** (Facts & trivia). Faster right answers score more, and streaks add a bonus.
- **Name That Tune:** a few seconds of a song plays through the TV (sound only, no video) and everyone picks the title. It uses the songs the NAS has saved from the jukebox, so play at least 4 songs on the jukebox first.
- **Word Race:** everyone solves the same five-letter word on their phone at once (green = right spot, yellow = wrong spot). The TV shows everyone's progress as colors only. Fewer guesses and faster scores more. Any five letters count as a guess.
- **Bluff:** the TV shows a strange-but-true fact with a blank. Everyone types a fake answer, then everyone tries to pick the real one. You score for finding the truth and for every person your lie fools.
- **Wheel Puzzle:** take turns spinning the wheel, calling consonants and buying vowels ($250). Solve the puzzle to bank your money. Watch out for BANKRUPT.
- **Draw It:** each player takes a turn drawing a word on their phone while everyone else types guesses. The drawing shows live on the TV. Faster guesses score more, and the drawer scores for every right guess. Needs at least 2 players.

The TV shows a leaderboard between rounds and a podium at the end. The host can **Skip**, **End game**, **Play again** or **Pick another game**. A phone that went to sleep rejoins with its score when it's opened again.

**Game time:** in Setup → **Experimental** → **Game time**, choose any of: a "game starts soon, press OK to watch" box on the TVs that are on; the TVs changing to the game by themselves (you can pick which TVs); and phone alerts through the free **ntfy** app, with a **Watch on TV** button and optionally the final score. Everything is off until you tick it. It follows the teams on your Sports page.

**KNAS Wrapped:** your year in TV, like Spotify Wrapped. Open `http://SERVER_IP:8642/wrapped` (or 🎁 on the history page), pick a year and a TV (or every TV) and press **Play**: hours watched, days you tuned in, your top channel and shows, your biggest binge, your biggest TV day, when you watch, month by month, the hardest-working TV, channel flips, your jukebox anthem and your TV personality. Tap or press → for the next slide. Give it a channel number (Setup → Channels → Viewing history → **Wrapped ch.**) and it plays on a loop in the cable box. It needs viewing history to be on.

**Phone extras** (Setup → **Experimental** → **Phone extras**, each off until you turn it on). On the phone remote they're under the **☰** button at the top right:

- **📤 Throw it to the TV:** turn it on, then open `http://SERVER_IP:8642/throw` on a phone (or tap 📤 on the remote). Pick a photo or video and flick it up (or tap **Throw it**): it flies onto the TV with an "incoming transmission" frame. Choose one TV or every TV at the top. Photos stay up 30 seconds (you can change that); videos play to the end with sound. **Back** on the TV, or **Take it off the TV** on the phone, closes it. Videos from newer iPhones (HEVC) are converted on the NAS first so every TV can play them, which takes a little while for long videos. Everything thrown is deleted after a day.
- **🍅 Screen fun:** turn it on, then open `http://SERVER_IP:8642/fun` on a phone (or ☰ → Screen fun on the remote). Pick the TV at the top (or every TV). **Splat:** choose a tomato, pie, egg or snowball and flick it up: aim left or right, and flick harder to hit higher on the screen. It splats over whatever's on, drips and slides off after a few seconds. **Party:** tap **Confetti** or an emoji, or turn on **Shake for confetti** and shake your phone when something good happens. When several phones shake at once you get fireworks. (Shaking uses the motion sensor, so the first time it moves you to the secure address.) **Draw:** draw on your phone and the lines appear over the picture, like a football telestrator. Pick a color and line size; **Clear** wipes it, and lines fade on their own 30 seconds after you stop.
- **🎯 Flick games:** give it a channel number (like 48) and tune a TV there. Players scan the code (or go to `http://SERVER_IP:8642/flick`) and type a name; the first one in is the host 👑 and picks **Darts**, **Hoops**, **Bowling** or **Cup Pong**, then presses **Start**. Players take turns. When it's your turn, flick on your phone: the direction is your aim and how hard you flick is your power (the bar after each throw shows how hard it was; the white line in the middle is a good firm flick).
  - **Darts:** 3 darts a turn for 5 turns. Softer lands lower on the board, harder lands higher. Triples, doubles and bullseyes count like real darts.
  - **Hoops:** 5 shots a turn for 3 turns. A swish is 3 points, a make is 2. From round 2 the hoop slides side to side, faster in round 3.
  - **Bowling:** 5 frames, 2 balls each. Bend your swipe to put a curve on the ball; hitting the pocket just beside the head pin gets the most strikes. Strike = pins + 10, spare = pins + 5.
  - **Cup Pong:** 3 throws a turn. Softer flicks land in the front cups, harder ones reach the back row. Most cups wins.
- **📡 Stream channel:** give it a channel number (like 49). On a phone open `http://SERVER_IP:8642/streams` (or ☰ → Stream on the remote), paste a link and tap **Play**. It works with YouTube live streams (news, live cams, game streams, 24/7 music), Twitch, many news and TV station sites, and direct `.m3u8` stream links. KNAS finds the real video behind the page with the jukebox's video tool (it sets that up by itself the first time) and passes it through the NAS, so every TV can play it. **Put it on the TVs** switches every TV that's on to the channel, **⭐ Save** keeps it in your list for one tap later, and **Stop** clears it. Links from YouTube and Twitch expire after a few hours; KNAS quietly finds them again. Paid apps (Netflix, Hulu, ESPN+, Peacock…) lock their video so they can't play here, and sites that rebroadcast paid channels without permission aren't supported.
- **🎤 Voice remote:** turn it on and a 🎤 button appears on the phone remote. Tap it and say what you want: "channel 42", "go to 7", "put on Nickelodeon", the name of a show ("King of the Hill": if it's on any channel it tunes there; if it's coming up later it tells you when), "channel up", "last channel", "volume up", "mute", "guide", or "play Thriller on the jukebox". The phone's own speech recognition does the listening (Apple's on iPhone, Google's on Android, the same as dictating a text). It needs the secure address (below): the first time, the remote shows a button to open the secure remote. Add that one to your home screen. On iPhone, Siri & Dictation has to be on in Settings.
- **📹 Live Cam:** give it a channel number (like 46). On a phone, open `SERVER_IP:8645/cam` (or tap 📹 on the remote), type what the camera is ("Kitchen") and press **Go live**. The channel shows it with a red LIVE banner and the time; with 2 to 4 phones live it splits the screen. **Put it on the TVs** switches every TV that's on to the Live Cam channel. Pictures only, no sound, and nothing is recorded: it stops when you press **Stop** or leave the page. Keep the phone plugged in for long stretches.
- **🦆 Duck Season:** give it a channel number (like 47) and tune a TV there. Players scan the code on the screen (or open `SERVER_IP:8645/zapper`), type a name and choose **Zapper** or **Tilt**.
  - **Zapper** uses the phone's back camera, like the original light guns. Hold the phone up with the camera facing the TV. First shoot the target in the middle of the TV 3 times to calibrate (the phone learns how long your TV takes to flash). Then, every time you fire, the TV flashes black with a white box where each duck is, and the phone checks whether the small circle in the middle of its view saw the box. If you weren't aimed right at the duck, it's a miss. Want it harder? **Hide scope** turns off the camera view so you aim over the top of the phone. If you move the TV or switch TVs, press **Recalibrate**. Bright lamps or windows right behind the TV can cause misses. Heads up: each zapper shot flashes the screen black with white boxes for about a third of a second.
  - **Tilt** uses the motion sensors to move a crosshair on the TV. Point at the middle of the TV and tap **Center**; tap it again whenever the crosshair drifts.
  - Someone presses **Start**. Each round has 10 ducks and everyone gets 3 shots per duck (or pair of ducks). Hit enough of them to go on to the next round; the ducks get faster each round. You can also play by clicking or tapping on the TV screen itself.

**The secure address:** phones only let a page use the camera, microphone or motion sensors when it's secure (https). So KNAS also answers on `https://SERVER_IP:8645` (the normal port + 3), with a certificate it makes for itself. The first time each phone opens it, the phone warns that the connection "isn't private". That's expected, because nobody but KNAS vouches for the certificate: tap **Show details → visit this website** (iPhone) or **Advanced → Proceed** (Android). It's your own box on your own Wi-Fi. Typing the address without `https://` works too; KNAS sends you to the secure one. The secure address's front page (`https://SERVER_IP:8645`) is a phone menu with Remote, Live Cam, Duck Season and the rest. The weather channel and the cable box stay on the normal address. To use another port set `SECURE_PORT` in `settings.txt`, or `SECURE_PORT=off` to turn it off. On Docker Desktop (Windows/Mac), host networking must be on, the same as for the normal address.

**The Ratings:** open `http://SERVER_IP:8642/ratings` (or 🏆 on the phone menu) for a Nielsen-style chart of this week's most-watched channels and shows in your house, with ▲▼ arrows vs last week and how many TVs are watching each channel right now.

**Viewing history:** open `http://SERVER_IP:8642/history` (or 📊 on the remote) to see how long you watched, top channels and shows, each TV, the hours you watch most and a list of what was on. It's kept on your NAS for about a year. Turn it off or clear it in Setup → **Channels** → **Viewing history**.

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

### FFmpeg settings KNAS needs

KNAS plays your ErsatzTV channels right in the web browser, and web browsers can only play some video and audio formats. In ErsatzTV, go to **Settings → FFmpeg Profiles** and edit the profile your channels use (check every profile if you have more than one):

| Setting | Set it to | If it's wrong |
|---|---|---|
| Video Format | **h264** | HEVC/H.265 shows **NO SIGNAL** |
| Bit Depth | **8-bit** | 10-bit shows **NO SIGNAL** |
| Audio Format | **aac** | AC3 / E-AC3 plays the picture with **no sound** |
| Audio Channels | **2** | Mixed stereo and 5.1 episodes can make the sound drop out |
| Normalize Audio | **on** | Same as above |

On each channel, set **Streaming Mode** to **HLS Segmenter**. If you use an Nvidia card (NVENC hardware acceleration), double-check the video format is still **h264**. Nvidia can default to HEVC.

If a channel plays fine in other apps but not in KNAS, it's almost always one of these.

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

### Real old commercials in your ErsatzTV channels

Old commercial compilations (on archive.org, search "90s commercials" and the like) are often hours long. The **commercial splitter** cuts them into one file per commercial for you, by finding the quick fades to black between ads. It's in `extras/windows` in your KNAS folder.

1. Copy `Split Commercials.bat` and `knas-split-commercials.ps1` to the Windows PC that runs ErsatzTV. Keep them together.
2. **Drag your long videos (or a whole folder of them) onto `Split Commercials.bat`.** Or double-click it and pick the videos.
3. Each video gets a folder next to it called `<video name> - clips` with the commercials inside. Pieces over 3 minutes (usually part of a show that was recorded too) go in a `_long pieces (check these)` folder so you can look at them, and tiny glitches are skipped. Your original videos aren't changed. If you stop it partway, run it again and it carries on where it left off.

It uses the ffmpeg that comes with ErsatzTV. If it can't find one, it offers to download it. The clips also get their volume evened out, since old commercials are famously loud. It takes a while on long tapes (it reads the whole video, then re-saves each commercial), so let it run.

**Marking where the breaks go in your episodes (the Tools page):** ErsatzTV can only put commercials in the middle of an episode at **chapter markers**, and most episode files have none. KNAS's **Tools page** adds them, right on your NAS:

1. **Add your shows as libraries.** Open **`http://SERVER_IP:8642/tools`** (or **Setup page → Commercial breaks tool**). Copy the location of a folder with your shows and paste it in: from File Explorer's address bar on Windows (like `\\192.168.1.50\Media\TV` or `Z:\TV`), from Finder on a Mac (**Copy as Pathname**, or its `smb://` address), or from the folder's info in your NAS's Files app (like `/volume1/Media/TV`). Press **Add library**. It's saved right away, and you can add as many as you want (TV, cartoons, movies…). KNAS only ever changes files inside the libraries you add.
   - New installs can already see the NAS's drive. If you installed KNAS before 2.7.2, the Tools page asks you to add one line to `docker-compose.yml` once: under `knas42:` → `volumes:`, add `- /volume1:/nas/volume1` (QNAP: `- /share:/nas/share`, Unraid: `- /mnt/user:/nas/user`), then save and redeploy. Don't put `:ro` on the end, or KNAS can only look.
2. Pick a show and an episode. The first time, KNAS scans it for act breaks (fades to black, scene changes during a silence) and suggests where the breaks go. The dashed red lines are its suggestions. Each break shows a picture from right before and right after it.
3. Fix anything you don't like: drag a break on the timeline, nudge it with the buttons, remove it, or play to a spot and press **Add break here**. The **Cut ⏮ / ⏭** buttons jump between scene changes, and breaks snap to nearby scene changes while you drag.
4. Press **Save breaks**. Nothing is re-encoded: KNAS adds the markers, checks the file, and swaps it in under the same name (an `.avi` becomes `.mkv`). Then **Next episode →**.
5. To do lots of episodes at once: open a folder (one season, one show, or your whole TV folder) and press **Auto-mark this folder**. It goes through every folder inside too.
   - Leave **Just check first** on. It changes nothing and shows how many episodes got clean breaks. Then press **Looks good: add these breaks** (it uses what the check found, so it doesn't scan everything twice).
   - It works with any video type. Files that can't hold breaks (.avi, .wmv, .ts, .mpg, .flv and so on) are saved as .mkv with the same picture and sound, then ErsatzTV picks them up on its next scan.
   - It runs on the NAS, not in your browser. Close the page or turn off your computer and it keeps going. If the NAS restarts, it carries on where it left off. Reopen the Tools page any time to see how far it got and about how long is left.
   - A big library takes a while (often about a minute per episode, so a few thousand episodes can take a couple of days). It runs at low priority so the TV stays smooth.
   - When it's done, the **Worth a look** list shows the episodes to check by hand: best guesses, ones with no clean break, and files that didn't work. Click one to open it. **Download the full report** gives you the whole list.
   - **⚙ Break plan** sets how many breaks each length of show gets. By default: 1 in an 11-minute cartoon, 2 in a half-hour show, 4 in an hour show, and one every 15 minutes in a movie. It also has **Go easy on the NAS** (on by default), which keeps the scan to about a quarter of the CPU.
   - Lots of downloaded and disc episodes come with their own chapters, often bunched at the start. ErsatzTV would put commercials there, so KNAS replaces chapters that aren't at the act breaks. Chapters that are already at the act breaks are left alone.
   - **Shows coming from Jellyfin or Emby?** ErsatzTV only sees the new breaks after Jellyfin re-reads the episodes. Add your Jellyfin address and an API key on the setup page (**ErsatzTV & Jellyfin**) and KNAS does that for you after every save or auto-mark run. ErsatzTV then picks up the breaks on its next sync from Jellyfin.
   - **Keep backups of the originals** saves the untouched files in a hidden `.knas-originals` folder at the top of the library, so Jellyfin, Plex, Emby and ErsatzTV don't list the episodes twice. To undo one episode, open it and press **↩ Put the original back**. When you're happy, press **Delete all backups** on the Tools page's library list. (Backups from before 2.7.6 sat next to the episodes. KNAS moves them into the hidden folder by itself. Rescan your media app afterwards to clear the doubles.)
   - It pauses on its own if the drive gets nearly full, or if lots of episodes in a row fail (for example, if the shows folder disconnects). Fix the problem and press **Continue**.
7. In ErsatzTV, **rescan** that show's library.

**Prefer to do it on a Windows PC?** The same break finder is also in `extras/windows` (with your shows on a mapped network drive):

1. Copy `Add Commercial Breaks.bat` and `knas-add-breaks.ps1` to the PC (keep them together).
2. **Drag a show's folder onto `Add Commercial Breaks.bat`** (season folders inside are included), or double-click it and pick the folder. Do it while nobody is watching that show.
3. For each episode it works out where breaks belong from the length (1 break for an 11-minute cartoon, 2 for a half-hour show, 4 for an hour show, about every 16 minutes for a movie), then looks around each spot for a real act break: a fade to black (best), or a scene change during a moment of silence. A plain pause in the middle of a scene doesn't count. If there's no clean break near a spot, it puts no break there rather than guessing. **Check first:** answer **Y** to "Just check first" and it only makes pictures of right before and after each break (in `_break previews` folders) without changing any files. Look through them, then run it again for real.
4. Nothing is re-encoded: only a chapter list is added, and each file is checked before it replaces the original. It asks if you want backup copies of the originals too. Files that can't hold chapters (like `.avi`) are re-wrapped as `.mkv`. Episodes that already have chapters are skipped, so it's safe to run again on a show folder after you add new episodes.
5. In ErsatzTV, **rescan** that library so it sees the new chapters.

**Getting the breaks in the middle of episodes:** in ErsatzTV, add the clip folders as a library (type **Other Videos**), make a **collection** of them, and make a **filler preset** set to **Mid-Roll** that uses that collection (for example 3 or 4 commercials per break). Then pick it in your schedule's **Mid-Roll filler**. ErsatzTV puts mid-roll breaks at the **chapter markers** in your episode files. Files with no chapters get no mid-roll breaks (that's what the commercial breaks tool above fixes). Keep your KNAS break clips as the **Fallback / Pad** filler so shows still start on the :00 and :30.

---

## 8. Updating

1. Download the new release's update `.zip` (`KNAS-<version>-update.zip`) from the GitHub **Releases** page.
2. Drop the zip, as is (don't unzip it), into the **`updates`** folder inside your KNAS folder.
3. Wait about a minute. KNAS installs it and restarts by itself.

Your settings, teams, facts, trivia, music, logos and clips are never touched. `updates/update-log.txt` shows what happened. A broken update is refused, and the working version keeps running.

`docker-compose.yml` is never changed by an update, so your Docker setup stays exactly as you made it.

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| ErsatzTV channels show **NO SIGNAL**, or play with **no sound** (but work in other apps) | Your ErsatzTV FFmpeg profile sends something browsers can't play. Set it to h264, 8-bit, aac, 2 audio channels. See [FFmpeg settings KNAS needs](#ffmpeg-settings-knas-needs). |
| Channel up goes the wrong way | Setup page → **Channels & screen** → **Channel up goes to…** |
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

**Which ports does it use?** `8642` for the web pages, plus `8643` (weather stream, off by default), `8644` (break recorder, only while making clips) and `8645` (the secure address for Live Cam, Duck Season and the voice remote). Both containers use host networking.

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
