package io.github.thebust3r.knas42;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.provider.Settings;
import android.content.ComponentName;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import java.util.List;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

/**
 * KNAS 42 for Android and Android TV: the KNAS cable box, full screen.
 *
 * The first time it opens it asks for the NAS's address (like 192.168.1.50) and remembers it.
 * Hold BACK for a second for the menu: change the address, or "Open when the TV turns on".
 * The TV remote works like it does in a browser: arrows, OK, numbers, channel up/down, guide, info, back.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "knas";
    private static final String KEY_URL = "url";
    private static final int KNAS_PORT = 8642;

    private WebView web;
    private SharedPreferences prefs;
    private AlertDialog dialog;
    private long backDownAt = 0;
    private boolean backHeld = false;
    private boolean stopped = false;
    private long stoppedAt = 0;
    private Updater updater;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        web.setFocusable(true);
        web.setFocusableInTouchMode(true);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        root.addView(web, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
        setUpWebView();

        String url = prefs.getString(KEY_URL, null);
        if (saved != null && web.restoreState(saved) != null) {
            // picked up where it left off
        } else if (url == null) {
            askAddress(false);
        } else {
            open(url);
        }
        web.requestFocus();
        if (WakeService.enabled(this)) WakeService.start(this);
        updater = new Updater(this, prefs);
        if (url != null) updater.check(true);          // a new app version on GitHub? (at most every few hours)
    }

    private void setUpWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);     // channels start playing by themselves, like a TV
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setTextZoom(100);                               // a big system font size shouldn't break the guide
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        if (Build.VERSION.SDK_INT >= 21) s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        String version = "";
        try { version = getPackageManager().getPackageInfo(getPackageName(), 0).versionName; } catch (Exception ignored) { }
        s.setUserAgentString(s.getUserAgentString() + " KNASApp/" + version);   // lets KNAS know it's running in the app

        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return false;                             // every KNAS page stays inside the app
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return false;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (Build.VERSION.SDK_INT >= 23 && request.isForMainFrame()) cantConnect();
            }

            @Override
            @SuppressWarnings("deprecation")
            public void onReceivedError(WebView view, int code, String description, String failingUrl) {
                if (Build.VERSION.SDK_INT < 23) cantConnect();
            }
        });
    }

    /** "192.168.1.50", "192.168.1.50:8642" or "http://nas.local:8642/tv" -> http://192.168.1.50:8642/tv */
    static String normalize(String typed) {
        if (typed == null) return null;
        String t = typed.trim().replace(" ", "");
        if (t.isEmpty()) return null;
        if (!t.contains("://")) t = "http://" + t;
        Uri u = Uri.parse(t);
        String host = u.getHost();
        if (host == null || host.isEmpty()) return null;
        int port = u.getPort() > 0 ? u.getPort() : KNAS_PORT;
        String path = u.getEncodedPath();
        if (path == null || path.isEmpty() || path.equals("/")) path = "/tv";
        String scheme = u.getScheme() == null ? "http" : u.getScheme();
        String query = u.getEncodedQuery();
        return scheme + "://" + host + ":" + port + path + (query != null ? "?" + query : "");
    }

    private void open(String url) {
        web.loadUrl(url);
    }

    private void askAddress(final boolean cancelable) {
        if (dialog != null && dialog.isShowing()) dialog.dismiss();
        final EditText box = new EditText(this);
        box.setSingleLine(true);
        box.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        box.setImeOptions(EditorInfo.IME_ACTION_DONE);
        box.setHint("192.168.1.50");
        String cur = prefs.getString(KEY_URL, null);
        if (cur != null) {
            Uri u = Uri.parse(cur);
            box.setText(u.getHost() + (u.getPort() > 0 && u.getPort() != KNAS_PORT ? ":" + u.getPort() : ""));
            box.setSelection(box.getText().length());
        }
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        FrameLayout wrap = new FrameLayout(this);
        wrap.setPadding(pad, pad / 2, pad, 0);
        wrap.addView(box);

        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle("Where's KNAS?")
                .setMessage("Type your NAS's address, like 192.168.1.50. (It's the address you use for KNAS in a browser, without the :8642.)")
                .setView(wrap)
                .setCancelable(cancelable)
                .setPositiveButton("Watch", null);
        if (cancelable) b.setNegativeButton("Cancel", null);
        dialog = b.create();
        dialog.setOnShowListener(new DialogInterface.OnShowListener() {
            @Override
            public void onShow(DialogInterface d) {
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) { useAddress(box.getText().toString()); }
                });
                box.requestFocus();
            }
        });
        box.setOnEditorActionListener(new android.widget.TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(android.widget.TextView v, int actionId, KeyEvent event) {
                useAddress(box.getText().toString());
                return true;
            }
        });
        dialog.show();
    }

    private void useAddress(String typed) {
        String url = normalize(typed);
        if (url == null) {
            Toast.makeText(this, "Type an address like 192.168.1.50", Toast.LENGTH_LONG).show();
            return;
        }
        prefs.edit().putString(KEY_URL, url).apply();
        if (dialog != null) dialog.dismiss();
        open(url);
        web.requestFocus();
    }

    private void cantConnect() {
        if (isFinishing() || (dialog != null && dialog.isShowing())) return;
        String url = prefs.getString(KEY_URL, "");
        Uri u = Uri.parse(url);
        dialog = new AlertDialog.Builder(this)
                .setTitle("Can't reach KNAS")
                .setMessage("Couldn't connect to " + u.getHost() + ":" + (u.getPort() > 0 ? u.getPort() : KNAS_PORT)
                        + ".\n\nMake sure the NAS is on and this device is on the same Wi-Fi.")
                .setCancelable(false)
                .setPositiveButton("Try again", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String again = prefs.getString(KEY_URL, null);
                        if (again != null) open(again); else askAddress(false);
                    }
                })
                .setNeutralButton("Change address", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) { askAddress(false); }
                })
                .create();
        dialog.show();
    }

    /** Send a remote button to the KNAS page. The callback gets true when KNAS used it (closed the guide, say). */
    private void sendKey(String key, final ValueCallback<Boolean> done) {
        String js = "(function(){try{var e=new KeyboardEvent('keydown',{key:'" + key + "',bubbles:true,cancelable:true});"
                + "return document.dispatchEvent(e)?'0':'1'}catch(x){return '0'}})()";
        web.evaluateJavascript(js, new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String v) {
                if (done != null) done.onReceiveValue(v != null && v.contains("1"));
            }
        });
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        if (dialog != null && dialog.isShowing()) return super.dispatchKeyEvent(e);
        int code = e.getKeyCode();

        // BACK: closes the guide or banner in KNAS. Press it twice to leave the app. Hold it to change the address.
        if (code == KeyEvent.KEYCODE_BACK) {
            if (e.getAction() == KeyEvent.ACTION_DOWN) {
                if (e.getRepeatCount() == 0) {
                    backDownAt = SystemClock.uptimeMillis();
                    backHeld = false;
                } else if (!backHeld && SystemClock.uptimeMillis() - backDownAt > 900) {
                    backHeld = true;
                    showMenu();
                }
            } else if (e.getAction() == KeyEvent.ACTION_UP && !backHeld) {
                pressBack();
            }
            return true;
        }

        // Buttons a browser page doesn't get by itself: hand them to KNAS by name.
        String key = null;
        switch (code) {
            case KeyEvent.KEYCODE_CHANNEL_UP:
            case KeyEvent.KEYCODE_PAGE_UP:
                key = "ChannelUp"; break;
            case KeyEvent.KEYCODE_CHANNEL_DOWN:
            case KeyEvent.KEYCODE_PAGE_DOWN:
                key = "ChannelDown"; break;
            case KeyEvent.KEYCODE_GUIDE:
            case KeyEvent.KEYCODE_MENU:
            case KeyEvent.KEYCODE_TV_INPUT:
                key = "Guide"; break;
            case KeyEvent.KEYCODE_INFO:
                key = "Info"; break;
            case KeyEvent.KEYCODE_LAST_CHANNEL:
            case KeyEvent.KEYCODE_MEDIA_PREVIOUS:
                key = "ArrowLeft"; break;
            case KeyEvent.KEYCODE_MEDIA_NEXT:
                key = "ChannelUp"; break;
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_BUTTON_A:
                key = "Enter"; break;
            default:
                break;
        }
        if (key != null) {
            if (e.getAction() == KeyEvent.ACTION_DOWN) sendKey(key, null);
            return true;
        }
        return super.dispatchKeyEvent(e);
    }

    /** Hold BACK: the app's settings. */
    private void showMenu() {
        if (dialog != null && dialog.isShowing()) dialog.dismiss();
        final boolean auto = WakeService.enabled(this);
        final boolean home = isHome();
        String[] items = {
                "Change KNAS address",
                "Open when the TV turns on: " + (auto ? "ON (press to turn off)" : "OFF (press to turn on)"),
                "Use KNAS as the home screen: " + (home ? "ON (press to turn off)" : "OFF (press to turn on)"),
                "Other apps (Netflix, YouTube, settings...)",
                "Check for app updates (this is " + Updater.installedVersion(this) + ")",
                "Reload KNAS"
        };
        dialog = new AlertDialog.Builder(this)
                .setTitle("KNAS 42 app settings")
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which) {
                        if (which == 0) askAddress(true);
                        else if (which == 1) setAutoStart(!auto);
                        else if (which == 2) setHome(!home);
                        else if (which == 3) openOtherApps();
                        else if (which == 4) updater.check(false);
                        else web.reload();
                    }
                })
                .setNegativeButton("Close", null)
                .create();
        dialog.show();
    }

    // ---- "Use KNAS as the home screen": KNAS becomes the screen the TV turns on to (and where Home goes) ----

    private ComponentName homeAlias() {
        return new ComponentName(this, getPackageName() + ".Home");
    }

    private boolean isHome() {
        return HomeButtonService.on(this);
    }

    private boolean homeHelperEnabled() {
        String list = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return list != null && list.toLowerCase().contains((getPackageName() + "/").toLowerCase());
    }

    private void setHome(boolean on) {
        prefs.edit().putBoolean(HomeButtonService.PREF_HOME, on).apply();
        HomeButtonService.resume(this);
        // Regular Android TV boxes can also pick KNAS as their home app (Google TV ignores this)
        getPackageManager().setComponentEnabledSetting(homeAlias(),
                on ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED : PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                PackageManager.DONT_KILL_APP);
        if (!on) {
            Toast.makeText(this, "KNAS isn't the home screen anymore", Toast.LENGTH_LONG).show();
            return;
        }
        if (homeHelperEnabled()) {
            Toast.makeText(this, "KNAS is your home screen now. Press Home to try it.", Toast.LENGTH_LONG).show();
            return;
        }
        dialog = new AlertDialog.Builder(this)
                .setTitle("One more step")
                .setMessage("So the Home button opens KNAS, turn on \"KNAS 42 Home button\" in the TV's Accessibility settings.\n\n"
                        + "On the next screen, find KNAS 42 Home button (it may be under \"Downloaded apps\" or \"Services\"), turn it on and press back.\n\n"
                        + "It only watches for the TV's home screen; it doesn't read anything on your screen.")
                .setPositiveButton("Open the setting", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) { justAskedHome = true; openAccessibilitySettings(); }
                })
                .setNegativeButton("Later", null)
                .create();
        dialog.show();
    }

    private boolean justAskedHome = false;

    private void openAccessibilitySettings() {
        try {
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        } catch (Exception e) {
            dialog = new AlertDialog.Builder(this).setTitle("Find it in Settings")
                    .setMessage("Go to Settings → System → Accessibility → KNAS 42 Home button, and turn it on.")
                    .setPositiveButton("OK", null).create();
            dialog.show();
        }
    }

    /** Your other apps (Netflix, YouTube...), plus the TV's own home screen, in a list. */
    private void openOtherApps() {
        final List<String> names = new java.util.ArrayList<String>();
        final List<Intent> intents = new java.util.ArrayList<Intent>();
        final List<Boolean> isHomeScreen = new java.util.ArrayList<Boolean>();
        PackageManager pm = getPackageManager();

        // The TV's own home screen first
        Intent h = new Intent(Intent.ACTION_MAIN);
        h.addCategory(Intent.CATEGORY_HOME);
        for (ResolveInfo r : pm.queryIntentActivities(h, 0)) {
            if (r.activityInfo == null) continue;
            String pkg = r.activityInfo.packageName;
            if (getPackageName().equals(pkg) || pkg.contains("settings") || pkg.contains("fallbackhome") || pkg.contains("setupwizard")) continue;
            Intent i = new Intent(Intent.ACTION_MAIN);
            i.addCategory(Intent.CATEGORY_HOME);
            i.setClassName(pkg, r.activityInfo.name);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            names.add("TV home screen (" + r.loadLabel(pm) + ")");
            intents.add(i);
            isHomeScreen.add(true);
            break;
        }

        // Then every app, the TV kind first (Leanback), phone-style ones if there are no TV ones
        java.util.TreeMap<String, Intent> apps = new java.util.TreeMap<String, Intent>(String.CASE_INSENSITIVE_ORDER);
        String[] cats = {"android.intent.category.LEANBACK_LAUNCHER", Intent.CATEGORY_LAUNCHER};
        java.util.HashSet<String> seen = new java.util.HashSet<String>();
        for (String cat : cats) {
            Intent q = new Intent(Intent.ACTION_MAIN);
            q.addCategory(cat);
            for (ResolveInfo r : pm.queryIntentActivities(q, 0)) {
                if (r.activityInfo == null) continue;
                String pkg = r.activityInfo.packageName;
                if (getPackageName().equals(pkg) || seen.contains(pkg)) continue;
                seen.add(pkg);
                Intent i = new Intent(Intent.ACTION_MAIN);
                i.addCategory(cat);
                i.setClassName(pkg, r.activityInfo.name);
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
                apps.put(String.valueOf(r.loadLabel(pm)), i);
            }
        }
        for (java.util.Map.Entry<String, Intent> a : apps.entrySet()) {
            names.add(a.getKey());
            intents.add(a.getValue());
            isHomeScreen.add(false);
        }
        if (names.isEmpty()) {
            try { startActivity(new Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); } catch (Exception ignored) { }
            return;
        }
        if (dialog != null && dialog.isShowing()) dialog.dismiss();
        dialog = new AlertDialog.Builder(this)
                .setTitle("Other apps")
                .setItems(names.toArray(new String[0]), new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which) {
                        // Going to the TV's home screen on purpose: don't bounce back to KNAS for a while
                        if (isHomeScreen.get(which)) HomeButtonService.pause(MainActivity.this, 15 * 60 * 1000L);
                        try { startActivity(intents.get(which)); } catch (Exception e) {
                            Toast.makeText(MainActivity.this, "Couldn't open that app", Toast.LENGTH_LONG).show();
                        }
                    }
                })
                .setNegativeButton("Close", null)
                .create();
        dialog.show();
    }

    private void setAutoStart(boolean on) {
        prefs.edit().putBoolean(WakeService.PREF_AUTOSTART, on).apply();
        if (!on) {
            WakeService.stop(this);
            Toast.makeText(this, "KNAS won't open by itself anymore", Toast.LENGTH_LONG).show();
            return;
        }
        WakeService.start(this);
        // Newer Android only lets an app open itself if it's allowed to "display over other apps".
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            dialog = new AlertDialog.Builder(this)
                    .setTitle("One more step")
                    .setMessage("So KNAS can open by itself when the TV turns on, Android needs you to allow "
                            + "\"Display over other apps\" for KNAS 42.\n\nOn the next screen, find KNAS 42 and turn it on, then press back.")
                    .setPositiveButton("Open the setting", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface d, int w) { justAskedOverlay = true; openOverlaySetting(); }
                    })
                    .setNegativeButton("Later", null)
                    .create();
            dialog.show();
        } else {
            Toast.makeText(this, "KNAS will open when the TV turns on", Toast.LENGTH_LONG).show();
        }
    }

    private void openOverlaySetting() {
        try {
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
            return;
        } catch (Exception ignored) { }
        try {
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION));
            return;
        } catch (Exception ignored) { }
        dialog = new AlertDialog.Builder(this)
                .setTitle("Find it in Settings")
                .setMessage("This TV doesn't open that setting directly. Go to Settings → Apps → Special app access → "
                        + "Display over other apps → KNAS 42, and turn it on.")
                .setPositiveButton("OK", null)
                .create();
        dialog.show();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (updater != null) updater.resumed();
        HomeButtonService.resume(this);
        if (justAskedHome) {
            justAskedHome = false;
            if (homeHelperEnabled()) Toast.makeText(this, "All set: the Home button opens KNAS now", Toast.LENGTH_LONG).show();
        }
        if (WakeService.enabled(this) && Build.VERSION.SDK_INT >= 23 && Settings.canDrawOverlays(this) && justAskedOverlay) {
            justAskedOverlay = false;
            Toast.makeText(this, "All set: KNAS will open when the TV turns on", Toast.LENGTH_LONG).show();
        }
    }

    private boolean justAskedOverlay = false;

    private void pressBack() {
        sendKey("GoBack", new ValueCallback<Boolean>() {
            @Override
            public void onReceiveValue(Boolean used) {
                if (used) return;                              // KNAS closed something (the guide, a banner...)
                if (isFinishing() || (dialog != null && dialog.isShowing())) return;
                final boolean home = isHome();
                dialog = new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Leave KNAS?")
                        .setPositiveButton(home ? "Other apps" : "Exit", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) { if (home) openOtherApps(); else finish(); }
                        })
                        .setNeutralButton("Settings", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) { showMenu(); }
                        })
                        .setNegativeButton("Stay", null)
                        .create();
                dialog.show();
            }
        });
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && Build.VERSION.SDK_INT >= 19) {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override
    protected void onStop() {
        super.onStop();
        stopped = true;
        stoppedAt = SystemClock.elapsedRealtime();
        web.evaluateJavascript("try{document.querySelectorAll('video,audio').forEach(function(v){v.pause()})}catch(e){}", null);
        web.onPause();
        web.pauseTimers();
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (stopped) {                                    // back on: pick up right where it was, no reloading
            stopped = false;
            web.onResume();
            web.resumeTimers();
            if (prefs.getString(KEY_URL, null) == null) return;
            if (SystemClock.elapsedRealtime() - stoppedAt > 6 * 3600 * 1000L) {
                web.reload();                             // off for hours: start fresh
            } else {
                web.evaluateJavascript("try{if(typeof SLEEP!=='undefined'&&SLEEP&&typeof wake==='function')wake();"
                        + "else if(window.CH&&CH.length&&typeof tune==='function')tune(cur<0?0:cur,{now:true});"
                        + "else location.reload()}catch(e){location.reload()}", null);
            }
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        if (dialog != null) dialog.dismiss();
        if (web != null) {
            web.stopLoading();
            web.destroy();
        }
        super.onDestroy();
    }
}
