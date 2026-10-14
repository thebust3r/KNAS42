package io.github.thebust3r.knas42;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityEvent;

/**
 * "Use KNAS as the home screen" on Google TV / Android TV boxes that won't let you pick another home app:
 * when the box's own home screen comes up (the Home button, waking up, starting up), KNAS opens instead.
 * Off unless you turn it on (KNAS settings + Settings -> Accessibility -> KNAS 42 Home button).
 * It only listens for the TV's home screen apps, and reads nothing on the screen.
 */
public class HomeButtonService extends AccessibilityService {

    static final String PREF_HOME = "home_override";
    static final String PREF_PAUSE_UNTIL = "home_pause_until";
    private long lastOpen = 0;

    static boolean on(Context c) {
        return c.getSharedPreferences("knas", MODE_PRIVATE).getBoolean(PREF_HOME, false);
    }

    /** "Other apps -> TV home screen": leave the TV's home screen alone for a while. */
    static void pause(Context c, long ms) {
        c.getSharedPreferences("knas", MODE_PRIVATE).edit().putLong(PREF_PAUSE_UNTIL, System.currentTimeMillis() + ms).apply();
    }

    static void resume(Context c) {
        c.getSharedPreferences("knas", MODE_PRIVATE).edit().remove(PREF_PAUSE_UNTIL).apply();
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        if (e == null || e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || e.getPackageName() == null) return;
        SharedPreferences p = getSharedPreferences("knas", MODE_PRIVATE);
        if (!p.getBoolean(PREF_HOME, false)) return;
        if (System.currentTimeMillis() < p.getLong(PREF_PAUSE_UNTIL, 0)) return;
        long now = SystemClock.uptimeMillis();
        if (now - lastOpen < 1500) return;
        lastOpen = now;
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        try { startActivity(i); } catch (Exception ignored) { }
    }

    @Override
    public void onInterrupt() { }
}
