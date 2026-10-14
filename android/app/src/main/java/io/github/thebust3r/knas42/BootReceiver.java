package io.github.thebust3r.knas42;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** When the TV box starts up and "Open when the TV turns on" is on, start KNAS. Right after an app update, reopen KNAS. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String a = intent.getAction();
        if (Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) {           // just updated itself: back to KNAS
            if (WakeService.enabled(context)) WakeService.start(context);
            WakeService.openKnas(context);
            return;
        }
        if (!WakeService.enabled(context)) return;
        WakeService.start(context);
        WakeService.openKnas(context);
    }
}
