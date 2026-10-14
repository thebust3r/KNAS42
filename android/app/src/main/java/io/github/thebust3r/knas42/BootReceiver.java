package io.github.thebust3r.knas42;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** When the TV box starts up (or the app is updated) and "Open when the TV turns on" is on, start KNAS. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!WakeService.enabled(context)) return;
        WakeService.start(context);
        String a = intent.getAction();
        if (a != null && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) WakeService.openKnas(context);
    }
}
