# ADR 0001: 最小構成のEnd-to-Endアーキテクチャ

- Status: Accepted
- Date: 2026-07-24

## Context

AIエージェント(最初はClaude Code)が人間のAttentionを必要としたとき、物理LEDでそれを知らせる。
通知内容は表示しない。「attentionが必要かどうか」という1bitの状態だけを物理世界に出す。

試作ハードウェアは Seeed Studio XIAO nRF52840(オンボードRGB LED、BLE)。

マイルストーン:

1. **M1**: 特定のBeaconを一意に識別し、MacからBLE経由で**そのBeacon**のオンボードLEDをON/OFFできる
2. **M2**: Claude Codeが人間待ちになったらON、人間が対応して処理が再開したらOFF

## Attentionの状態モデル(プロダクト仕様)

このプロダクトが扱う「Attention」は、「AIが質問や承認を要求している状態」だけではなく、
**「AIが処理を停止し、制御を人間に返した状態」全般**を指す。正常完了も含む。

| エージェントの状態 | LED |
|---|---|
| 自律的に処理を進めている | OFF |
| 停止し、人間側の次の行動を待っている(質問・承認要求・正常完了を含む) | ON |

この定義のもとでは、Claude Codeの `Stop` hook(ターン終了=制御を人間に返した)を
Attention ONに使うのは技術的な代替手段ではなく、状態モデルそのものの実装である。

## Decision

### 全体構成

```
Claude Code
  → Hooks (.claude/settings.json)          … integrations/claude-code/
  → beaconctl on|off (CLI)                  … cli/
  → BLE GATT write (1 byte)                 … docs/protocol.md
  → XIAO nRF52840 ファームウェア            … firmware/
  → オンボードLED
```

レイヤ間の契約は「attention = ON / OFF」の1バイトのみ。
ファームウェアはClaude Codeについて何も知らず、CLIはLEDのピンについて何も知らない。

### ファームウェア: Arduino + Seeed nRF52 Boards(非mbed)+ Bluefruit

- BSP: **Seeed nRF52 Boards**(Adafruit nRF52 coreのfork、FreeRTOS + SoftDevice + Bluefruit52Lib)。
  Seeed公式WikiがBLE用途にはこちらを推奨(mbed版はTinyML向け)。
- BLE: `bluefruit.h` で peripheral + custom GATT service + writable characteristic。
  公式example(`custom_hrm.ino`)に同型の実装パターンあり。
- ビルド/書き込み: `arduino-cli`(FQBN: `Seeeduino:nrf52:xiaonRF52840`)。
  シリアル書き込み失敗時はUF2(リセットボタンのダブルタップ → マスストレージにコピー)がフォールバック。
- LED: オンボードRGB LED(RED=P0.26, GREEN=P0.30, BLUE=P0.06)。**active low**
  (`digitalWrite(pin, LOW)` で点灯)。v0.1は赤1色のみ使用。

検討した代替案:

| 案 | 不採用の理由 |
|---|---|
| CircuitPython | 手軽だが、将来の電池駆動(deep sleep)への移行に最も不利 |
| Zephyr / nRF Connect SDK | 専用基板移行時の本命だが、custom GATT 1本の試作には過剰。GATT設計はそのまま持ち越せるため、専用基板を作る段階で再評価する |
| PlatformIO | XIAO nRF52840対応がcommunity fork依存でメンテが不安定 |

### BLEプロトコル: 1 characteristic、1 byte

`docs/protocol.md` 参照。custom service + writable characteristic 1本。
1バイトのビット割り当てで色(bit0-2)と点滅(bit3)を表現し、`0x00` のみ消灯。
未知の値はfail-safe(ON、赤にフォールバック)に倒す(理由はprotocol.md参照)。
色・点滅は「複数のClaude Codeセッションが1台のBeaconを共有したとき、状態を
区別できるようにする」ために入れた。どのセッションにどの色/パターンを割り当てるかの
集約ロジックはIntegration層(M2)の責務であり、Beaconは受け取った1バイトを表示するだけ。

### Beaconの個体識別

各Beaconは工場書き込みの永続一意ID(nRF52840 FICR DEVICEID)を持ち、Mac側は
Device nameやscan順序ではなくこのIDでBeaconを指定する。方式の詳細と判断理由は
[ADR 0002](0002-beacon-identity.md)。

### Mac側CLI: Python + bleak

- **bleak** はmacOS(CoreBluetooth)対応のBLEライブラリで、2026年時点で最も活発にメンテされている
  (v3.0.1が2026-03リリース。noble系はビルドが壊れやすくリリース頻度も低い)。
- `beaconctl on` / `beaconctl off` の2コマンドのみ。service UUIDでスキャン → 接続 → 1バイトwrite → 切断。
- 常駐デーモンは作らない。状態遷移の頻度(人間待ちの発生)は低く、都度接続で十分。
  接続レイテンシが体感で問題になったら初めてデーモン化を検討する。

### Claude Code integration: 公式Hooks

`.claude/settings.json` のHookでLEDを制御する。画面パースやtmux監視は使わない。

| 状態 | Hookイベント | 動作 |
|---|---|---|
| 承認待ち | `Notification` (matcher: `permission_prompt`) | ON |
| 入力待ち(ターン終了) | `Stop` | ON |
| 入力待ち(idle通知) | `Notification` (matcher: `idle_prompt`) | ON |
| 人間がプロンプト送信 | `UserPromptSubmit` | OFF |
| 承認されてツール実行再開 | `PreToolUse` | OFF |

補足:

- `Stop` を使う理由: `idle_prompt` 通知はidle検出までに遅延があるため、ターン終了(=入力待ち開始)を
  即時に拾うには `Stop` が確実。両方ONにしても冪等なので害はない。
- `PreToolUse` を使う理由: permission承認後は `UserPromptSubmit` が発火しないため、
  ツール実行再開をOFFのトリガーにする。
- `PreToolUse` は高頻度に発火するため、Hookスクリプトはローカルの状態ファイル
  (例: `/tmp/agent-beacon.state`)と比較して**状態が変わるときだけ** `beaconctl` を呼ぶ。
- 全HookのJSON入力(stdin)には `session_id` が含まれる。v0.1は単一セッション前提だが、
  将来は「セッションごとの状態ファイル + どれか1つでも待ちならON」で複数セッションに拡張できる。

## 作らないもの(Non-goals)

- Slack等の一般通知、通知内容の表示、UI/ダッシュボード、クラウド/アカウント管理
- BLEのペアリング/ボンディング(open writeで運用。試作機の脅威モデルでは許容。
  専用基板化の際に再評価)
- 複数Beaconの管理UIや同時制御(ただし**個体識別の仕組み自体はv0.1に含む** — ADR 0002)
- 常駐ブリッジデーモン、電池駆動の省電力チューニング
- Zephyr移行(専用基板を作る段階まで保留)

## Consequences

- ファームウェアとIntegrationが1バイトのプロトコルだけで分離されるため、
  Claude Code以外のエージェント対応はHook側の追加だけで済む。
- Arduino/Bluefruit採用により試作は最速だが、数µAオーダーの省電力が必要になった時点で
  Zephyrへの書き換えが必要になる。GATT設計(UUID・値)は変えないため、CLI・Hook側は無変更で済む。
- 都度接続方式のため、Hook発火からLED点灯まで1〜2秒程度のレイテンシが見込まれる。
  Attention通知という用途では許容範囲と判断。

## References

- Claude Code Hooks: https://code.claude.com/docs/en/hooks.md / https://code.claude.com/docs/en/hooks-guide.md
- Seeed XIAO nRF52840 Wiki: https://wiki.seeedstudio.com/XIAO_BLE/
- Seeed nRF52 core (Adafruit fork): https://github.com/Seeed-Studio/Adafruit_nRF52_Arduino
- Bluefruit custom service example: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/examples/Peripheral/custom_hrm/custom_hrm.ino
- bleak: https://bleak.readthedocs.io/
