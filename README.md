# Let's Note Wheelpad Scroll Daemon

Panasonic Let's Noteの「ホイールパッド」で円を描くようになぞることで、スムーズなスクロールを実現するためのPythonスクリプトです。

> [!NOTE]
> **動作確認済み環境**:
> - **OS**: CachyOS
> - **WM/Compositor**: Hyprland
> - **Device**: Panasonic Let's Note SV1

## 概要
waylandではlet's note のホイールパッドを円を書くように操作してスクロールができないので、pythonを使用してスクロールできるようにしました。また、このプロジェクトはAntigravityで開発しました。(readmeも書かせました...)

## 準備

このスクリプトは `evdev` ライブラリを使用します。あらかじめインストールしておいてください。

```bash
pip install evdev
```

## インストール・設定手順

GitHubに公開・共有するためのセットアップ手順です。

### 1. スクリプトの準備
現在のディレクトリにある `wheelpad.py` を用意してください。

### 2. スクリプトをシステムの領域に配置する

自分個人のフォルダではなく、システム全体が読み込める「プログラム置き場」に移動させます。Linuxの作法として `/usr/local/bin/` に置くのが一般的です。

```bash
sudo cp wheelpad.py /usr/local/bin/wheelpad.py
```

### 3. systemdサービスファイルの作成

systemd は、Linuxの裏側で動くあらゆるサービス（ネットワークやBluetoothなど）を管理している親玉です。ここに「うちのスクリプトも起動時に動かしてね」という設計図を渡します。

以下のコマンドで新しい設計図（サービスファイル）を作成します。

```bash
sudo nano /etc/systemd/system/wheelpad.service
```

ファイルが開いたら、以下の内容をペーストして保存します（nanoの場合は `Ctrl+O` → `Enter` で保存、`Ctrl+X` で終了です）。

```ini
[Unit]
Description=Let's Note Wheelpad Scroll Daemon
After=multi-user.target

[Service]
# プログラムの実行コマンド（Pythonのパスとスクリプトのパス）
ExecStart=/usr/bin/python /usr/local/bin/wheelpad.py
# もし何かのエラーで落ちても、3秒後に自動で再起動する設定
Restart=always
RestartSec=3

[Install]
# OSの起動が終わったタイミングで実行するという意味
WantedBy=multi-user.target
```

> [!NOTE]
> **専門用語解説**: `[Unit]` はこのサービスの概要、`[Service]` は具体的な動かし方、`[Install]` はどのタイミングで起動するか（OS起動時など）を定義しています。

### 4. 魔界の扉を開く（サービスの有効化と起動）

最後に、作成した設計図をシステムに認識させて、起動＆自動起動の設定を行います。以下の3つのコマンドを順番に実行してください！

```bash
# 1. systemdに「新しい設定ファイル作ったよ！」と教え込む
sudo systemctl daemon-reload

# 2. 次回のPC起動時から自動で立ち上がるようにする（有効化）
sudo systemctl enable wheelpad.service

# 3. 今すぐ裏側で起動させる！
sudo systemctl start wheelpad.service
```

### 5. 動作確認

ここまで来たら、普通にパッドのフチをくるくるしてみてください。
ターミナルで何も実行していないのに、スムーズにスクロールすれば大成功です！

念のため、裏側でちゃんと動いているか（エラーが出ていないか）を確認するには以下のコマンドを使います。
`active (running)` と緑色で表示されていれば完璧です。

```bash
sudo systemctl status wheelpad.service
```

## ライセンス

[MIT License](LICENSE) 
