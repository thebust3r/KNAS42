# KNAS 42 📺

**A 90s cable box for any screen.** Flip through channels with static in between, open a retro TV guide, and watch a "local forecast" weather channel, live scores for your teams and your own shows.

It runs on your home server in Docker. Watch it on any TV, computer, phone or old CRT that has a web browser. No accounts, no sign-ups, nothing to pay for.

![KNAS 42](docs/images/hero.jpg)

---

## What you get

- 📺 **A cable box:** a 90s TV guide, channel banners and static between channels. Works with a TV remote, a game controller, a mouse or swipes on a phone.
- ⛅ **A weather channel:** your local forecast, a moving radar map, news headlines and smooth jazz, like the 90s weather channel.
- 🏈 **A sports channel:** live scores for your teams, play-by-play, and a cheer when your team scores.
- ⏸️ **A "We'll be right back" screen:** trivia, fun facts and what's coming up next.
- 🎬 **Your own shows (optional):** if you use [ErsatzTV](https://ersatztv.org), your shows and movies become channels in the guide.
- 🎃 **Holiday looks:** snow at Christmas, bats at Halloween, fireworks on the Fourth, and more.
- 🎨 **Make it yours:** 10 color themes, 18 fonts, 4 guide styles and your own logos.

| | |
|:---:|:---:|
| ![TV guide](docs/images/guide.jpg) **The TV guide** | ![Weather](docs/images/weather.jpg) **The weather channel** |
| ![Sports](docs/images/sports.jpg) **Live sports** | ![Break screen](docs/images/break.jpg) **Break screen trivia** |
| ![Radar](docs/images/radar.jpg) **The radar map** | ![Holiday look](docs/images/holiday.jpg) **Holiday looks** |

---

## Install it (3 steps)

**You need:** a computer that's always on and runs Docker. A NAS (UGREEN, Synology, QNAP…), a Linux PC, a mini PC or a Raspberry Pi 4/5 all work.

**1. Download it.** Click the green **Code** button above, then **Download ZIP**. Unzip it and copy the folder onto your server.

**2. Start it.** In your NAS's Docker app, create a new **Project** (some apps call it a **Stack**) and point it at that folder. The first start takes 5 to 10 minutes.

<details>
<summary>Using the command line instead?</summary>

```sh
cd /path/to/the/knas/folder
docker compose up -d --build
```
</details>

**3. Watch.** On your TV, computer or phone, open:

```
http://YOUR-SERVER-IP:8642/tv
```

**That's it.** There's nothing you have to set up. KNAS figures out your town for the weather by itself.

> **What's my server's IP?** It's your server's address on your home network, like `192.168.1.50`. Your NAS shows it in its network settings, and the KNAS log in your Docker app prints the exact link when it starts.

---

## Want to change something? (optional)

Open **`http://YOUR-SERVER-IP:8642/setup`** on any device at home. You can:

- fix your town if the guess is wrong
- add your sports teams
- connect ErsatzTV
- pick colors, fonts and holiday looks

Every setting there is optional.

![Setup page](docs/images/setup.jpg)

---

## Common questions

**Do I need ErsatzTV?**
No. Without it you still get the weather, sports and break channels. ErsatzTV just adds your own shows and movies to the guide.

**What can I watch it on?**
Anything with a web browser: a TV box like an Onn or Fire TV, a smart TV, an Xbox, a computer, a phone, or an old CRT TV hooked up through a converter. On an Android TV box, [Fully Kiosk Browser](https://www.fully-kiosk.com/) works best.

**How do I update it?**
Download the new update `.zip` and drop it in the `updates` folder. Don't unzip it. KNAS updates itself within a minute and keeps all your settings.

**Where are my settings saved?**
In `settings.txt` in the KNAS folder. The setup page edits it for you.

**Something's not working?**
See the troubleshooting section at the end of the setup guide.

### 📖 [Full step-by-step guide](docs/SETUP-GUIDE.md)

The guide covers everything in detail: installing on each type of NAS, watching on every kind of device, connecting ErsatzTV, and setting up break clips for ErsatzTV (on the same NAS, on a Windows PC or on a Mac).

---

<details>
<summary><b>Technical details (ports, files, credits)</b></summary>

**Ports** (both containers use host networking)

| Port | What it's for |
|---|---|
| 8642 | The web pages and the setup page |
| 8643 | The weather channel as live video for ErsatzTV (off unless you turn it on) |
| 8644 | The break screen recorder (only runs while making break clips) |

**Your files:** settings are in `settings.txt`, your own facts and trivia are in `facts.txt` and `trivia.txt`, and your teams are in `teams.txt`. Updates never overwrite them.

**Credits**
- Weather and town lookup: [Open-Meteo](https://open-meteo.com).
- Guessing your town until you set one: [ipwho.is](https://ipwho.is), with [ipapi.co](https://ipapi.co) and [freeipapi.com](https://freeipapi.com) as backups (asked at most once a week, and never once you set a town).
- Radar: [RainViewer](https://www.rainviewer.com).
- Maps and town names: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Scores: ESPN's public site API (unofficial, may change).
- Trivia: [Open Trivia Database](https://opentdb.com) (CC BY-SA 4.0).
- Facts and On This Day: Wikipedia.
- Video playback: [hls.js](https://github.com/video-dev/hls.js).
- Fonts (SIL Open Font License or Apache 2.0, licenses in `web/fonts`): Barlow, Barlow Condensed, Fira Sans Condensed, Roboto Condensed, Oswald, Asap Condensed, Saira Condensed, Lexend, Nunito, Bebas Neue, Exo 2, Righteous, VT323, Space Mono, Fredoka, Comic Neue, Patrick Hand, Roboto Slab, Playfair Display.

Not affiliated with any of the above, or with any real TV network or cable company. KNAS saves everything it downloads, so it's gentle on these free services.

</details>

## License

MIT, free to use, change and share. See [`LICENSE`](LICENSE).
