# ADR 0002: Beaconの個体識別

- Status: Accepted
- Date: 2026-07-24

## Context

複数のMac / AI実行環境それぞれに物理Beaconを対応付ける構成(Mac A → Beacon A、
Mac B → Beacon B、…)が想定される。全個体が同じDevice name(`AgentBeacon`)と
同じService UUIDしか持たないと、ホストは「自分が光らせるべきBeacon」を安定して
識別できない。これはUIの問題ではなく初期プロトコルの識別子設計の問題であり、
v0.1から入れる。

制約:

- **macOSのCoreBluetoothはperipheralのBLE MACアドレスをアプリに公開しない。**
  ホストから見えるのはmacOSが生成したper-MacのペリフェラルUUIDで、これは
  Mac間で共有できず、同一Macでも再生成されうる。→ MACアドレスもCoreBluetoothの
  UUIDも、設定に保存する永続IDとしては使えない。
- 識別は接続前(scan段階)にできる必要がある。全候補に接続してIDを読む方式は
  複数台環境で遅く不安定。

## Decision

### IDの源泉: nRF52840 FICR DEVICEID

Beacon IDには nRF52840 の **FICR(Factory Information Configuration Registers)の
DEVICEID(64bit)** を使う。工場書き込みで実質一意、書き換え不可、ファームウェア
更新でも変わらない。追加のプロビジョニング作業(IDの採番・書き込み)が不要。

- **Full ID**: 64bitを16桁の小文字hexで表現(例: `1a2b3c4d5e6f7a8b`)
- **Short ID**: Full IDの下位32bit = 末尾8桁(例: `5e6f7a8b`)。
  Advertisingパケットの容量制約(31バイト)のための短縮形。
  個人〜チーム規模の台数では32bitの衝突は実質無視できる。

### 接続前の識別: Advertising manufacturer data

AdvertisingパケットにShort IDを含める(詳細は `docs/protocol.md`):

- Company ID `0xFFFF`(Bluetooth SIGのテスト用予約値。製品化時に要再検討)+ Short ID 4バイト
- Service UUID(18バイト)+ Flags(3バイト)+ manufacturer data(8バイト)= 29バイト で31バイト内に収まる
- Device nameはscan responseに載せるが、**表示用であり識別には使わない**

### 接続後の確認: Device ID characteristic

GATTにFull IDを返すread-only characteristicを持つ(`docs/protocol.md`)。
デバッグとShort ID衝突時の最終確認用。

### Mac側: 設定ファイルにBeacon IDを保持

- `beaconctl scan` で周囲のBeaconをShort ID付きで一覧表示
- `beaconctl use <short-id>` で設定ファイル(`~/.config/agent-beacon/config.json`)に保存
- `beaconctl on|off` は設定されたIDをmanufacturer dataと照合して対象を特定する。
  scan順序・Device name・CoreBluetoothのUUIDには依存しない
- 未設定の場合、発見されたBeaconがちょうど1台のときのみそれを使う(単一台での
  試用を妨げないため)。複数台見つかったらエラーにして `use` を促す

## 検討した代替案

| 案 | 不採用の理由 |
|---|---|
| Device nameに個体IDを埋める(例: `AgentBeacon-5e6f`) | 動作はするが、nameは表示用途と識別用途が混ざり、長さ制約もきつい。識別はmanufacturer dataに分離する方が明確 |
| BLE MACアドレス | macOSのCoreBluetoothが公開しないため識別に使えない |
| CoreBluetoothのペリフェラルUUIDを保存 | per-Macかつ再生成されうる。Mac間で設定を持ち回れない |
| ペアリング/ボンディング | v0.1には過剰な複雑性。open write方針(ADR 0001)とも不整合 |
| 初回setup時にIDを採番してFlashに書き込む | FICR DEVICEIDで足りるのに書き込み処理と状態を増やす理由がない |

## Consequences

- ファームウェアは個体ごとのビルド差分なしで同一バイナリを全台に書ける
- 将来の専用nRF52840基板でもFICR DEVICEIDはそのまま使える(Zephyr移行時も同様)
- Company ID `0xFFFF` はテスト用予約値のため、製品として出す場合は
  Bluetooth SIGのCompany ID取得または別方式(service data等)への移行が必要
