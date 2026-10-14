package io.github.thebust3r.knas42;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;

/**
 * "Open when the TV turns on": a small background helper that waits for the TV to wake up
 * (the screen turning on, or the screensaver ending) and opens KNAS.
 * Android only shows a running-app notice for it; nothing else happens until the TV wakes.
 */
public class WakeService extends Service {

    static final String PREF_AUTOSTART = "autostart";
    private static final String CHANNEL = "knas-wake";
    private BroadcastReceiver wake;
    private long lastOpen = 0;

    static boolean enabled(Context c) {
        return c.getSharedPreferences("knas", MODE_PRIVATE).getBoolean(PREF_AUTOSTART, false);
    }

    static void start(Context c) {
        Intent i = new Intent(c, WakeService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
        } catch (Exception ignored) { }
    }

    static void stop(Context c) {
        c.stopService(new Intent(c, WakeService.class));
    }

    static void openKnas(Context c) {
        Intent i = new Intent(c, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        try { c.startActivity(i); } catch (Exception ignored) { }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        goForeground();
        wake = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                long now = SystemClock.uptimeMillis();
                if (now - lastOpen < 5000) return;
                lastOpen = now;
                // give the TV a moment to finish waking before opening KNAS
                new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
                    @Override
                    public void run() { if (enabled(WakeService.this)) openKnas(WakeService.this); }
                }, 1200);
            }
        };
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_DREAMING_STOPPED);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(wake, f, Context.RECEIVER_EXPORTED);
        else registerReceiver(wake, f);
    }

    private void goForeground() {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Open when the TV turns on", NotificationManager.IMPORTANCE_MIN);
            ch.setShowBadge(false);
            if (nm != null) nm.createNotificationChannel(ch);
            b = new Notification.Builder(this, CHANNEL);
        } else {
            b = new Notification.Builder(this);
        }
        Notification n = b.setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("KNAS 42")
                .setContentText("Opens KNAS when the TV turns on")
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(42, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(42, n);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (!enabled(this)) { stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (wake != null) try { unregisterReceiver(wake); } catch (Exception ignored) { }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
