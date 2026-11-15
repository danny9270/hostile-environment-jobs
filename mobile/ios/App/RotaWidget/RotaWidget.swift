import SwiftUI
import WidgetKit

// Home-screen and lock-screen countdown to leave (or back to site), from the rotation set up in the app's Rota tab.
// Same rules as phase() in scripts/app.html: a cycle of `on` days on site then `off` days home, counted from `start`.

struct Rota {
    let on: Int, off: Int, start: Date?

    static func load() -> Rota {
        let d = UserDefaults(suiteName: "group.com.hostileenvironmentjobs.app")
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd"
        return Rota(on: d?.integer(forKey: "on") ?? 0, off: d?.integer(forKey: "off") ?? 0, start: f.date(from: d?.string(forKey: "start") ?? ""))
    }

    struct Phase { let left: Int; let what: String; let onsite: Bool; let progress: Double }

    func phase(on day: Date) -> Phase? {
        guard on > 0, off >= 0, let start else { return nil }
        let cal = Calendar.current
        let d = cal.dateComponents([.day], from: cal.startOfDay(for: start), to: cal.startOfDay(for: day)).day ?? 0
        if d < 0 { return Phase(left: -d, what: -d == 1 ? "day until you fly out" : "days until you fly out", onsite: false, progress: 0) }
        let cycle = on + off, p = d % cycle
        if p < on {
            let left = on - p
            return Phase(left: left, what: (left == 1 ? "day" : "days") + (off > 0 ? " to leave" : " left in this hitch"), onsite: true, progress: Double(p + 1) / Double(on))
        }
        let left = cycle - p
        return Phase(left: left, what: (left == 1 ? "day" : "days") + " until you fly back", onsite: false, progress: Double(p - on + 1) / Double(max(off, 1)))
    }
}

struct Entry: TimelineEntry { let date: Date; let phase: Rota.Phase? }

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> Entry { Entry(date: Date(), phase: .init(left: 14, what: "days to leave", onsite: true, progress: 0.5)) }
    func getSnapshot(in context: Context, completion: @escaping (Entry) -> Void) {
        completion(Entry(date: Date(), phase: Rota.load().phase(on: Date()) ?? placeholder(in: context).phase))
    }
    // One entry per day for the next week, each starting at midnight, then ask again.
    func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
        let rota = Rota.load(), cal = Calendar.current, today = cal.startOfDay(for: Date())
        let entries = (0..<7).compactMap { i -> Entry? in
            guard let day = cal.date(byAdding: .day, value: i, to: today) else { return nil }
            return Entry(date: i == 0 ? Date() : day, phase: rota.phase(on: day))
        }
        completion(Timeline(entries: entries, policy: .after(cal.date(byAdding: .day, value: 7, to: today)!)))
    }
}

let accent = Color(red: 0.95, green: 0.60, blue: 0.20)
let home = Color(red: 0.45, green: 0.75, blue: 0.45)

struct RotaView: View {
    @Environment(\.widgetFamily) var family
    let entry: Entry

    var body: some View {
        Group {
            if let p = entry.phase {
                switch family {
                case .accessoryCircular:
                    Gauge(value: p.progress) { Text(p.onsite ? "Leave" : "Back") } currentValueLabel: { Text("\(p.left)") }
                        .gaugeStyle(.accessoryCircular)
                case .accessoryRectangular:
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(p.left)").font(.system(size: 26, weight: .black, design: .rounded))
                        Text(p.what).font(.caption)
                    }
                case .accessoryInline:
                    Text("\(p.left) \(p.what)")
                default:
                    VStack(alignment: .leading, spacing: 6) {
                        Text(p.onsite ? "ON SITE" : "HOME").font(.system(size: 11, weight: .semibold, design: .monospaced)).foregroundStyle(.secondary)
                        Text("\(p.left)").font(.system(size: 52, weight: .black, design: .rounded)).foregroundStyle(p.onsite ? accent : home)
                            .minimumScaleFactor(0.5).lineLimit(1)
                        Text(p.what.uppercased()).font(.system(size: 13, weight: .heavy)).lineLimit(2)
                        Spacer(minLength: 0)
                        ProgressView(value: p.progress).tint(p.onsite ? accent : home)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    Text("ROTATION").font(.system(size: 11, weight: .semibold, design: .monospaced)).foregroundStyle(.secondary)
                    Text("Set up your rotation in the app's Rota tab.").font(.system(size: 14, weight: .semibold))
                }
            }
        }
        .containerBackground(for: .widget) { Color(red: 0.07, green: 0.08, blue: 0.07) }
    }
}

@main
struct RotaWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "RotaWidget", provider: Provider()) { RotaView(entry: $0) }
            .configurationDisplayName("Rotation countdown")
            .description("Days until leave, or until you fly back.")
            .supportedFamilies([.systemSmall, .accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}
