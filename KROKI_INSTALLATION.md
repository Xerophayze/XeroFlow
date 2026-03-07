# Kroki Local Installation Guide

This guide explains how to install and manage a local Kroki instance on your Ubuntu 24.04 server for offline Mermaid diagram rendering.

## Quick Installation

1. **Transfer the installation script to your Ubuntu server:**
   ```bash
   # From your Windows machine, copy the script to the server
   scp install_kroki_local.sh searxng@searxng.local:/tmp/
   ```

2. **SSH into your Ubuntu server:**
   ```bash
   ssh searxng@searxng.local
   ```

3. **Run the installation script:**
   ```bash
   cd /tmp
   chmod +x install_kroki_local.sh
   sudo bash install_kroki_local.sh
   ```

The script will:
- ✅ Check for Docker and Docker Compose
- ✅ Create `/opt/kroki` directory
- ✅ Generate `docker-compose.yml` with all services
- ✅ Pull the latest Kroki images
- ✅ Start the Kroki stack
- ✅ Verify health and connectivity
- ✅ Create a `kroki` management command

## What Gets Installed

The script installs a complete Kroki stack with:
- **Kroki Gateway** - Main API server (port 8000)
- **Mermaid Renderer** - For Mermaid diagrams
- **BPMN Renderer** - For BPMN diagrams
- **Excalidraw Renderer** - For Excalidraw diagrams

All services are configured to restart automatically on system boot.

## Access Points

After installation, Kroki is accessible at:
- **Local (on Ubuntu server):** `http://localhost:8000`
- **Network (from other machines):** `http://searxng.local:8000`
- **Health check:** `http://searxng.local:8000/health`

## Management Commands

The installation creates a convenient `kroki` command for management:

```bash
# Show status and health
kroki status

# View logs (follow mode)
kroki logs

# Restart services
kroki restart

# Stop services
kroki stop

# Start services
kroki start

# Update to latest images
kroki update

# Remove completely
kroki remove
```

## Manual Management (Alternative)

If you prefer using Docker Compose directly:

```bash
cd /opt/kroki

# View running containers
sudo docker compose ps

# View logs
sudo docker compose logs -f

# Restart all services
sudo docker compose restart

# Stop services
sudo docker compose stop

# Start services
sudo docker compose start

# Remove everything
sudo docker compose down
```

## Testing the Installation

### From the Ubuntu server:
```bash
curl http://localhost:8000/health
```

### From your Windows machine:
```powershell
Invoke-WebRequest -Uri "http://searxng.local:8000/health"
```

### Test Mermaid rendering:
```bash
curl -X POST http://localhost:8000/mermaid/svg \
  -H "Content-Type: text/plain" \
  -d "graph TD; A-->B"
```

## Integration with ExportWord.py

The `ExportWord.py` file has been updated to automatically use your local Kroki instance:

```python
kroki_base = os.environ.get("KROKI_SERVER", "http://searxng.local:8000")
```

No environment variables or configuration needed - it just works!

## Troubleshooting

### Services won't start
```bash
# Check Docker is running
sudo systemctl status docker

# Check for port conflicts
sudo netstat -tulpn | grep 8000

# View detailed logs
cd /opt/kroki
sudo docker compose logs
```

### Can't access from network
```bash
# Check firewall (Ubuntu uses ufw)
sudo ufw status
sudo ufw allow 8000/tcp

# Verify containers are running
sudo docker compose ps
```

### Health check fails
```bash
# Wait a bit longer (services need ~10 seconds to start)
sleep 10
curl http://localhost:8000/health

# Check individual service logs
sudo docker compose logs kroki
sudo docker compose logs mermaid
```

### Update to latest version
```bash
kroki update
# or
cd /opt/kroki
sudo docker compose pull
sudo docker compose up -d
```

## Uninstallation

To completely remove Kroki:

```bash
# Using the management command
kroki remove

# Or manually
cd /opt/kroki
sudo docker compose down
sudo rm -rf /opt/kroki
sudo rm /usr/local/bin/kroki
```

## Resource Usage

Typical resource usage:
- **Disk space:** ~500MB for all images
- **Memory:** ~400MB RAM total
- **CPU:** Minimal when idle, spikes during rendering

## Security Notes

- Kroki runs on HTTP (port 8000) - suitable for internal networks
- No authentication required (trusted network assumed)
- For external access, consider adding NGINX reverse proxy with HTTPS
- Services are isolated in Docker containers

## Advanced Configuration

### Reduce services (Mermaid only)

Edit `/opt/kroki/docker-compose.yml` and remove the `bpmn` and `excalidraw` services:

```yaml
services:
  kroki:
    image: yuzutech/kroki
    container_name: kroki
    depends_on:
      - mermaid
    environment:
      - KROKI_MERMAID_HOST=mermaid
    ports:
      - "8000:8000"
    tmpfs:
      - /tmp:exec
    restart: unless-stopped

  mermaid:
    image: yuzutech/kroki-mermaid
    container_name: kroki-mermaid
    expose:
      - "8002"
    restart: unless-stopped
```

Then restart:
```bash
sudo docker compose up -d
```

### Change port

Edit `/opt/kroki/docker-compose.yml` and change the port mapping:
```yaml
ports:
  - "9000:8000"  # Use port 9000 instead
```

Update `ExportWord.py`:
```python
kroki_base = os.environ.get("KROKI_SERVER", "http://searxng.local:9000")
```

## Support

- **Kroki Documentation:** https://docs.kroki.io/
- **GitHub Issues:** https://github.com/yuzutech/kroki/issues
- **Docker Hub:** https://hub.docker.com/u/yuzutech

## Version Information

This installation uses the latest stable versions:
- Kroki: Latest from `yuzutech/kroki`
- Mermaid: Latest from `yuzutech/kroki-mermaid`
- All images are automatically updated when you run `kroki update`
