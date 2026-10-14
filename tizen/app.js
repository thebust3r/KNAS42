window.onerror = function (msg, src, line) {
  try { var e = document.getElementById("err") || document.body; document.getElementById("ask").style.display = "table";
        document.getElementById("start").style.display = "none"; e.textContent = "Something went wrong: " + msg + " (line " + line + ")"; } catch (x) {}
};
"use strict";
var KEY = "knas_url", PORT = 8642, timer = 0, mode = "", typed = "", scanId = 0;

/* Hand the remote's extra buttons to KNAS (channel up/down, numbers, guide, info, color buttons...) */
(function () {
  if (!window.tizen || !tizen.tvinputdevice) return;
  var keys = ["ChannelUp", "ChannelDown", "ChannelList", "PreviousChannel", "Info", "Guide", "Minus",
              "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
              "ColorF0Red", "ColorF1Green", "ColorF2Yellow", "ColorF3Blue",
              "MediaPlayPause", "MediaPlay", "MediaPause", "MediaStop", "MediaFastForward", "MediaRewind"];
  for (var i = 0; i < keys.length; i++) { try { tizen.tvinputdevice.registerKey(keys[i]); } catch (e) {} }
})();

function $(id) { return document.getElementById(id); }
function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
function hostOf(u) { var m = /^https?:\/\/([^\/:]+)/.exec(u || ""); return m ? m[1] : ""; }
function urlFor(ip) { return "http://" + ip + ":" + PORT + "/tv"; }
function show(id) { $("start").style.display = id === "start" ? "table" : "none"; $("ask").style.display = id === "ask" ? "table" : "none"; }

function useIp(ip) {
  var url = urlFor(ip);
  try { localStorage.setItem(KEY, url); } catch (e) {}
  mode = ""; scanId++;
  show("start"); $("where").textContent = ip;
  timer = setTimeout(function () { location.replace(url); }, 400);
}

/* Is KNAS at this address? Only counts if KNAS's own remote icon loads from it as a real picture,
   so a router or anything else on port 8642 can't fool it. */
function probe(ip, ms) {
  return new Promise(function (resolve) {
    var done = false, img = new Image();
    var t = setTimeout(function () { fin(false); }, ms);
    function fin(ok) { if (done) return; done = true; clearTimeout(t); img.onload = img.onerror = null; try { img.src = ""; } catch (e) {} resolve(ok); }
    img.onload = function () { fin(img.width > 8 && img.height > 8); };
    img.onerror = function () { fin(false); };
    img.src = "http://" + ip + ":" + PORT + "/remote-icon-192.png?probe=" + Date.now();
  });
}

/* This TV's own network (like 192.168.1), so we search the right addresses first */
function tvSubnet(cb) {
  var got = false;
  function from(v) { if (got || !v || !v.ipAddress) return; var m = /^(\d+\.\d+\.\d+)\.\d+$/.exec(v.ipAddress); if (m) { got = true; cb(m[1]); } }
  try {
    tizen.systeminfo.getPropertyValue("ETHERNET_NETWORK", from, function () {});
    tizen.systeminfo.getPropertyValue("WIFI_NETWORK", from, function () {});
  } catch (e) {}
  setTimeout(function () { if (!got) { got = true; cb(null); } }, 1500);
}

function scan() {
  var my = ++scanId;
  mode = "scan"; show("ask"); $("ip").style.display = "none";
  $("askTitle").textContent = "Finding KNAS…";
  $("askHint").innerHTML = "Press <b>OK</b> to type the address with the number buttons instead";
  $("err").textContent = "";
  tvSubnet(function (sub) {
    var nets = [], extra = ["192.168.1", "192.168.0", "10.0.0", "192.168.86", "192.168.68", "10.0.1", "192.168.2"];
    if (sub) nets.push(sub);
    for (var i = 0; i < extra.length; i++) if (nets.indexOf(extra[i]) < 0) nets.push(extra[i]);
    var hosts = [];
    for (var n = 0; n < nets.length; n++) for (var h = 1; h < 255; h++) hosts.push(nets[n] + "." + h);
    var next = 0, found = false, busy = 0, total = hosts.length;
    function pump() {
      if (my !== scanId || found) return;
      while (busy < 48 && next < total) {
        (function (ip) {
          busy++;
          probe(ip, 1800).then(function (ok) {
            busy--;
            if (my !== scanId || found) return;
            if (ok) { found = true; $("askMsg").textContent = "Found it at " + ip; useIp(ip); return; }
            pump();
          });
        })(hosts[next++]);
      }
      $("askMsg").textContent = "Looking for KNAS on your home network… " + Math.min(99, Math.round(next * 100 / total)) + "%";
      if (next >= total && busy === 0 && !found) {
        $("err").textContent = "Couldn't find KNAS by itself.";
        typeIt(sub ? sub + "." : "");
      }
    }
    pump();
  });
}

/* Type the address with the remote: numbers, ▶ for a dot, ◀ to erase, OK to connect */
function typeIt(start) {
  scanId++; mode = "type"; show("ask");
  if (typeof start === "string") typed = start;
  else { var cur = hostOf(saved()); typed = cur || typed; }
  $("askTitle").textContent = "Where's KNAS?";
  $("askMsg").innerHTML = "Type your NAS's address with the <b>number buttons</b>";
  $("askHint").innerHTML = "<b>▶</b> adds a dot &nbsp;·&nbsp; <b>◀</b> erases &nbsp;·&nbsp; <b>OK</b> connects &nbsp;·&nbsp; <span class=\"red\"></span> searches again";
  $("ip").style.display = "inline-block";
  draw();
}
function draw() { $("ipText").textContent = typed; }

function connectTyped() {
  var ip = typed.replace(/\.+$/, "");
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) { $("err").textContent = "That's not a full address yet (like 192.168.1.50)"; return; }
  $("err").textContent = "Checking " + ip + "…";
  probe(ip, 4000).then(function (ok) {
    if (mode !== "type") return;
    if (ok) useIp(ip);
    else $("err").textContent = "No KNAS at " + ip + ". Check the address and press OK again.";
  });
}

document.addEventListener("keydown", function (e) {
  var c = e.keyCode;
  if (mode === "scan") {
    if (c === 13) { e.preventDefault(); typeIt(); }
    else if (c === 10009 && saved()) { e.preventDefault(); location.replace(saved()); }
    return;
  }
  if (mode === "type") {
    e.preventDefault();
    if (c >= 48 && c <= 57) { if (typed.length < 15) typed += String(c - 48); }
    else if (c >= 96 && c <= 105) { if (typed.length < 15) typed += String(c - 96); }
    else if (c === 39 || c === 189 || c === 190 || c === 110) { if (typed && typed.slice(-1) !== ".") typed += "."; }
    else if (c === 37 || c === 8) { typed = typed.slice(0, -1); }
    else if (c === 13) { connectTyped(); return; }
    else if (c === 403) { scan(); return; }
    else if (c === 10009) { if (typed) typed = typed.slice(0, -1); else if (saved()) location.replace(saved()); }
    $("err").textContent = ""; draw();
    return;
  }
  if (c === 403 || c === 37 || c === 13) { e.preventDefault(); clearTimeout(timer); typeIt(); }   /* red, left or OK on "Tuning in": change the address */
});

/* Start: straight to KNAS if we know where it is (a moment to press red first), otherwise go find it */
(function () {
  var url = saved();
  if (!url) { scan(); return; }
  var ip = hostOf(url), t0 = Date.now();
  $("where").textContent = ip;
  probe(ip, 5000).then(function (ok) {
    if (mode) return;                                  /* they pressed OK/red to change it */
    if (!ok) { typed = ip; typeIt(); $("err").textContent = "Couldn't reach KNAS at " + ip + ". Fix the address, or press red to search."; return; }
    timer = setTimeout(function () { location.replace(url); }, Math.max(0, 1500 - (Date.now() - t0)));
  });
})();
