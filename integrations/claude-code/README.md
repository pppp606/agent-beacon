# integrations/claude-code

Claude Code公式Hooksと Agent Beacon をつなぐブリッジ。

## 動作

状態モデル(ADR 0001): エージェントが**自律的に動いている間はOFF**、
**停止して制御を人間に返したらON**(質問・承認要求・正常完了を含む)。

| Hookイベント | 意味 | セッション状態 |
|---|---|---|
| `Stop` | ターン終了(制御を人間に返した) | waiting |
| `Notification` (`idle_prompt`\|`permission_prompt`) | 入力待ち/承認待ち通知 | waiting |
| `UserPromptSubmit` | 人間がプロンプト送信 | working |
| `PreToolUse` | ツール実行(承認後の再開を含む) | working |
| `SessionStart` | セッション開始/再開 | working |
| `SessionEnd` | セッション終了 | 削除 |

複数セッションは `session_id` ごとに集約され、
**どれか1つでも waiting ならLED ON、全部 working になったらOFF**。

Hook本体はローカルファイル更新だけで即終了し(Claude Codeをブロックしない)、
BLE書き込みはデタッチされた `--sync` プロセスが desired/applied の2ファイルで
最新状態に収束させる。イベントからLED反映までは数秒(BLE接続時間)。

## インストール

1. Beaconをセットアップしておく(`beaconctl use <id>` 済みであること。ルートREADME参照)
2. `settings.example.json` の `/PATH/TO/agent-beacon` をこのリポジトリの絶対パスに置換
3. その `hooks` を `~/.claude/settings.json` にマージ(全プロジェクトで有効化する場合)。
   特定プロジェクトだけならそのプロジェクトの `.claude/settings.json` へ

必要なもの: `python3`(標準ライブラリのみ)、`uv`(BLE書き込みプロセスが
`uv run cli/beaconctl.py` を呼ぶ)。

## 状態・デバッグ

状態ディレクトリ: `~/.local/state/agent-beacon/`(`AGENT_BEACON_STATE_DIR` で変更可)

- `sessions/<session_id>` — 各セッションの waiting / working
- `desired` / `applied` — 集約結果と、Beaconへ書き込み済みの状態
- `hook.log` — イベントと書き込みの記録

うまく動かないときは `hook.log` と `beaconctl status` を確認。
BLE書き込み失敗(Beacon圏外など)は `applied` を更新しないため、
次のイベントで自動リトライされる。

テスト: `make test`(偽beaconctlでフロー全体を検証。実機不要)
