**Already have KNAS?** Download `KNAS-1.1.6-update.zip` below and drop it (still zipped) into your `updates` folder. Your settings stay.
**New install on a Windows PC?** Download `KNAS42-Setup-1.1.6.exe` below and run it: no Docker needed. (Mac or Docker Desktop: `install-knas.sh` / `Install-KNAS-Windows.bat`.) On a NAS, follow the README.
**Samsung TV?** Download `KNAS-42-Samsung-1.1.6.wgt` below and install it with TizenBrew Installer (install from a file). The TV needs Developer Mode on.
**Android TV box or Android phone?** Download `KNAS-42-1.1.6.apk` below and install it. ([How](https://github.com/thebust3r/knas42/blob/main/docs/SETUP-GUIDE.md#android-tv-box-onn-chromecast-with-google-tv-fire-tv-and-android-phones))

## New in 1.1.6
- KNAS for Windows: an installer (KNAS42-Setup) that runs KNAS as a normal Windows program, no Docker. Icon by the clock with setup, the TV address and the phone remote; starts with Windows; finds ErsatzTV on the same PC by itself
- The guide on phones: slide a finger and the highlight follows it channel by channel; drag past the edge to keep scrolling
- iPhones use lite mode, and the Doppler radar no longer runs phones out of memory
- The TV address shown everywhere is your home address, even with a VPN on (LAN_IP in settings to set it yourself)
- KNAS finds its own Tailscale address and shares it with the KNAS apps for watching away from home (TAILSCALE_ADDRESS in settings to set one)
- Commercial splitter: fixed the ffmpeg download error, and it finds far more breaks (fuzzy VHS black, quiet cuts, commercial lengths). Add Commercial Breaks got the same download fix

## New in 1.1.5
- One-click installer for Windows (and Mac/Linux): sets up KNAS in Docker Desktop with the right settings and opens the setup page. Run it again to update
- The startup log says to use localhost when running in Docker Desktop, instead of only Docker's internal address

## New in 1.1.4
- Android TV app: the Home button really goes to KNAS on Google TV boxes (Onn, Chromecast) when "Use KNAS as the home screen" is on, and "Other apps" shows a list of your installed apps
- The guide no longer runs channel numbers into names on older TVs, and holiday effects use less power on TV boxes
- A Samsung TV app: install the KNAS-42-Samsung .wgt with TizenBrew Installer and KNAS opens full screen with the whole remote working (PRE-CH and CH LIST too)

## New in 1.1.3
- Install straight from your NAS's Docker app: search for knas42, map an empty folder to /knas, use host network, start. The first start sets everything up, and a newer image updates it (your settings stay)
- KNAS is on Docker Hub too, so it shows up in Docker app image searches

## New in 1.1.2
- The setup page tells you when a new KNAS is out, with what's new and a download button
- The break-clip recorder (knas42-cast) is optional on new installs: it only starts if you turn on break clips

## New since the first GitHub version

**KNAS 42 app (Android and Android TV)**
- Opens straight to the cable box, full screen
- TV remote works: arrows, OK, numbers, channel up/down, guide, info, back
- Can open by itself when the TV turns on, right away, picking up where you left off (hold Back → Settings)
- The app updates itself. When a new version is on GitHub it asks "Install now?" and does it with one press.
- "Use KNAS as the home screen", so the TV turns on straight to KNAS with no home screen first. Your other apps are under Settings → Other apps. (Google TV boxes like Onn need a one-time step from a computer, see the setup guide.)

**Phone remote**
- Remote at /remote, works on any TV in the house (channels, guide, number pad, last channel, info)
- Can save it to your home screen like an app
- Volume slider and mute
- What's on list: every channel, what's on now and next, tap to tune
- Name your TVs and pick which channels each one shows
- Turn off all TVs button (good-night screen, any button wakes it)
- Degauss button
- Phone menu at /phone with everything in one place

**Cable box and guide**
- Volume and mute on the cable box itself, with an on-screen volume bar
- Guide shows how many TVs are on each channel
- New guide style, "Cable listings 2000s": live channel in the corner, shows color-coded (sports green, movies purple, kids light blue)
- Setting for whether channel up follows the guide or goes to the next number

**Sports**
- Score bug in the corner while your team plays: always on, only when they score, or on and off every few minutes

**Stats**
- Viewing history at /history
- Ratings at /ratings: weekly top channels and shows, up/down vs last week, who's watching now
- Wrapped at /wrapped: your year in TV, can also be its own channel

**ErsatzTV**
- Tells ErsatzTV to rescan the break clips when they change (fixes "media isn't available")
- Clip copier fills in the ErsatzTV API key for you

**Fixes**
- Weather channel loads way faster
- Fresh installs take about a minute now instead of 5 to 10
- A bunch of bug fixes
