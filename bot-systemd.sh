#!/bin/bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="tg_insta_bot.service"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$SERVICE_DIR/$SERVICE_NAME"

echo "⚙️ Рабочая директория проекта: $DIR"

if [ ! -d "$DIR/venv" ]; then
    echo "📦 Виртуальное окружение не найдено. Создаю..."
    python3 -m venv "$DIR/venv"
    
    if [ -f "$DIR/requirements.txt" ]; then
        echo "📥 Устанавливаю зависимости из requirements.txt..."
        "$DIR/venv/bin/pip" install --upgrade pip
        "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"
    else
        echo "⚠️ Внимание: файл requirements.txt не найден в папке $DIR!"
    fi
else
    echo "✅ Виртуальное окружение уже существует."
fi

echo "⚙️ Подготовка пользовательской службы systemd..."

mkdir -p "$SERVICE_DIR"

cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=Telegram Instagram Downloader Bot
After=network.target

[Service]
WorkingDirectory=$DIR
Environment="PATH=$DIR/venv/bin"
ExecStart=$DIR/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

echo "🔄 Перезагрузка конфигурации systemd..."
systemctl --user daemon-reload

echo "✅ Включение автозапуска..."
systemctl --user enable $SERVICE_NAME

echo "🚀 Перезапуск / запуск бота..."
systemctl --user restart $SERVICE_NAME

loginctl enable-linger $USER

echo "🎉 Готово! Бот развернут и запущен в фоне."
echo "Посмотреть статус: systemctl --user status $SERVICE_NAME"
echo "Посмотреть логи:   journalctl --user -u $SERVICE_NAME -f"