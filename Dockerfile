FROM python:3.12.8-slim-bullseye

RUN <<EOF
apt-get update
apt-get install -y curl sudo
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /bin
EOF

WORKDIR /bot
COPY . .

RUN <<EOF
sudo pip install poetry
poetry install
EOF

ENTRYPOINT ["task"]

CMD ["start-bot"]

