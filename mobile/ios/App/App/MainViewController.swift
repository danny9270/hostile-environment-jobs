import Capacitor

// The app's web view, with the app's own native plugins added (the npm plugins register themselves).
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(WidgetPlugin())
    }
}
