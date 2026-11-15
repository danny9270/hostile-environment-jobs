package com.hostileenvironmentjobs.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;
import java.util.Calendar;
import java.util.TimeZone;

// Home-screen countdown to leave (or back to site), from the rotation set up in the app's Rota tab.
// Same rules as phase() in scripts/app.html. Android refreshes it every few hours and whenever the rotation changes.
public class RotaWidgetProvider extends AppWidgetProvider {
    static final String PREFS = "hej_widget";

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) mgr.updateAppWidget(id, views(ctx));
    }

    static void updateAll(Context ctx) {
        AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
        int[] ids = mgr.getAppWidgetIds(new ComponentName(ctx, RotaWidgetProvider.class));
        for (int id : ids) mgr.updateAppWidget(id, views(ctx));
    }

    // Whole days from a "YYYY-MM-DD" date to today on this phone (java.time needs a newer Android than the app supports).
    static long daysSince(String ymd) {
        String[] a = ymd.split("-");
        Calendar from = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        from.clear(); from.set(Integer.parseInt(a[0]), Integer.parseInt(a[1]) - 1, Integer.parseInt(a[2]));
        Calendar now = Calendar.getInstance();
        Calendar to = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        to.clear(); to.set(now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH));
        return Math.round((to.getTimeInMillis() - from.getTimeInMillis()) / 86400000.0);
    }

    static RemoteViews views(Context ctx) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        int on = p.getInt("on", 0), off = p.getInt("off", 0);
        String start = p.getString("start", "");
        RemoteViews v = new RemoteViews(ctx.getPackageName(), R.layout.rota_widget);
        String where = "ROTATION", num = "", what = "Set up your rotation in the app's Rota tab";
        int colour = 0xFFF29A33;
        try {
            if (on > 0 && off >= 0 && start.matches("\\d{4}-\\d\\d-\\d\\d")) {
                long d = daysSince(start);
                long left;
                if (d < 0) {
                    left = -d; where = "BEFORE YOU GO"; what = left == 1 ? "day until you fly out" : "days until you fly out";
                } else {
                    long cycle = on + off, ph = d % cycle;
                    if (ph < on) {
                        left = on - ph; where = "ON SITE";
                        what = (left == 1 ? "day" : "days") + (off > 0 ? " to leave" : " left in this hitch");
                    } else {
                        left = cycle - ph; where = "HOME"; colour = 0xFF73BF73;
                        what = (left == 1 ? "day" : "days") + " until you fly back";
                    }
                }
                num = String.valueOf(left);
            }
        } catch (Exception ignored) {}
        v.setTextViewText(R.id.rota_where, where);
        v.setTextViewText(R.id.rota_num, num);
        v.setTextColor(R.id.rota_num, colour);
        v.setTextViewText(R.id.rota_what, what.toUpperCase());
        Intent open = new Intent(ctx, MainActivity.class);
        v.setOnClickPendingIntent(R.id.rota_root, PendingIntent.getActivity(ctx, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        return v;
    }
}
