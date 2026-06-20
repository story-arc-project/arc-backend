# arc-backend

## Requirements
* uv
* docker
* docker-compose-plugin

These can be installed by the following command (for Linux)
```
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -LsSf https://raw.githubusercontent.com/bunniesnu/docker-install/refs/heads/main/install.sh | sh
```

## Usage
```
git clone https://github.com/story-arc-project/arc-backend.git
cd arc-backend
chmod +x run.sh
./run.sh
```

## About file uploads (S3)

Currently, the project uses minio container through docker-compose.yml configuration. To change to S3 or S3-compatible cloud services (e.g. R2), following files need to be changed.
- docker-compose.yml
- nginx/default.conf.template