# Agent Beacon BLE Protocol v0.1

BeaconデバイスはBLE peripheralとして動作し、「attentionが必要かどうか」という
1つの状態だけを受け取る。ホスト(Mac)がcentral。

## Beacon ID

各Beaconは永続的な一意IDを持つ(設計判断は [ADR 0002](adr/0002-beacon-identity.md))。

- **Full ID**: nRF52840 FICR DEVICEID(64bit)の16桁小文字hex表現
- **Short ID**: Full IDの下位32bit(末尾8桁)。Advertisingでの識別に使う

## Advertising

| フィールド | 内容 |
|---|---|
| Flags | LE General Discoverable |
| 128-bit Service UUID | Attention Service(プロダクト種別の発見用。全個体共通) |
| Manufacturer data | Company ID `0xFFFF`(2バイト, LE)+ Short ID(4バイト, LE)|
| Device name(scan response) | `AgentBeacon`(表示用。**識別には使わない**) |

ホストは Service UUID で「Agent Beaconであること」を発見し、
manufacturer data の Short ID で「どの個体か」を識別する。

Company ID `0xFFFF` はBluetooth SIGのテスト用予約値。試作フェーズ限定であり、
製品化時に再検討する(ADR 0002)。

## GATT

### Attention Service

- Service UUID: `7b1f0001-9f02-4c60-b0f7-a9f6a4b0beac`

### Attention State Characteristic

- Characteristic UUID: `7b1f0002-9f02-4c60-b0f7-a9f6a4b0beac`
- Properties: Read, Write
- 長さ: 1 byte 固定

ビット割り当て:

| bit | 意味 |
|---|---|
| 0 | 赤 |
| 1 | 緑 |
| 2 | 青 |
| 3 | 点滅(約2Hz) |
| 4-7 | 予約 |

- `0x00` = attention不要(消灯)。**消灯させる値は今後のバージョンでも `0x00` のみ**
- 非ゼロ = attention必要(点灯または点滅)
- 色はbit0-2のORで7色(例: `0x03`=黄、`0x07`=白)
- 例: `0x01`=赤点灯、`0x09`=赤点滅、`0x0e`=シアン点滅

**未知値・不正値の扱い(fail-safe)**: 非ゼロなら必ず点す。
色ビットがすべて0の非ゼロ値(予約bitのみ等)は**赤点灯にフォールバック**する。
これは「将来バージョンのホストが送るAttention状態を古いBeaconが受信しても、
通知を取りこぼさない」ためのfail-safe設計である。このプロダクトでは通知の
取りこぼし(false negative)が最も避けるべき故障モードであり、未知値を無視する
より点灯に倒す方が目的に合う。

- Readは現在の状態を返す(デバッグ用)。
- 電源投入直後の状態は `0x00`(消灯)。
- 切断されても状態は保持する(切断 ≠ OFF)。

### Device ID Characteristic

- Characteristic UUID: `7b1f0003-9f02-4c60-b0f7-a9f6a4b0beac`
- Properties: Read
- 長さ: 16 bytes 固定(ASCII、Full IDの16桁小文字hex)

デバッグおよびShort ID衝突時の最終確認用。

## セキュリティ

v0.1ではペアリング/ボンディングなし(open write)。試作機の脅威モデルでは許容し、
専用基板化の際に再評価する。
