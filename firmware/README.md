# firmware

Seeed XIAO nRF52840 向けファームウェア。BLE peripheralとして
[Attention Service](../docs/protocol.md) を公開し、1バイトの状態でオンボードLEDを制御する。
エージェント(Claude Code等)のことは一切知らない。

## セットアップ(初回のみ)

```sh
brew install arduino-cli
arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json
arduino-cli core update-index
arduino-cli core install Seeeduino:nrf52
```

## ビルド

FQBNはボードにより異なる(`arduino-cli board list` が表示してくれる):

- 無印: `Seeeduino:nrf52:xiaonRF52840`
- Sense: `Seeeduino:nrf52:xiaonRF52840Sense`

```sh
arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840Sense firmware/agent_beacon
```

## 書き込み

USB接続してシリアル経由:

```sh
arduino-cli board list   # ポート確認 (/dev/cu.usbmodemXXXX) とFQBN確認
arduino-cli upload -p /dev/cu.usbmodemXXXX --fqbn Seeeduino:nrf52:xiaonRF52840Sense firmware/agent_beacon
```

シリアルDFUが `Timed out waiting for acknowledgement` で失敗することがある。
一度リトライすると通ることが多い。それでも失敗する場合は下のUF2を使う。

シリアル書き込みに失敗する場合はUF2で:

1. リセットボタンをダブルタップ → `XIAO-SENSE` 等の名前でマスストレージがマウントされる
2. `arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840 --export-binaries firmware/agent_beacon`
   で生成される `.uf2` をドライブにコピー

## 動作

- 起動時: LED消灯、`AgentBeacon` としてadvertise(manufacturer dataにShort ID)
- Attention State characteristic への write: `0x00` で消灯、それ以外で赤LED点灯(fail-safe)
- 切断されても状態は保持
