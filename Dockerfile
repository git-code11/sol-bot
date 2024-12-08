FROM python

WORKDIR ~/bot
COPY * .

RUN <<EOF
apt-get update
apt-get install -y curl sudo
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d /bin
sudo pip install poetry
poetry install
EOF

ENTRYPOINT task