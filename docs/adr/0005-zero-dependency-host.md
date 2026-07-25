# ADR 0005: ライブラリを置けないホスト向けゼロ依存クライアント(beaconctl-lite)

- Status: Accepted(`swift-lite` ブランチのみ。mainにはマージしない)
- Date: 2026-07-25

## Context

ポリシー上「そのMacで開発しているプロジェクトのライブラリ以外はインストール禁止」
というホスト(Mac)がある。agent-beaconはそのMacのプロジェクトではないため、
bleakはもちろん、uvやvenvすら置けない。

検討した代替案:

- **SSH委譲**(他のMacにBLE書き込みを依頼): 委譲先がRemote Loginを開けて
  常時起きている必要があり、単一障害点になる。不採用
- **ファイル同期経由**(iCloud等で状態を共有し他のMacが書く): 同期遅延が
  不定で、やはり他のMacの稼働に依存する。不採用

一方、macOSには**インストール不要のBLEスタックが標準搭載**されている:
CoreBluetooth(OSフレームワーク)と、開発機なら必ず入っている
Swiftツールチェーン(Xcode Command Line Tools)。bleakが必要なのは
「PythonからBLEに触る」ためであって、BLE自体には外部依存は要らない。

## Decision

### Swift + CoreBluetooth の単一ファイルクライアントを追加する

`cli/beaconctl_lite.swift`。配布はソース(このリポジトリ)で、各ホストが
`swiftc` で1回ビルドする(`make lite`)。バイナリ配布はしない
(Gatekeeperの隔離・署名問題を避け、監査可能性を保つため)。

### スコープは on / off / status のみ

Hookが必要とする操作だけを実装する。`scan`(一覧)と `use`(設定保存)は
省略し、設定はPython版と同一の `~/.config/agent-beacon/config.json` を
読むだけにする(IDが分かっていれば手で1行書けば済む):

```json
{"beacon_id": "5e6f7a8b", "host_color": "blue"}
```

### プロトコル実装としてリポジトリで管理し、共有ベクタでロックする

RMW・状態表示のロジックは `tests/protocol_vectors.json` と
Python版との全数比較でテストする(`tests/test_lite.py`。
`swiftc` が無い環境では自動スキップ)。プロトコルを話す実装を
リポジトリ外に置くと、次のプロトコル変更でその実装だけが静かに壊れるため、
「使うMacが1台でも実装はリポジトリで管理」を原則とする。

### mainにはマージせず `swift-lite` ブランチで維持する

需要が単一ホストに限られるため。プロトコル変更時はこのブランチを
mainにrebaseしてテストを回す(ベクタ比較が乖離を検出する)。
需要が増えたらmainへのマージを再検討する。

## 使い方(対象ホストで)

```sh
git clone <repo> && cd agent-beacon && git switch swift-lite
make lite                                   # swiftc で1回ビルド
mkdir -p ~/.config/agent-beacon
echo '{"beacon_id": "<short-id>", "host_color": "blue"}' > ~/.config/agent-beacon/config.json
cli/beaconctl-lite status                   # 動作確認(初回はBluetooth権限の許可)
```

Hook連携は `settings.example.json` のコマンドに環境変数を1つ足すだけ:

```
AGENT_BEACON_CTL=/PATH/TO/agent-beacon/cli/beaconctl-lite python3 /PATH/TO/.../attention_hook.py
```

## 既知の制約(許容する)

- Xcode Command Line Tools(swiftc)が前提。開発機以外では使えない
- `scan`/`use` が無いので、Short IDは他のMacで調べて手で設定する
- 初回実行時にターミナルへのBluetooth権限プロンプトが出る(bleak版と同じ)

## References

- 全体設計: [ADR 0001](0001-minimal-e2e-architecture.md) / 複数Mac共有: [ADR 0004](0004-multi-host-sharing.md)
- プロトコル: [../protocol.md](../protocol.md)(v0.2のRMW規約に従う)
