# skills

Codex、Claude CodeなどのAIコーディングエージェントのためのアジ鯖専用スキルをまとめたリポジトリです。

AIのプロンプトにコピペするだけで入ります:
```
https://github.com/azisaba/skills のスキルをインストールして
```

## 含まれるもの

- `[アジ鯖] Minecraft K8s Manifest生成` (`generate-minecraft-k8s-manifest`) - アジ鯖用(<https://github.com/AzisabaNetwork/minecraft-servers>)のKubernetes Manifestファイルを対話形式で生成します。
- `[アジ鯖] Resticバックアップ復元` (`restore-backup`) - アジ鯖のバックアップから指定した日時の指定したファイルを指定した場所に復元します。(`192.168.0.226`にアクセスできる環境が必要です)

## 使い方

### 全自動

CodexやClaude Codeなどのプロンプトに以下をコピペするだけです:
```
https://github.com/azisaba/skills のスキルをインストールして
```

### 手動

```shell
git clone https://github.com/azisaba/skills && cd skills && codex ; claude
```
