import Capacitor
import WidgetKit

// Hands the rotation (days on, days off, first day of a hitch) to the home-screen countdown widget (RotaWidget).
// The widget works out the countdown itself from these three numbers, so the app only writes them when they change.
// Both share the App Group below; scripts/app.html calls this through window.HEJNative.widget.
@objc(WidgetPlugin)
public class WidgetPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "WidgetPlugin"
    public let jsName = "HEJWidget"
    public let pluginMethods: [CAPPluginMethod] = [CAPPluginMethod(name: "setRota", returnType: CAPPluginReturnPromise)]
    static let group = "group.com.hostileenvironmentjobs.app"

    @objc func setRota(_ call: CAPPluginCall) {
        guard let shared = UserDefaults(suiteName: WidgetPlugin.group) else { return call.reject("No shared storage") }
        shared.set(call.getInt("on") ?? 0, forKey: "on")
        shared.set(call.getInt("off") ?? 0, forKey: "off")
        shared.set(call.getString("start") ?? "", forKey: "start")
        WidgetCenter.shared.reloadAllTimelines()
        call.resolve()
    }
}
