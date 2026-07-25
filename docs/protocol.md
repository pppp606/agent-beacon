# Agent Beacon BLE Protocol v0.2

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
- 例: `0x01`=赤点灯、`0x09`=赤点滅

### 表示(v0.2: 順繰り表示)

複数の色ビットが立っているときは、混色ではなく**立っているビットを
bit0→bit1→bit2の順に1色ずつ順繰りに表示**する(800ms/色)。
色ビットが1つだけならその色を連続点灯する。

| 状態バイト | 表示 |
|---|---|
| `0x01` | 赤の点灯 |
| `0x03` | 赤→緑→赤→…(800ms/色) |
| `0x07` | 赤→緑→青→赤→… |

点滅ビット(bit3)は表示全体に直交して適用する(順繰り表示中も全体が約2Hzで点滅)。

表示は「状態バイト + フェーズ番号 → その瞬間の1色」の純粋関数として定義され
(`attention_state.h` の `attention_display`)、書き込みの順序やタイミングに依存しない。

### ホスト割り当てとread-modify-write(v0.2規約)

複数ホストで1台のBeaconを共有するため、色ビットを**ホストごとの割り当て**として使う
([ADR 0004](adr/0004-multi-host-sharing.md)): 例 Mac A=赤(bit0)、Mac B=緑(bit1)、
Mac C=青(bit2)。状態バイトは「いま人間を待っているホストの集合」を表す。

各ホストは **read-modify-write** で自分のビットだけを操作する:

- **Attention発生**: readで現在値を取得 → 自分の色ビットを立てる(必要なら点滅ビットも)→ write
- **Attention解除**: readで現在値を取得 → 自分の色ビットだけを落とす → write。
  ただし**色ビットがすべて0になる場合は `0x00` を書く**(点滅ビット・予約ビットも
  一緒に消す)。点滅ビットだけが残るとfail-safeで赤点灯し、消せない誤点灯になるため

これはホスト側の規約であり、Beaconは関知しない(受け取ったバイトを表示するだけ)。
2ホストのread-modify-writeが同時に走った場合のlost updateは許容する(ADR 0004)。

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
