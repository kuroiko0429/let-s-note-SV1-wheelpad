# Let's Note Wheelpad Scroll Daemon

Panasonic Let's Noteの「ホイールパッド」で円を描くようになぞることで、スムーズなスクロールを実現するためのPythonスクリプトです。

> [!NOTE]
> **動作確認済み環境**:
> - **OS**: CachyOS
> - **WM/Compositor**: Hyprland
> - **Device**: Panasonic Let's Note SV1

## 概要
waylandではlet's note のホイールパッドを円を書くように操作してスクロールができないので、pythonを使用してスクロールできるようにしました。また、このプロジェクトはAntigravityで開発しました。(readmeも書かせました...)

## 主な機能
- **スムーズスクロール**: 高解像度イベント (`REL_WHEEL_HI_RES`) による滑らかなスクロール対応
- **水平スクロール**: 2本指で縁をなぞると横スクロール
- **動的速度調整**: 早く回すとスクロールが加速
- **慣性スクロール**: 指を離した後も設定した減速率でスクロールがしなやかに持続
- **柔軟な設定**: `config.toml` による感度、デッドゾーン、各種速度のカスタマイズ

## 準備

このスクリプトは `evdev` ライブラリを使用します。あらかじめインストールしておいてください。

```bash
pip install evdev
```

## インストール・設定手順

GitHubに公開・共有するためのセットアップ手順です。

### 1. スクリプトの準備
現在のディレクトリにある `wheelpad.py` を用意してください。

### 2. スクリプトと設定ファイルの配置

自分個人のフォルダではなく、システム全体が読み込める場所に移動させます。Linuxの作法として実行ファイルは `/usr/local/bin/`、設定ファイルは `/etc/` に置くのが一般的です。

```bash
# プログラムを配置
sudo cp wheelpad.py /usr/local/bin/wheelpad.py
sudo chmod +x /usr/local/bin/wheelpad.py

# 設定ファイルを配置
sudo mkdir -p /etc/wheelpad
sudo cp config.toml /etc/wheelpad/config.toml
```

> [!TIP]
> **設定の変更方法**
> スクロール感度や慣性の強さを変えたい場合は `/etc/wheelpad/config.toml` を編集してください。
> ```bash
> sudo nano /etc/wheelpad/config.toml
> ```
> 編集後、`sudo systemctl restart wheelpad.service` で反映されます。

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

### 開発・デバッグ時の使い方

システムにインストールせず、手元で一時的に動かす場合は設定ファイルのパスを直指定できます。
`--debug` フラグをつけると、ターミナルにタッチ検出状況やスクロール速度が出力されます。

```bash
sudo python wheelpad.py --config ./config.toml --debug
```

## ライセンス

[MIT License](LICENSE) 
