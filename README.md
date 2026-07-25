# agent-beacon

**A physical light for when AI agents need your attention.**

AIエージェント(まずはClaude Code)が人間の入力・承認・判断を必要としたときだけ、
手元の物理LEDを点灯させるデバイス。通知内容は表示しない。
「AIが人間のAttentionを必要としている」という1つの状態だけを物理世界に出す。

## 構成

```
Claude Code → Hooks → beaconctl (CLI) → BLE → XIAO nRF52840 → LED
```

| ディレクトリ | 責務 |
|---|---|
| `firmware/` | XIAO nRF52840向けファームウェア(Arduino + Bluefruit)。エージェントのことは知らない |
| `cli/` | Mac側CLI `beaconctl`(Python + bleak) |
| `integrations/claude-code/` | Claude Code Hooks設定とHookスクリプト(M2) |
| `docs/` | プロトコル仕様と設計判断(ADR) |

## マイルストーン

1. **M1**: 特定のBeaconを一意に識別し、MacからBLE経由でそのBeaconのオンボードLEDをON/OFF ✅
2. **M2**: Claude Codeが人間待ちでON、対応して処理が再開したらOFF ✅
3. **M3**: 複数Macで1台のBeaconを共有(色ビット=ホスト割り当て + 順繰り表示 + 複数同時接続) ✅ — [ADR 0004](docs/adr/0004-multi-host-sharing.md)

## 使い方

ファームウェアの書き込みは [firmware/README.md](firmware/README.md)、
Claude Code連携は [integrations/claude-code/README.md](integrations/claude-code/README.md) 参照。

```sh
uv run cli/beaconctl.py scan                        # 周囲のBeaconをShort ID付きで一覧
uv run cli/beaconctl.py use 5e6f7a8b                # 対象BeaconのIDを設定に保存
uv run cli/beaconctl.py on                          # 自ホストのattentionビットを立てる
uv run cli/beaconctl.py off                         # 自ホストのattentionビットを落とす
uv run cli/beaconctl.py status                      # 現在の状態を読み出す
```

Beaconの識別はDevice nameやscan順序ではなく、nRF52840の固有IDで行う
([ADR 0002](docs/adr/0002-beacon-identity.md))。
初回実行時はターミナルにBluetooth権限の許可を求められる。

### 複数Macで1台のBeaconを共有する(M3)

各Macに色ビットを1つ割り当てる(赤/緑/青、[ADR 0004](docs/adr/0004-multi-host-sharing.md))。
`on`/`off` はread-modify-writeで**自分のビットだけ**を操作するため、
あるMacの解除が他のMacの「待ち」を消すことはない。

```sh
# Mac A(デフォルトの赤のままでよい)
uv run cli/beaconctl.py use 5e6f7a8b

# Mac B
uv run cli/beaconctl.py use 5e6f7a8b --color green
```

複数ホストが同時に待っているときは、Beaconが各色を800msずつ順繰りに表示する。

## 開発とテスト

TDDで進める(方針は [ADR 0003](docs/adr/0003-test-strategy.md))。
プロトコルを変えるときは `docs/protocol.md` と `tests/protocol_vectors.json` を
先に更新し、テストを落としてから実装する。

```sh
make test        # ホストテスト: CLIユニット + ファームのdecodeロジック + 共有ベクタ
make test-e2e    # + 実機BLE往復 (Beaconが近くにあり、BluetoothがONのとき)
make firmware    # ファームウェアのビルド
make flash       # ビルドして書き込み
```

LEDが実際に光るかの目視確認は、最後の受け入れテストとしてだけ行う。

## ドキュメント

- 設計判断: [docs/adr/0001-minimal-e2e-architecture.md](docs/adr/0001-minimal-e2e-architecture.md)
- Beacon識別: [docs/adr/0002-beacon-identity.md](docs/adr/0002-beacon-identity.md)
- テスト戦略: [docs/adr/0003-test-strategy.md](docs/adr/0003-test-strategy.md)
- 複数Mac共有(M3): [docs/adr/0004-multi-host-sharing.md](docs/adr/0004-multi-host-sharing.md)
- BLEプロトコル: [docs/protocol.md](docs/protocol.md)
