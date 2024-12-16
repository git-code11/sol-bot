FROM python:3.12.8-slim-bullseye

RUN <<EOF
# install redis
apt-get install lsb-release curl gpg -y
curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
chmod 644 /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/redis.list
apt-get update -y
apt-get install redis -y
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin
EOF

WORKDIR /bot
COPY . .


RUN <<EOF
chmod +x docker-entrypoint.sh
mv docker-entrypoint.sh /usr/local/bin
pip install poetry
poetry install
EOF


ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["start-bot"]
