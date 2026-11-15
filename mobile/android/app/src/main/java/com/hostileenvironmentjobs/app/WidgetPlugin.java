package com.hostileenvironmentjobs.app;

import android.content.Context;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

// Hands the rotation (days on, days off, first day of a hitch) to the home-screen countdown widget (RotaWidgetProvider).
// scripts/app.html calls this through window.HEJNative.widget whenever the rotation is saved.
@CapacitorPlugin(name = "HEJWidget")
public class WidgetPlugin extends Plugin {
    @PluginMethod
    public void setRota(PluginCall call) {
        Context ctx = getContext();
        ctx.getSharedPreferences(RotaWidgetProvider.PREFS, Context.MODE_PRIVATE).edit()
            .putInt("on", call.getInt("on", 0))
            .putInt("off", call.getInt("off", 0))
            .putString("start", call.getString("start", ""))
            .apply();
        RotaWidgetProvider.updateAll(ctx);
        call.resolve(new JSObject());
    }
}
