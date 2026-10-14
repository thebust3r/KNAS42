package io.github.thebust3r.knas42;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * App updates from GitHub: when the app opens (at most every few hours) it looks at the latest
 * KNAS release, and if it has a newer app, offers to install it. One press downloads and installs it.
 */
class Updater {

    static final String RELEASES = "https://api.github.com/repos/thebust3r/knas42/releases/latest";
    private static final long CHECK_EVERY_MS = 6 * 3600 * 1000L;

    private final Activity act;
    private final SharedPreferences prefs;
    private String pendingUrl, pendingVersion;
    boolean waitingForPermission = false;

    Updater(Activity act, SharedPreferences prefs) {
        this.act = act;
        this.prefs = prefs;
    }

    static String installedVersion(Context c) {
        try { return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName; } catch (Exception e) { return "0"; }
    }

    /** The app's internal build number for a version, the same way the build makes it: 1.1.1 -> 110101 */
    static long code(String v) {
        String[] x = (v.replaceAll("[^0-9.]", "") + ".0.0.0").split("\\.");
        int[] n = new int[3];
        for (int i = 0, j = 0; i < x.length && j < 3; i++) if (!x[i].isEmpty()) n[j++] = Integer.parseInt(x[i]);
        return 100000L + n[0] * 10000L + n[1] * 100L + n[2];
    }

    @SuppressWarnings("deprecation")
    static long installedCode(Context c) {
        try {
            android.content.pm.PackageInfo p = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? p.getLongVersionCode() : p.versionCode;
        } catch (Exception e) { return 0; }
    }

    /** "2.22.10" is newer than "2.22.9" */
    static boolean newer(String a, String b) {
        String[] x = a.replaceAll("[^0-9.]", "").split("\\."), y = b.replaceAll("[^0-9.]", "").split("\\.");
        for (int i = 0; i < Math.max(x.length, y.length); i++) {
            int p = i < x.length && !x[i].isEmpty() ? Integer.parseInt(x[i]) : 0;
            int q = i < y.length && !y[i].isEmpty() ? Integer.parseInt(y[i]) : 0;
            if (p != q) return p > q;
        }
        return false;
    }

    /** Look for a new version. quiet = only say something if there's an update. */
    void check(final boolean quiet) {
        long last = prefs.getLong("update_checked", 0);
        if (quiet && System.currentTimeMillis() - last < CHECK_EVERY_MS) return;
        if (!quiet) toast("Checking for updates…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                String version = null, apk = null;
                try {
                    JSONObject rel = new JSONObject(new String(get(RELEASES), "UTF-8"));
                    version = rel.optString("tag_name", "").replaceFirst("^[vV]", "");
                    JSONArray assets = rel.optJSONArray("assets");
                    for (int i = 0; assets != null && i < assets.length(); i++) {
                        JSONObject a = assets.getJSONObject(i);
                        if (a.optString("name").toLowerCase().endsWith(".apk")) apk = a.optString("browser_download_url");
                    }
                    prefs.edit().putLong("update_checked", System.currentTimeMillis()).apply();
                } catch (final Exception e) {
                    if (!quiet) toast("Couldn't check for updates (" + e.getClass().getSimpleName() + ")");
                    return;
                }
                final String v = version, url = apk, have = installedVersion(act);
                act.runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (v != null && url != null && code(v) > installedCode(act)) offer(v, url, have);
                        else if (!quiet) toast("The app is up to date (" + have + ")");
                    }
                });
            }
        }).start();
    }

    private void offer(final String version, final String url, String have) {
        if (act.isFinishing()) return;
        new AlertDialog.Builder(act)
                .setTitle("KNAS 42 app update")
                .setMessage("Version " + version + " is out (this TV has " + have + "). Install it now? It only takes a few seconds, and your settings stay.")
                .setPositiveButton("Install", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) { install(version, url); }
                })
                .setNegativeButton("Later", null)
                .show();
    }

    void install(String version, String url) {
        pendingVersion = version;
        pendingUrl = url;
        // Android asks once whether KNAS 42 may install updates for itself.
        if (Build.VERSION.SDK_INT >= 26 && !act.getPackageManager().canRequestPackageInstalls()) {
            new AlertDialog.Builder(act)
                    .setTitle("Allow app updates")
                    .setMessage("So KNAS 42 can update itself, Android needs you to allow \"Install unknown apps\" for KNAS 42. "
                            + "On the next screen, turn it on, then press back.")
                    .setPositiveButton("Open the setting", new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface d, int w) {
                            waitingForPermission = true;
                            try {
                                act.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + act.getPackageName())));
                            } catch (Exception e) {
                                waitingForPermission = false;
                                new AlertDialog.Builder(act).setTitle("Find it in Settings")
                                        .setMessage("Go to Settings → Apps → Security & restrictions (or Special app access) → Install unknown apps → KNAS 42, and turn it on. Then try the update again (hold Back → Check for app updates).")
                                        .setPositiveButton("OK", null).show();
                            }
                        }
                    })
                    .setNegativeButton("Later", null)
                    .show();
            return;
        }
        download();
    }

    /** Back from the "Install unknown apps" screen. */
    void resumed() {
        if (!waitingForPermission) return;
        waitingForPermission = false;
        if (Build.VERSION.SDK_INT >= 26 && act.getPackageManager().canRequestPackageInstalls() && pendingUrl != null) download();
    }

    private void download() {
        final String url = pendingUrl;
        toast("Downloading the update…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    byte[] apk = get(url);
                    PackageInstaller pi = act.getPackageManager().getPackageInstaller();
                    PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                    params.setAppPackageName(act.getPackageName());
                    int id = pi.createSession(params);
                    PackageInstaller.Session s = pi.openSession(id);
                    OutputStream out = s.openWrite("knas.apk", 0, apk.length);
                    out.write(apk);
                    s.fsync(out);
                    out.close();
                    Intent done = new Intent(act, InstallReceiver.class);
                    int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? 0x02000000 /* FLAG_MUTABLE */ : 0);
                    s.commit(PendingIntent.getBroadcast(act, id, done, flags).getIntentSender());
                    s.close();
                } catch (Exception e) {
                    toast("The update didn't download (" + e.getClass().getSimpleName() + "). Try again later.");
                }
            }
        }).start();
    }

    private static byte[] get(String url) throws Exception {
        for (int hops = 0; hops < 6; hops++) {          // GitHub sends downloads on to another address
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(15000);
            c.setReadTimeout(60000);
            c.setRequestProperty("User-Agent", "KNAS42-app");
            c.setRequestProperty("Accept", url.contains("api.github.com") ? "application/vnd.github+json" : "*/*");
            int code = c.getResponseCode();
            if (code >= 300 && code < 400 && c.getHeaderField("Location") != null) {
                url = new URL(new URL(url), c.getHeaderField("Location")).toString();
                c.disconnect();
                continue;
            }
            if (code != 200) throw new Exception("HTTP " + code);
            InputStream in = c.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] b = new byte[16384];
            int n;
            while ((n = in.read(b)) > 0) buf.write(b, 0, n);
            in.close();
            c.disconnect();
            return buf.toByteArray();
        }
        throw new Exception("too many redirects");
    }

    private void toast(final String msg) {
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() { Toast.makeText(act, msg, Toast.LENGTH_LONG).show(); }
        });
    }
}
