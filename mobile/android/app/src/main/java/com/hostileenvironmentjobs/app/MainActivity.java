package com.hostileenvironmentjobs.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // The app's own native plugin (the npm plugins register themselves).
        registerPlugin(WidgetPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
