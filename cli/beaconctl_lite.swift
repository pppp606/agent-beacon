// beaconctl-lite — zero-dependency Agent Beacon client (ADR 0005).
//
// For hosts that cannot install any library (no bleak, no uv): everything
// here is macOS-standard — CoreBluetooth + the Swift toolchain from Xcode
// Command Line Tools.
//
// Build:  make lite   (= swiftc -O cli/beaconctl_lite.swift -o cli/beaconctl-lite)
// Scope:  on / off / status only. No scan/use: the target beacon and this
//         host's color come from the same config file the Python CLI writes
//         (~/.config/agent-beacon/config.json); write it by hand here.
//
// Protocol logic (RMW, state description) mirrors cli/beaconctl.py and is
// locked to it by tests/protocol_vectors.json via tests/test_lite.py.

import CoreBluetooth
import Foundation

let serviceUUID = CBUUID(string: "7B1F0001-9F02-4C60-B0F7-A9F6A4B0BEAC")
let stateUUID = CBUUID(string: "7B1F0002-9F02-4C60-B0F7-A9F6A4B0BEAC")
let manufacturerID: UInt16 = 0xFFFF  // prototype only (ADR 0002)

let colorMask: UInt8 = 0x07
let blinkBit: UInt8 = 0x08
let colors: [String: UInt8] = [
    "red": 0x01, "green": 0x02, "blue": 0x04,
    "yellow": 0x03, "magenta": 0x05, "cyan": 0x06, "white": 0x07,
]
let hostColorDefault = "red"

func fail(_ message: String) -> Never {
    fputs(message + "\n", stderr)
    exit(1)
}

// ---------- pure logic (docs/protocol.md v0.2) ----------

func rmwSet(_ current: UInt8, _ colorBits: UInt8, blink: Bool) -> UInt8 {
    return current | (colorBits & colorMask) | (blink ? blinkBit : 0)
}

func rmwClear(_ current: UInt8, _ colorBits: UInt8) -> UInt8 {
    let state = current & ~(colorBits & colorMask)
    // Last host out writes 0x00: a leftover blink/reserved bit would
    // fail-safe to red and never turn off.
    return (state & colorMask) == 0 ? 0x00 : state
}

func describeState(_ state: UInt8) -> String {
    if state == 0x00 { return "off" }
    let bits = state & colorMask
    let blink = (state & blinkBit) != 0 ? " blink" : ""
    if bits == 0x00 { return "on red (fail-safe)\(blink)" }
    let names = [("red", UInt8(0x01)), ("green", UInt8(0x02)), ("blue", UInt8(0x04))]
        .filter { bits & $0.1 != 0 }.map { $0.0 }
    if names.count == 1 { return "on \(names[0])\(blink)" }
    return "on \(names.joined(separator: "+")) (cycle)\(blink)"
}

func shortId(fromManufacturerData data: Data) -> String? {
    let b = [UInt8](data)
    guard b.count >= 6 else { return nil }
    let company = UInt16(b[0]) | (UInt16(b[1]) << 8)
    guard company == manufacturerID else { return nil }
    let id = UInt32(b[2]) | (UInt32(b[3]) << 8) | (UInt32(b[4]) << 16) | (UInt32(b[5]) << 24)
    return String(format: "%08x", id)
}

// ---------- config (shared with cli/beaconctl.py) ----------

func loadConfig() -> (beaconId: String?, hostColor: String?) {
    let path = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".config/agent-beacon/config.json")
    guard let data = try? Data(contentsOf: path),
          let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
        return (nil, nil)
    }
    return (json["beacon_id"] as? String, json["host_color"] as? String)
}

// ---------- BLE client ----------

enum Op {
    case on(bits: UInt8, blink: Bool)
    case off(bits: UInt8)
    case status
}

final class BeaconClient: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    let targetId: String
    let op: Op
    var central: CBCentralManager!
    var peripheral: CBPeripheral?

    init(targetId: String, op: Op) {
        self.targetId = targetId
        self.op = op
        super.init()
    }

    func run(timeout: Double) {
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
            fail("Beacon \(self.targetId) not found.")
        }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            central.scanForPeripherals(withServices: [serviceUUID], options: nil)
        case .poweredOff:
            fail("Bluetooth is turned off. Turn it on in Control Center / System Settings and retry.")
        case .unauthorized:
            fail("Bluetooth permission denied for this terminal "
                 + "(System Settings > Privacy & Security > Bluetooth).")
        case .unsupported:
            fail("Bluetooth LE is not supported on this Mac.")
        default:
            break  // .unknown / .resetting: wait for the next state change
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        // Identify by Short ID from manufacturer data, never by name (ADR 0002);
        // stop scanning the moment the target is seen (same as the Python CLI).
        guard self.peripheral == nil,
              let mfr = advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data,
              shortId(fromManufacturerData: mfr) == targetId else { return }
        self.peripheral = peripheral
        central.stopScan()
        central.connect(peripheral, options: nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral,
                        error: Error?) {
        fail("Connect failed: \(error?.localizedDescription ?? "unknown error")")
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.delegate = self
        peripheral.discoverServices([serviceUUID])
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil,
              let svc = peripheral.services?.first(where: { $0.uuid == serviceUUID }) else {
            fail("Attention Service not found: \(error?.localizedDescription ?? "missing service")")
        }
        peripheral.discoverCharacteristics([stateUUID], for: svc)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                    error: Error?) {
        guard error == nil,
              let chr = service.characteristics?.first(where: { $0.uuid == stateUUID }) else {
            fail("Attention State characteristic not found: "
                 + (error?.localizedDescription ?? "missing characteristic"))
        }
        // on/off are read-modify-write on this host's color bit (protocol v0.2)
        peripheral.readValue(for: chr)
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                    error: Error?) {
        guard error == nil, let value = characteristic.value, !value.isEmpty else {
            fail("Read failed: \(error?.localizedDescription ?? "empty value")")
        }
        let current = value[value.startIndex]
        switch op {
        case .status:
            print(String(format: "0x%02x ", current) + describeState(current))
            finish()
        case .on(let bits, let blink):
            writeIfChanged(rmwSet(current, bits, blink: blink), current, characteristic)
        case .off(let bits):
            writeIfChanged(rmwClear(current, bits), current, characteristic)
        }
    }

    private func writeIfChanged(_ new: UInt8, _ current: UInt8, _ chr: CBCharacteristic) {
        if new == current {
            finish()
            return
        }
        peripheral!.writeValue(Data([new]), for: chr, type: .withResponse)
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic,
                    error: Error?) {
        if let error = error {
            fail("Write failed: \(error.localizedDescription)")
        }
        finish()
    }

    private func finish() {
        // Short-lived connection model (ADR 0001): disconnect, then exit.
        if let p = peripheral {
            central.cancelPeripheralConnection(p)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { exit(0) }
        } else {
            exit(0)
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                        error: Error?) {
        exit(0)
    }
}

// ---------- entry point ----------

func usage() -> Never {
    fputs("""
    usage: beaconctl-lite on [--color C] [--blink] [--timeout N]
           beaconctl-lite off [--color C] [--timeout N]
           beaconctl-lite status [--timeout N]

    Target beacon and host color come from ~/.config/agent-beacon/config.json:
      {"beacon_id": "5e6f7a8b", "host_color": "blue"}

    """, stderr)
    exit(2)
}

var args = Array(CommandLine.arguments.dropFirst())
guard let command = args.first else { usage() }
args.removeFirst()

// Test-only entry points (pure logic, no Bluetooth) for tests/test_lite.py
if command == "_rmw" {
    guard args.count == 4, let current = UInt8(args[1]), let bits = UInt8(args[2]),
          args[0] == "set" || args[0] == "clear" else { usage() }
    print(args[0] == "set" ? rmwSet(current, bits, blink: args[3] == "1")
                           : rmwClear(current, bits))
    exit(0)
}
if command == "_describe" {
    guard args.count == 1, let state = UInt8(args[0]) else { usage() }
    print(describeState(state))
    exit(0)
}

guard ["on", "off", "status"].contains(command) else { usage() }

var colorOpt: String?
var blink = false
var timeout = 10.0
var i = 0
while i < args.count {
    switch args[i] {
    case "--color":
        i += 1
        guard i < args.count else { usage() }
        colorOpt = args[i]
    case "--blink":
        blink = true
    case "--timeout":
        i += 1
        guard i < args.count, let t = Double(args[i]) else { usage() }
        timeout = t
    default:
        usage()
    }
    i += 1
}

let config = loadConfig()
guard let beaconId = config.beaconId?.lowercased() else {
    fail("No beacon configured. Write ~/.config/agent-beacon/config.json, e.g.\n"
         + "  {\"beacon_id\": \"5e6f7a8b\", \"host_color\": \"blue\"}")
}
let colorName = colorOpt ?? config.hostColor ?? hostColorDefault
guard let bits = colors[colorName] else {
    fail("Unknown color '\(colorName)'. Known: \(colors.keys.sorted().joined(separator: ", "))")
}

let op: Op
switch command {
case "on": op = .on(bits: bits, blink: blink)
case "off": op = .off(bits: bits)
default: op = .status
}

let client = BeaconClient(targetId: beaconId, op: op)
client.run(timeout: timeout)
RunLoop.main.run()
