# ADR 0004: 複数Macによる1台のBeacon共有(M3)

- Status: Accepted(実装はM2完了後 = M3)
- Date: 2026-07-24

## Context

複数のMacが1台のBeaconを共有する構成(Mac A/B/C → 1 Beacon)を可能にしたい。

```
Mac A ─┐
Mac B ─┼── BLE ──→ ● Agent Beacon
Mac C ─┘
```

現状の課題は2つ:

1. **BLE接続**: Bluefruitのデフォルトは同時1接続で、1台のMacが接続中は
   advertisingが停止し、他のMacからBeaconが見えなくなる
2. **状態の意味論**: 全Macが同じ1バイトに書くと後勝ち(last-write-wins)になり、
   Mac Aが自分のOFFを書いた瞬間にMac Bの「待ち」が消えてしまう

また、XIAOのオンボードRGB LEDは3素子1パッケージのため、複数色を同時点灯すると
混色して1色に見え、「どのMacが呼んでいるか」を見分けられない。

## Decision

### 1. 色ビット = ホスト割り当て(規約)

プロトコルの色ビット(bit0-2)を**ホストごとの割り当て**として使う:
Mac A = 赤(bit0)、Mac B = 緑(bit1)、Mac C = 青(bit2)。

各Macは **read-modify-write** で自分のビットだけを操作する:

- Attention発生: 現在値を読む → 自分のビットを立てる → 書き戻す
- Attention解除: 現在値を読む → **自分のビットだけ**落とす → 書き戻す

これにより、状態バイトは常に「いま待っているホストの集合」を表す。
プロトコル(1バイト)もファームウェアの状態も変更不要で、Beaconは
受け取ったバイトを表示するだけという分離(ADR 0001)を維持できる。

**キューは作らない**。このプロダクトの通知は「人間が対応するまで出続けるべき状態」
であり、「一度表示したら消費されるイベント」ではない。集合方式は冪等
(何度書いても同じ結果)で、取りこぼし・二重積み・掃除の問題が構造的に存在しない。

### 2. 表示: 複数ビット時は混色ではなく順繰り表示

複数の色ビットが立っているときは、混色(判読困難)ではなく
**立っているビットを1色ずつ順繰りに表示**する(目安800ms/色):

| 状態バイト | 表示 |
|---|---|
| `0x01` | 赤の点灯 |
| `0x03` | 赤→緑→赤→… |
| `0x07` | 赤→緑→青→赤→… |

点滅ビット(bit3)は表示全体に直交して適用する(誰かが点滅を要求すると
表示全体が点滅)。1ビットのみの場合は従来通り。

動作イメージ:

```
t0  全員作業中                    0x00  消灯
t1  Mac Aが人間待ちに             0x01  赤点灯
t2  Mac Bも人間待ちに             0x03  赤→緑→…
t3  人間がMac Aに返信(Aのみ解除)  0x02  緑点灯だけが残る
```

表示は常に現在のバイトから再計算されるため、追加・解除のタイミングや順序に
表示が依存しない。

実装は `attention_state.h` に「状態バイト + フェーズ番号 → その瞬間の1色」の
純粋関数を足す形で行い、ADR 0003の手順(protocol.md とテストベクタを先に更新)に従う。

### 3. ファームウェア: 複数同時接続の受け入れ

調査結果(公式ソース確認済み):

- SoftDevice S140はperipheral roleで最大20同時接続をサポート
  (`BLE_GAP_ROLE_COUNT_COMBINED_MAX = 20`)。Bluefruitのデフォルトは
  `Bluefruit.begin(1, 0)` = 同時1接続
- 接続成立でadvertisingは自動停止し、ライブラリは自動再開しない
- `restartOnDisconnect(true)` は「**全**接続が切れたとき」しか広告を再開しない
  (再開条件が `0 == Bluefruit.Periph.connected()`)。1台残存中に枠が空いても
  広告されない落とし穴がある

変更点(公式example `bleuart_multi` と同型):

1. `Bluefruit.begin(4, 0)` — 同時接続枠を4に(3 Mac + 余裕)
2. connect callbackで `Bluefruit.Advertising.start(0)` — 満枠まで広告を継続し、
   接続中も他のMacからBeaconが見えるようにする
3. disconnect callbackでも `isRunning()` を確認して広告を再開する

なお「接続→1バイトwrite→切断」の短命接続モデル(ADR 0001)は維持する。
同時滞在数は普段0〜1なので4枠で十分。

## 既知の制約(許容する)

- **read-modify-writeのレース**: 2台がほぼ同時に読み書きすると片方の更新が
  消えうる(lost update)。書き込み頻度が低いため許容する。問題になったら
  「自分のビットのset/clearだけを送るコマンド」をプロトコルに足し、Beacon側で
  合成する方式に移行する
- **3台まで**: 色ビットは3つ。4台以上はホストID付きプロトコル(v0.3)が必要
- **点滅は全体共有**: 点滅ビットは1つなのでホストごとに点滅は分けられない

## References

- S140仕様: https://www.nordicsemi.com/Products/Development-software/s140
- `ble_gap.h`(S140 v7.3.0): https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/cores/nRF5/nordic/softdevice/s140_nrf52_7.3.0_API/include/ble_gap.h
- Bluefruit multi-connection example: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/examples/Peripheral/bleuart_multi/bleuart_multi.ino
- Advertising再開の挙動: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/src/BLEAdvertising.cpp
